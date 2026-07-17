from uvicorn import logging
import os
import json
import base64
import audioop
import asyncio
import websockets
from urllib.parse import urlencode
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.rest import Client
from pydantic import BaseModel
from dotenv import load_dotenv
import logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)
from loguru import logger

load_dotenv()

app = FastAPI()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not found in .env")

# The Gemini Multimodal Live API websocket URL

GEMINI_WS_URL = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={GEMINI_API_KEY}"

@app.api_route("/", methods=["GET", "POST"])
async def twilio_webhook(request: Request):
    print("request reached")
    # Consume the body to prevent Uvicorn connection drop (ERR_NGROK_3004)
    await request.body()
    """
    Twilio calls this endpoint when a phone call comes in.
    We return TwiML instructing Twilio to open a WebSocket to us.
    """
    host = request.headers.get("host")
    logger.info(f"Host: {host}")
    resp = VoiceResponse()
    connect = Connect()
    # Tell Twilio to connect via WebSocket to our /media endpoint
    connect.stream(url=f"wss://{host}/media")
    resp.append(connect)
    
    return Response(content=str(resp), media_type="text/xml")


@app.websocket("/media")
async def twilio_media_stream(websocket: WebSocket):
    """
    Twilio connects to this WebSocket and streams audio back and forth.
    We act as a bridge between Twilio and Gemini.
    """
    await websocket.accept()
    print("Twilio WebSocket connected!")

    if not GEMINI_API_KEY:
        print("Closing: No Gemini API Key")
        await websocket.close()
        return

    # Connect to Gemini
    try:
        async with websockets.connect(GEMINI_WS_URL, open_timeout=30) as gemini_ws:
            logger.info("Connected to Gemini Live API!")
            
            # Initial setup message to Gemini
            setup_msg = {
                "setup": {
                    "model": "models/gemini-2.5-flash-native-audio-preview-12-2025",
                    "generationConfig": {
                        "responseModalities": ["AUDIO"]
                    }
                }
            }
            await gemini_ws.send(json.dumps(setup_msg))
            
            logger.info("Sent setup message")
            stream_sid = None

            # Task 1: Read audio from Twilio -> Transcode -> Send to Gemini
            async def receive_from_twilio():
                nonlocal stream_sid
                try:
                    while True:
                        msg = await websocket.receive_text()
                        data = json.loads(msg)
                        
                        if data["event"] == "start":
                            stream_sid = data["start"]["streamSid"]
                            logger.info(f"Stream started: {stream_sid}")
                            
                        elif data["event"] == "media":
                            # Twilio sends base64 mulaw @ 8000Hz
                            audio_b64 = data["media"]["payload"]
                            mulaw_bytes = base64.b64decode(audio_b64)
                            
                            # Transcode: mulaw -> PCM 16-bit 8kHz -> PCM 16-bit 16kHz
                            pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
                            pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
                            
                            # Send to Gemini
                            gemini_msg = {
                                "realtimeInput": {
                                    "mediaChunks": [{
                                        "mimeType": "audio/pcm;rate=16000",
                                        "data": base64.b64encode(pcm_16k).decode('utf-8')
                                    }]
                                }
                            }
                            await gemini_ws.send(json.dumps(gemini_msg))
                            
                        elif data["event"] == "stop":
                            print("Twilio stopped the stream.")
                            break
                except Exception as e:
                    print(f"Twilio disconnect: {e}")

            # Task 2: Read audio from Gemini -> Transcode -> Send to Twilio
            async def receive_from_gemini():
                try:
                    while True:
                        msg = await gemini_ws.recv()
                        data = json.loads(msg)
                        if "serverContent" in data:
                            content = data["serverContent"]
                            if "modelTurn" in content:
                                parts = content["modelTurn"]["parts"]
                                for part in parts:
                                    if "inlineData" in part:
                                        # Gemini sends base64 PCM 16-bit @ 24000Hz
                                        audio_b64 = part["inlineData"]["data"]
                                        pcm_24k = base64.b64decode(audio_b64)
                                        
                                        # Transcode: PCM 16-bit 24kHz -> PCM 16-bit 8kHz -> mulaw
                                        pcm_8k, _ = audioop.ratecv(pcm_24k, 2, 1, 24000, 8000, None)
                                        mulaw_bytes = audioop.lin2ulaw(pcm_8k, 2)
                                        
                                        if stream_sid:
                                            # Send back to Twilio
                                            out_msg = {
                                                "event": "media",
                                                "streamSid": stream_sid,
                                                "media": {
                                                    "payload": base64.b64encode(mulaw_bytes).decode('utf-8')
                                                }
                                            }
                                            await websocket.send_text(json.dumps(out_msg))
                except Exception as e:
                    print(f"Gemini disconnect: {e}")

            # Run both tasks concurrently
            await asyncio.gather(
                receive_from_twilio(),
                receive_from_gemini()
            )

    except Exception as e:
        print(f"Failed to connect to Gemini: {e}")

class CallRequest(BaseModel):
    to_number: str

@app.post("/outbound")
def trigger_outbound_call(call_request: CallRequest, request: Request):

    print("Trigger made")
    """
    Trigger a phone call from Twilio to a specific number.
    When the user picks up, Twilio will hit the '/' webhook and connect to Gemini.
    """
    '''twilio_client = Client(account_sid, auth_token)
    
    # We construct the public ngrok URL dynamically from the incoming HTTP request
    host = request.headers.get("host")
    protocol = request.headers.get("x-forwarded-proto", "https")
    webhook_url = f"{protocol}://{host}/"

    try:
        call = twilio_client.calls.create(
            to=call_request.to_number,
            from_=from_number,
            url=webhook_url
        )
        return {"status": "success", "call_sid": call.sid, "webhook_url": webhook_url}
    except Exception as e:
        return {"status": "error", "message": str(e)}'''

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
