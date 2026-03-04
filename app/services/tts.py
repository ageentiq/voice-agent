"""Hamsa streaming Text-to-Speech service (tryhamsa.com)."""

import asyncio
import base64
import io
from collections.abc import AsyncIterator

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()

HAMSA_API_URL = "https://api.tryhamsa.com/v1"


class HamsaTTS:
    """Streaming text-to-speech using Hamsa (Arabic-optimized)."""

    def __init__(self):
        self.api_key = settings.hamsa_api_key
        self.voice_id = settings.hamsa_voice_id
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def synthesize_streaming(self, text: str) -> AsyncIterator[bytes]:
        """Stream TTS audio chunks in mulaw 8kHz format for Twilio.

        Yields base64-encoded mulaw audio chunks ready to send to Twilio.
        Hamsa supports native mulaw 8kHz output, so no resampling needed.
        """
        client = await self._get_client()

        url = f"{HAMSA_API_URL}/jobs/text-to-speech"

        payload = {
            "text": text,
            "voice_id": self.voice_id,
            "model_id": "tts_realtime",
            "output_format": "ulaw_8000",
        }

        try:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()

                async for chunk in response.aiter_bytes(chunk_size=1600):
                    # 1600 bytes = 200ms at 8kHz mulaw (1 byte per sample)
                    # Already in mulaw format — just base64 encode for Twilio
                    yield base64.b64encode(chunk).decode("ascii")

        except httpx.HTTPStatusError as e:
            logger.error(
                "Hamsa TTS HTTP error",
                status=e.response.status_code,
                detail=str(e),
            )
            raise
        except Exception as e:
            logger.error("Hamsa TTS error", error=str(e))
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
