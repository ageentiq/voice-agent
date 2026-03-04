"""Twilio telephony service - outbound calls and media streams."""

import asyncio
import base64
import json
import uuid
from datetime import datetime

import structlog
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.config import settings
from app.models.call import CallDirection, CallSession, CallStatus, TranscriptEntry
from app.services import database, rag
from app.services.agent import VoiceAgent
from app.services.stt import HamsaSTT
from app.services.tts import HamsaTTS

logger = structlog.get_logger()

# Active call sessions
_active_sessions: dict[str, "ActiveCall"] = {}
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrent_calls)
    return _semaphore


class ActiveCall:
    """Manages a single active voice call with STT/TTS/Agent pipeline."""

    def __init__(self, session: CallSession, agent: VoiceAgent):
        self.session = session
        self.agent = agent
        self.stt = HamsaSTT()
        self.tts = HamsaTTS()
        self._ws = None  # Twilio WebSocket
        self._stream_sid: str | None = None
        self._current_utterance = ""
        self._is_speaking = False  # True when TTS is playing
        self._speak_task: asyncio.Task | None = None
        self._utterance_lock = asyncio.Lock()

    async def start_stream(self, websocket, stream_sid: str) -> None:
        """Initialize the audio pipeline when Twilio media stream connects."""
        self._ws = websocket
        self._stream_sid = stream_sid
        self.session.status = CallStatus.IN_PROGRESS
        self.session.started_at = datetime.utcnow()

        # Start STT
        await self.stt.start(
            on_transcript=self._on_transcript,
            on_utterance_end=self._on_utterance_end,
        )

        # Send initial greeting
        greeting = await self.agent.get_greeting()
        if greeting:
            self.session.transcript.append(
                TranscriptEntry(role="agent", text=greeting)
            )
            await self._speak(greeting)

        logger.info("Call stream started", call_id=self.session.call_id)

    def _on_transcript(self, text: str, is_final: bool) -> None:
        """Handle STT transcript (called from Hamsa STT callback)."""
        if is_final:
            self._current_utterance += " " + text if self._current_utterance else text
        else:
            # Interim result - could use for barge-in detection
            if self._is_speaking and text.strip():
                # Customer is speaking while agent is talking - barge-in
                asyncio.create_task(self._handle_barge_in())

    def _on_utterance_end(self) -> None:
        """Handle end of customer utterance (silence detected)."""
        if self._current_utterance.strip():
            utterance = self._current_utterance.strip()
            self._current_utterance = ""
            asyncio.create_task(self._process_utterance(utterance))

    async def _handle_barge_in(self) -> None:
        """Handle customer interruption - stop TTS playback."""
        if self._is_speaking and self._ws:
            # Send clear message to Twilio to stop audio playback
            clear_msg = {
                "event": "clear",
                "streamSid": self._stream_sid,
            }
            try:
                await self._ws.send_json(clear_msg)
                self._is_speaking = False
                if self._speak_task and not self._speak_task.done():
                    self._speak_task.cancel()
                logger.debug("Barge-in: stopped TTS", call_id=self.session.call_id)
            except Exception as e:
                logger.error("Barge-in error", error=str(e))

    async def _process_utterance(self, text: str) -> None:
        """Process a complete customer utterance through the agent."""
        async with self._utterance_lock:
            logger.info("Processing utterance", text=text[:80], call_id=self.session.call_id)

            # Add to transcript
            self.session.transcript.append(
                TranscriptEntry(role="customer", text=text)
            )

            # Get agent response
            response = await self.agent.process_customer_input(text)

            if response:
                # Add to transcript
                self.session.transcript.append(
                    TranscriptEntry(role="agent", text=response)
                )

                # Speak the response
                await self._speak(response)

            # Check if conversation should end
            if self.agent.should_end_call:
                logger.info("Agent signals end of call", call_id=self.session.call_id)
                # Give time for the final message to play, then hang up
                await asyncio.sleep(2)
                await self.end_call()

            # Save call log periodically
            await database.save_call_log(self.session)

    async def _speak(self, text: str) -> None:
        """Convert text to speech and stream to Twilio."""
        if not self._ws or not self._stream_sid:
            return

        self._is_speaking = True

        try:
            async for audio_chunk in self.tts.synthesize_streaming(text):
                if not self._is_speaking:
                    break  # Interrupted by barge-in

                media_msg = {
                    "event": "media",
                    "streamSid": self._stream_sid,
                    "media": {
                        "payload": audio_chunk,
                    },
                }
                await self._ws.send_json(media_msg)

            # Mark audio sending complete
            mark_msg = {
                "event": "mark",
                "streamSid": self._stream_sid,
                "mark": {"name": "speech_done"},
            }
            await self._ws.send_json(mark_msg)

        except Exception as e:
            logger.error("TTS streaming error", error=str(e), call_id=self.session.call_id)
        finally:
            self._is_speaking = False

    async def handle_media(self, data: dict) -> None:
        """Handle incoming media (audio) from Twilio WebSocket."""
        payload = data.get("media", {}).get("payload", "")
        if payload:
            audio_bytes = base64.b64decode(payload)
            await self.stt.send_audio(audio_bytes)

    async def end_call(self) -> None:
        """End the call and clean up."""
        self.session.status = CallStatus.COMPLETED
        self.session.ended_at = datetime.utcnow()

        # Stop STT
        await self.stt.stop()

        # Close TTS client
        await self.tts.close()

        # Save final call log
        await database.save_call_log(self.session)

        # Remove from active sessions
        _active_sessions.pop(self.session.call_id, None)

        logger.info("Call ended", call_id=self.session.call_id)


async def initiate_call(
    customer_phone: str,
    customer_name: str,
    context: dict | None = None,
) -> CallSession:
    """Initiate an outbound call to a customer."""
    sem = _get_semaphore()

    if not sem._value:
        raise RuntimeError(
            f"Maximum concurrent calls ({settings.max_concurrent_calls}) reached"
        )

    await sem.acquire()

    try:
        call_id = str(uuid.uuid4())

        # Create call session
        session = CallSession(
            call_id=call_id,
            customer_phone=customer_phone,
            customer_name=customer_name,
            direction=CallDirection.OUTBOUND,
            status=CallStatus.QUEUED,
            metadata=context or {},
        )

        # Get project data for the agent
        project_data = await rag.get_project_data()

        # Create agent
        agent = VoiceAgent(
            call_id=call_id,
            customer_phone=customer_phone,
            customer_name=customer_name,
            project_data=project_data,
        )

        # Create active call handler
        active_call = ActiveCall(session=session, agent=agent)
        _active_sessions[call_id] = active_call

        # Initiate Twilio call
        twilio_client = TwilioClient(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
        )

        # TwiML URL that tells Twilio to connect a media stream
        stream_url = f"{settings.app_base_url}/webhooks/twilio/voice?call_id={call_id}"

        call = twilio_client.calls.create(
            to=customer_phone,
            from_=settings.twilio_phone_number,
            url=stream_url,
            status_callback=f"{settings.app_base_url}/webhooks/twilio/status?call_id={call_id}",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )

        session.twilio_call_sid = call.sid
        session.status = CallStatus.RINGING

        # Save initial call log
        await database.save_call_log(session)

        logger.info(
            "Call initiated",
            call_id=call_id,
            twilio_sid=call.sid,
            customer=customer_phone,
        )

        return session

    except Exception as e:
        sem.release()
        logger.error("Failed to initiate call", error=str(e))
        raise


def get_active_call(call_id: str) -> ActiveCall | None:
    """Get an active call by ID."""
    return _active_sessions.get(call_id)


def get_twiml_for_stream(call_id: str) -> str:
    """Generate TwiML that connects a media stream for a call."""
    response = VoiceResponse()
    connect = Connect()

    ws_url = f"{settings.app_base_url.replace('https://', 'wss://').replace('http://', 'ws://')}/ws/twilio/stream/{call_id}"
    connect.stream(url=ws_url)

    response.append(connect)
    return str(response)


def get_active_sessions_count() -> int:
    """Get number of active call sessions."""
    return len(_active_sessions)


def get_session_status(call_id: str) -> CallSession | None:
    """Get session status for a call."""
    active = _active_sessions.get(call_id)
    if active:
        return active.session
    return None
