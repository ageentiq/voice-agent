"""Hamsa streaming Speech-to-Text service (tryhamsa.com)."""

import asyncio
import json
from collections.abc import Callable

import structlog
import websockets

from app.config import settings

logger = structlog.get_logger()

HAMSA_STT_WS_URL = "wss://api.tryhamsa.com/v1/realtime/stt"


class HamsaSTT:
    """Streaming speech-to-text using Hamsa WebSocket API."""

    def __init__(self):
        self.api_key = settings.hamsa_api_key
        self._ws = None
        self._receive_task: asyncio.Task | None = None
        self._on_transcript: Callable[[str, bool], None] | None = None
        self._on_utterance_end: Callable[[], None] | None = None
        self._running = False

    async def start(
        self,
        on_transcript: Callable[[str, bool], None],
        on_utterance_end: Callable[[], None] | None = None,
    ) -> None:
        """Start a streaming STT session.

        Args:
            on_transcript: Callback(text, is_final) called for each transcript.
            on_utterance_end: Callback when an utterance ends (silence detected).
        """
        self._on_transcript = on_transcript
        self._on_utterance_end = on_utterance_end
        self._running = True

        # Connect to Hamsa real-time STT WebSocket
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        self._ws = await websockets.connect(
            HAMSA_STT_WS_URL,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=10,
        )

        # Send initial configuration
        config = {
            "type": "config",
            "encoding": "mulaw",
            "sample_rate": 8000,
            "channels": 1,
            "language": "ar",
            "model": "stt_realtime",
            "interim_results": True,
            "punctuate": True,
            "utterance_end_ms": 1500,  # 1.5s silence = end of utterance
        }
        await self._ws.send(json.dumps(config))

        # Start background task to receive transcripts
        self._receive_task = asyncio.create_task(self._receive_loop())

        logger.info("Hamsa STT session started")

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data to Hamsa for transcription.

        Audio should be mulaw 8kHz mono (raw bytes from Twilio).
        """
        if self._ws and self._running:
            try:
                await self._ws.send(audio_data)
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Hamsa STT WebSocket closed, cannot send audio")

    async def stop(self) -> None:
        """Stop the STT session."""
        self._running = False

        if self._ws:
            try:
                # Send end-of-stream signal
                await self._ws.send(json.dumps({"type": "stop"}))
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        logger.info("Hamsa STT session stopped")

    async def _receive_loop(self) -> None:
        """Background loop to receive transcript events from Hamsa."""
        try:
            async for message in self._ws:
                if not self._running:
                    break

                try:
                    data = json.loads(message)
                    event_type = data.get("type", "")

                    if event_type == "transcript":
                        transcript = data.get("text", "")
                        if not transcript:
                            continue

                        is_final = data.get("is_final", False)

                        if self._on_transcript:
                            self._on_transcript(transcript, is_final)

                        logger.debug(
                            "STT transcript",
                            text=transcript[:50],
                            is_final=is_final,
                        )

                    elif event_type == "utterance_end":
                        if self._on_utterance_end:
                            self._on_utterance_end()
                        logger.debug("Utterance end detected")

                    elif event_type == "error":
                        logger.error(
                            "Hamsa STT error",
                            error=data.get("message", "Unknown error"),
                        )

                except json.JSONDecodeError:
                    logger.warning("Non-JSON message from Hamsa STT")

        except websockets.exceptions.ConnectionClosed as e:
            if self._running:
                logger.error("Hamsa STT WebSocket closed unexpectedly", code=e.code)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self._running:
                logger.error("Hamsa STT receive error", error=str(e))
