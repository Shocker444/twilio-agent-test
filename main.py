import asyncio
import time
import contextlib
import json
import base64
import os
from typing import AsyncIterator
from uuid import uuid4
from loguru import logger

import uvicorn
from dotenv import load_dotenv
from fastapi import (
    FastAPI, 
    WebSocket, 
    WebSocketDisconnect, 
    Response, 
    Request, 
    HTTPException
)
from fastapi.middleware.cors import CORSMiddleware

from twilio.twiml.voice_response import VoiceResponse, Connect
from pydantic import BaseModel


from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableGenerator
from langgraph.checkpoint.memory import InMemorySaver
from datetime import datetime, timezone
from agent import agent
from utils import merge_async_iters, get_today_str, to_mongo
from settings import settings


from deepgram_setup import DeepgramSTT, DeepgramTTS
from elevenlabs_setup import ElevenLabsTTS

from events import (
    AgentTriggerEvent,
    TTSChunkEvent,
    AgentChunkEvent,
    AgentEndEvent,
    ToolCallEvent,
    ToolReturnEvent,
    VoiceAgentEvent,
    InterruptEvent,
    TwilioEvent,
    event_to_dict,
    )
    
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.api_route("/", methods=["GET", "POST"])
async def twilio_webhook(request: Request):
    logger.info("request reached")
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

class VoicePipeline:
    def __init__(self, stream_sid: str):
        self.stream_sid = stream_sid
        self.has_triggered = False

        # Latency trackers
        self.stt_end_time = None
        self.first_agent_chunk_time = None

    async def twilio_inp(self):
        pass

    async def _stt_stream(
            self,
            audio_stream: AsyncIterator[bytes],
        ) -> AsyncIterator[VoiceAgentEvent]:

        stt = DeepgramSTT(_stream_sid=self.stream_sid)
        logger.info("STT stream started")

        async def send_audio():
            """
            Background task that pumps audio chunks to Deepgram 
            """
            chunk_count = 0

            try:
                # Stream each audio chunk to deepgram as it arrives
                async for audio_chunk in audio_stream:
                    if isinstance(audio_chunk, bytes):
                        await stt.send_audio(audio_chunk)
                    elif isinstance(audio_chunk, str):
                        # Handle the text signal
                        pass
            finally:
                await asyncio.sleep(0.2)  # wait for any final events
                await stt.close()

        # launch the audio task in the background

        send_task = asyncio.create_task(send_audio())
        #print(f"🚀 Background audio task created: {send_task}")

        try:

            async for event in stt.receive_events():
                yield event
        
        finally:

            with contextlib.suppress(asyncio.CancelledError):
                send_task.cancel()
                await send_task

            await stt.close()



    async def _agent_stream(
            self,
            event_stream: AsyncIterator[VoiceAgentEvent]
    ) -> AsyncIterator[VoiceAgentEvent]:
        '''
        Processes STT events through the agent and yields VoiceAgentEvents
        '''

        thread_id = str(uuid4())  # unique ID for this conversation thread
        async for event in event_stream:
            yield event

            
            if event.type == "stt_output" or event.type == "agent_trigger":
                # Mark the time when STT finished returning text (or initial trigger)
                self.stt_end_time = time.perf_counter()
                self.first_agent_chunk_time = None
                
                buffer = []
                stream = agent.astream(
                    {"messages": [HumanMessage(content=event.text)]},
                    {"configurable": {"thread_id": thread_id}},
                    stream_mode="messages"
                )


                async for message, metadata in stream:
                    # logger.info(f"Agent Message: {message}")
                    try:
                        if isinstance(message, AIMessage):
                            if message.content:
                                if self.first_agent_chunk_time is None:
                                    self.first_agent_chunk_time = time.perf_counter()
                                    latency = self.first_agent_chunk_time - self.stt_end_time
                                    logger.info(f"⏱️ AGENT LATENCY (STT -> First LLM Token): {latency:.3f}s")

                                yield AgentChunkEvent(
                                    text=message.content
                                )
                                buffer.append(message.content)
                    except IndexError:
                        logger.error(f"IndexError: {message.content}")

                if buffer:
                    logger.info(f"Agent End: {''.join(buffer)}")
                    yield AgentEndEvent(text="".join(buffer))


    async def _tts_stream(
            self,
            event_stream: AsyncIterator[VoiceAgentEvent]
    ) -> AsyncIterator[VoiceAgentEvent]:
        
        tts = DeepgramTTS(_stream_sid=self.stream_sid)

        async def process_upstream():

            try:
                async for event in event_stream:
                    yield event
                    if event.type == "agent_chunk":
                        # Send text chunks to TTS as they arrive! (True streaming)
                        await tts.send_text(event.text)
                        
                    elif event.type == "agent_end":
                        await tts.flush()

                    elif event.type == "interrupt":
                        # BARGE-IN: User is speaking, so we shut up.
                        # 1. Tell Deepgram to stop producing audio.
                        
                        # 2. Throw away any text we were about to speak.
                        await tts.clear()

                    else:
                        pass

            except Exception as e:
                logger.error(f"Error while processing text: {e}")
                raise
            finally:
                await asyncio.sleep(0.2)
                await tts.close()

        

        try:
            first_audio_chunk = True
            async for events in merge_async_iters(process_upstream(), tts.receive_events()):
                if isinstance(events, TTSChunkEvent) and first_audio_chunk:
                    if self.first_agent_chunk_time:
                        tts_latency = time.perf_counter() - self.first_agent_chunk_time
                        logger.info(f"⏱️ TTS LATENCY (First LLM Token -> First Audio Byte): {tts_latency:.3f}s")
                    if self.stt_end_time:
                        total_latency = time.perf_counter() - self.stt_end_time
                        logger.info(f"⏱️ TOTAL PIPELINE LATENCY: {total_latency:.3f}s")
                    first_audio_chunk = False
                    
                yield events

        finally:
            await tts.close()

    def get_runnable(self):
        return (RunnableGenerator(self._stt_stream) | RunnableGenerator(self._agent_stream) | RunnableGenerator(self._tts_stream))

@app.websocket("/media")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("✅ WebSocket client connected")
    await websocket.accept()
    logger.info("🤝 WebSocket accepted")

    # Twilio sends a "connected" event first, then a "start" event
    stream_sid = None
    while True:
        message = await websocket.receive_text()
        data = json.loads(message)
        if data.get("event") == "start":
            stream_sid = data["start"]["streamSid"]
            
            logger.info(f"Stream started: {stream_sid}")
            break
        elif data.get("event") == "connected":
            logger.info("Received connected event, waiting for start...")
            continue
        else:
            logger.error(f"Expected start event, got: {data}")
            await websocket.close()
            return

    async def websocket_audio_stream() -> AsyncIterator[bytes]:
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                
                # We can ignore 'start' here since we already caught it
                if data["event"] == "media":
                    # Twilio sends base64 mulaw @ 8000Hz
                    audio_b64 = data["media"]["payload"]
                    mulaw_bytes = base64.b64decode(audio_b64)
                    yield mulaw_bytes
                            
                elif data["event"] == "stop":
                    logger.info("Twilio stopped the stream.")
                    break

                else:
                    logger.info(f"Ignored event: {data.get('event')}")
                    
            except WebSocketDisconnect:
                logger.info("Client disconnected gracefully")
                break
            except Exception as e:
                logger.error(f"Unexpected error receiving audio: {e}")
                break
            except RuntimeError as e:
                # Catch specific RuntimeErrors, although we've avoided it now
                logger.error(f"RuntimeError receiving audio: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error receiving audio: {e}")
                break

    voice_pipeline = VoicePipeline(stream_sid)
    
    output_stream = voice_pipeline.get_runnable().atransform(websocket_audio_stream())

    try:
        async for event in output_stream:
            if isinstance(event, TwilioEvent):
                t0 = time.perf_counter()
                await websocket.send_json(event_to_dict(event))
                t1 = time.perf_counter()
                
                # Only log if it took longer than 10ms to avoid spamming the console 
                # (since audio chunks are sent constantly)
                if (t1 - t0) > 0.01:
                    logger.info(f"⚡ OUTGOING NETWORK LATENCY (Send to Twilio): {(t1 - t0)*1000:.2f}ms")
    finally:
        pass

if __name__ == "__main__":
    uvicorn.run("main:app",
                host="0.0.0.0",
                port=8000,
                reload=settings.is_development)