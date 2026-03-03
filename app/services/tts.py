"""ElevenLabs streaming Text-to-Speech service."""

import asyncio
import audioop
import base64
import io
from collections.abc import AsyncIterator

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


class ElevenLabsTTS:
    """Streaming text-to-speech using ElevenLabs."""

    def __init__(self):
        self.api_key = settings.elevenlabs_api_key
        self.voice_id = settings.elevenlabs_voice_id
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def synthesize_streaming(self, text: str) -> AsyncIterator[bytes]:
        """Stream TTS audio chunks in mulaw 8kHz format for Twilio.

        Yields base64-encoded mulaw audio chunks ready to send to Twilio.
        """
        client = await self._get_client()

        url = f"{ELEVENLABS_API_URL}/text-to-speech/{self.voice_id}/stream"

        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.6,
                "similarity_boost": 0.8,
                "style": 0.3,
            },
            "output_format": "pcm_24000",
        }

        try:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                pcm_buffer = b""

                async for chunk in response.aiter_bytes(chunk_size=4800):
                    pcm_buffer += chunk

                    # Process in chunks of 4800 bytes (100ms at 24kHz 16-bit mono)
                    while len(pcm_buffer) >= 4800:
                        pcm_chunk = pcm_buffer[:4800]
                        pcm_buffer = pcm_buffer[4800:]

                        # Downsample from 24kHz to 8kHz
                        downsampled = audioop.ratecv(
                            pcm_chunk, 2, 1, 24000, 8000, None
                        )[0]

                        # Convert PCM to mulaw
                        mulaw_chunk = audioop.lin2ulaw(downsampled, 2)

                        # Base64 encode for Twilio
                        yield base64.b64encode(mulaw_chunk).decode("ascii")

                # Process remaining buffer
                if pcm_buffer:
                    downsampled = audioop.ratecv(
                        pcm_buffer, 2, 1, 24000, 8000, None
                    )[0]
                    mulaw_chunk = audioop.lin2ulaw(downsampled, 2)
                    yield base64.b64encode(mulaw_chunk).decode("ascii")

        except httpx.HTTPStatusError as e:
            logger.error("ElevenLabs TTS HTTP error", status=e.response.status_code, detail=str(e))
            raise
        except Exception as e:
            logger.error("ElevenLabs TTS error", error=str(e))
            raise

    async def synthesize_full(self, text: str) -> str:
        """Synthesize full audio and return as base64 mulaw.

        Returns a single base64 string of the complete audio.
        """
        chunks = []
        async for chunk in self.synthesize_streaming(text):
            chunks.append(chunk)
        return "".join(chunks)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
