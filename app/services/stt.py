"""Deepgram streaming Speech-to-Text service."""

import asyncio
from collections.abc import AsyncIterator, Callable

import structlog
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveOptions,
    LiveTranscriptionEvents,
)

from app.config import settings

logger = structlog.get_logger()


class DeepgramSTT:
    """Streaming speech-to-text using Deepgram."""

    def __init__(self):
        config = DeepgramClientOptions(api_key=settings.deepgram_api_key)
        self.client = DeepgramClient(config=config)
        self._connection = None
        self._on_transcript: Callable[[str, bool], None] | None = None
        self._on_utterance_end: Callable[[], None] | None = None

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

        self._connection = self.client.listen.asyncwebsocket.v("1")

        # Register event handlers
        self._connection.on(LiveTranscriptionEvents.Transcript, self._handle_transcript)
        self._connection.on(LiveTranscriptionEvents.UtteranceEnd, self._handle_utterance_end)
        self._connection.on(LiveTranscriptionEvents.Error, self._handle_error)

        options = LiveOptions(
            language="ar",  # Arabic
            model="nova-2",
            encoding="mulaw",
            sample_rate=8000,  # Twilio's audio format
            channels=1,
            punctuate=True,
            interim_results=True,
            utterance_end_ms=1500,  # 1.5s silence = end of utterance
            vad_events=True,
            endpointing=300,
            smart_format=True,
        )

        started = await self._connection.start(options)
        if not started:
            raise RuntimeError("Failed to start Deepgram connection")

        logger.info("Deepgram STT session started")

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data to Deepgram for transcription."""
        if self._connection:
            await self._connection.send(audio_data)

    async def stop(self) -> None:
        """Stop the STT session."""
        if self._connection:
            await self._connection.finish()
            self._connection = None
        logger.info("Deepgram STT session stopped")

    async def _handle_transcript(self, _connection, result, **kwargs) -> None:
        """Handle incoming transcript from Deepgram."""
        try:
            transcript = result.channel.alternatives[0].transcript
            if not transcript:
                return

            is_final = result.is_final
            if self._on_transcript:
                self._on_transcript(transcript, is_final)

            logger.debug(
                "STT transcript",
                text=transcript[:50],
                is_final=is_final,
            )
        except (IndexError, AttributeError) as e:
            logger.error("Error parsing Deepgram transcript", error=str(e))

    async def _handle_utterance_end(self, _connection, result, **kwargs) -> None:
        """Handle utterance end event (silence detected)."""
        if self._on_utterance_end:
            self._on_utterance_end()
        logger.debug("Utterance end detected")

    async def _handle_error(self, _connection, error, **kwargs) -> None:
        """Handle Deepgram errors."""
        logger.error("Deepgram STT error", error=str(error))
