import asyncio

from typing import AsyncIterator, Optional
import contextlib
import json
from urllib.parse import urlencode
from loguru import logger

import base64
import websockets
from websockets.client import WebSocketClientProtocol

from settings import settings

from events import TTSChunkEvent


class ElevenLabsTTS:
    def __init__(self,
                voice_id = "21m00Tcm4TlvDq8ikWAM",
                stability = 0.5,
                similarity_boost = 0.75,
    ):
        self.voice_id = voice_id
        self.stability = stability
        self.similarity_boost = similarity_boost
        self._ws: Optional[WebSocketClientProtocol] = None
        self._connection_signal = asyncio.Event()
        self._close_signal = asyncio.Event()

        self.api_key = settings.ELEVENLABS_API_KEY
        if not self.api_key:
            raise ValueError("ElevenLabs API key not set in settings.ELEVENLABS_API_KEY")

    async def receive_events(self) -> AsyncIterator[TTSChunkEvent]:
        while not self._close_signal.is_set():
            _, pending = await asyncio.wait([
                asyncio.create_task(self._close_signal.wait()),
                asyncio.create_task(self._connection_signal.wait())
            ],
            
            return_when=asyncio.FIRST_COMPLETED)

            with contextlib.suppress(asyncio.CancelledError):
                for task in pending:
                    task.cancel()
            
            if self._close_signal.is_set():
                break

            if self._ws and self._ws.close_code is None:
                self._connection_signal.clear()
                
                try:
                    async for raw_message in self._ws:
                        logger.info(f"ElevenLabs: Received raw message: {type(raw_message)} ---- {raw_message}")
                        if isinstance(raw_message, bytes):
                            yield TTSChunkEvent(
                                audio_data=raw_message,
                                is_final=True
                            )

                        else:
                            message = json.loads(raw_message)
                            if "audio" in message and message["audio"]:
                                yield TTSChunkEvent(
                                    audio_data=base64.b64decode(message["audio"]),
                                )

                except websockets.exceptions.ConnectionClosed:
                    logger.info("ElevenLabs: Websocket connection closed.")

    async def send_text(self, text_output: str):
        ws = await self._ensure_connection()

        payload = {
            "text": text_output,
            "flush": True
        }

        await ws.send(json.dumps(payload))

    async def close(self):
        if self._ws and self._ws.close_code is None:
            await self._ws.close()

        self._ws = None
        self._close_signal.is_set()
    
    async def _ensure_connection(self) -> WebSocketClientProtocol:
        if self._close_signal.is_set():
            raise RuntimeError("ElevenLabsTTS tried establishing a connection after it was closed")

        if self._ws and self._ws.close_code is None:
            return self._ws

        params = {
            "model":"eleven_multilingual_v2",
            "output_format": "ulaw_8000",
        }

        url = (f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream-input?"
                f"model_id={params['model']}&"
                f"output_format={params['output_format']}")

        bos_message = {
            "text": " ",
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost
            },
            "xi_api_key": self.api_key
        }

        try:
            self._ws = await websockets.connect(url)
        except Exception as e:
            logger.error(f"ElevenLabs: Failed to connect to websocket: {e}")
            raise
        
        try:
            await self._ws.send(json.dumps(bos_message))
        except Exception as e:
            logger.error(f"ElevenLabs: Failed to send BOS message: {e}")
            raise

        self._connection_signal.set()

        return self._ws
