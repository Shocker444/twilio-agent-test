"""
Docstring for deepgram_stt

Connects to Deepgram's STT API for transcription.

Input: PCM 16-bit audio buffer (bytes)
Output: STT events (stt_chunk for partials, stt_output for final transcripts)

"""

import asyncio

from loguru import logger
import contextlib
import json
from typing import AsyncIterator, Optional, Any
from urllib.parse import urlencode

import base64
import websockets
from websockets.client import WebSocketClientProtocol
from settings import settings

from events import STTChunkEvent, STTEvent, STTOutputEvent, TTSChunkEvent, InterruptEvent


class DeepgramSTT:
    """Deepgram STT client for streaming transcription."""

    def __init__(
        self,
        _stream_sid: Any = None,
        sample_rate: int = 16000,
        format_turns: bool = True,
    ):
        self._stream_sid = _stream_sid
        self.sample_rate = sample_rate
        self.format_turns = format_turns
        self.api_key = settings.DEEPGRAM_API_KEY
        if not self.api_key:
            raise ValueError("Deepgram API key not set in settings.DEEPGRAM_API_KEY")
        self._ws: Optional[WebSocketClientProtocol] = None
        self._connection_signal = asyncio.Event()
        self._close_signal = asyncio.Event()

    async def receive_events(self) -> AsyncIterator[STTEvent]:
        logger.info("Deepgram STT: Starting to receive events...")
        while not self._close_signal.is_set():
            _, pending = await asyncio.wait([
                asyncio.create_task(self._close_signal.wait()),
                asyncio.create_task(self._connection_signal.wait())
            ],
            return_when=asyncio.FIRST_COMPLETED
            )

            with contextlib.suppress(asyncio.CancelledError):
                for task in pending:
                    task.cancel()

            if self._close_signal.is_set():
                break

            if self._ws and self._ws.close_code is None:
                self._connection_signal.clear()

                textchunk_buffer = []
                try:
                    async for raw_message in self._ws:
                        try:
                            message = json.loads(raw_message)
                            message_type = message.get('type')
                                
                            if message_type == "TurnInfo":
                                transcript = message.get("transcript", "")
                                turn = message.get("event", "")

                                if turn == "StartOfTurn":
                                    yield InterruptEvent(stream_sid=self._stream_sid)

                                elif turn == "EndOfTurn" and transcript:
                                    logger.info(f"Deepgram STT: Final Message: {message}")
                                    yield STTOutputEvent(text=transcript)

                                elif turn == "Update" and transcript:
                                    yield STTChunkEvent(text=transcript)

                                else:
                                    pass

                            elif message_type == "Metadata":
                                pass

                            else:
                                if "error" in message:
                                    logger.error(f"Deepgram error: {message['error']}")
                                    break
                        except json.JSONDecodeError as e:
                            logger.error(f"[DEBUG] Deepgram JSON decode error: {e}")
                            continue

                except websockets.exceptions.ConnectionClosed:
                    logger.info("Deepgram: Websocket connection closed.")

    async def send_audio(self, audio_data: bytes) -> None:
        ws = await self._ensure_connection()
        await ws.send(audio_data)

    async def close(self) -> None:
        if self._ws and self._ws.close_code is None:
            await self._ws.close()

        self._ws = None
        self._close_signal.set()

    async def _ensure_connection(self) -> WebSocketClientProtocol:
        if self._close_signal.is_set():
            raise RuntimeError("DeepgramSTT tried establishing a connection after it was closed")

        if self._ws and self._ws.close_code is None:
            return self._ws

        # Create a new connection
        params = {
            "model": "flux-general-en",   # Swapped back to Deepgram Flux
            "encoding": "mulaw",          # Accept native Twilio format
            "sample_rate": 8000,          # Twilio streams at 8kHz
            "eot_threshold": 0.75
        }
        url = f"wss://api.deepgram.com/v2/listen?{urlencode(params)}"
        headers = {"Authorization": f"Token {self.api_key}"}

        logger.info(f"Deepgram STT: Connecting to {url}")
        self._ws = await websockets.connect(url, additional_headers=headers)
        logger.info('Deepgram STT: WebSocket connection established.')

        self._connection_signal.set()
        return self._ws
    
class DeepgramTTS:
    """Deepgram TTS client for text to speech streaming"""

    def __init__(self,
        _stream_sid: Any = None,
        ):
        self.api_key = settings.DEEPGRAM_API_KEY
        if not self.api_key:
            raise ValueError("Deepgram API KEY not Found")
        
        self._stream_sid = _stream_sid
        self._ws: Optional[WebSocketClientProtocol] = None
        self._connection_signal = asyncio.Event()
        self._close_signal = asyncio.Event()

    async def receive_events(self) -> AsyncIterator[bytes]:
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
                    if isinstance(raw_message, bytes):
                        yield TTSChunkEvent(stream_sid=self._stream_sid,
                                            audio_data=raw_message)

                    elif isinstance(raw_message, str):
                        try:

                            meta = json.loads(raw_message)
                            logger.info(f"Deeggram audio metadata {meta}")
                            if "error" in meta:
                                logger.info(f"Deepgram TTS Error: {meta['error']}")

                        except json.JSONDecodeError as e:
                            pass
                    

            except websockets.exceptions.ConnectionClosed:
                logger.info("Connection closed")

            

    async def send_text(self, text_output: str) -> None:
        ws = await self._ensure_connection()
        await ws.send(json.dumps({"type": "Speak",
                                  "text": text_output}))
        
    async def flush(self) -> None:
        ws = await self._ensure_connection()
        await ws.send(json.dumps({"type": "Flush"}))

    async def clear(self) -> None:
        """
        Clears the internal buffer of text that has not yet been spoken.
        Useful for implementation of barge-in (interruption).
        """
        ws = await self._ensure_connection()
        await ws.send(json.dumps({"type": "Clear"}))

    async def close(self) -> None:
        if self._ws and self._ws.close_code is None:
            await self._ws.close()

        self._ws = None
        self._close_signal.set()

    async def _ensure_connection(self) -> WebSocketClientProtocol:
        if self._close_signal.is_set():
            raise RuntimeError("DeepgramSTT tried establishing a connection after it was closed")
        
        if self._ws and self._ws.close_code is None:
            return self._ws
        
        params = {
            "model":"aura-2-callista-en",
            "encoding":"mulaw",
            "sample_rate":"8000",
        }

        url = f"wss://api.deepgram.com/v1/speak?{urlencode(params)}"
        headers = {"Authorization": f"Token {self.api_key}"}
        self._ws = await websockets.connect(uri=url, additional_headers=headers)

        self._connection_signal.set()
        return self._ws





