"""FastAPI application - Voice Customer Service Agent for Osus Real Estate."""

import json
import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Form, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from app.config import settings
from app.models.call import (
    BatchCallRequest,
    CallStatus,
    CallStatusResponse,
    InitiateCallRequest,
)
from app.services import database, telephony

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Startup
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    await database.connect()
    logger.info("Voice Agent service started")

    yield

    # Shutdown
    await database.disconnect()
    logger.info("Voice Agent service stopped")


app = FastAPI(
    title="Osus Voice Agent",
    description="Voice-based customer service agent for Osus Real Estate (أُسُس العقارية)",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Health ──────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "active_calls": telephony.get_active_sessions_count(),
        "max_concurrent_calls": settings.max_concurrent_calls,
    }


# ─── Call Management API ─────────────────────────────────────────────────────


@app.post("/api/calls/initiate")
async def initiate_call(request: InitiateCallRequest):
    """Initiate a single outbound call. Used by n8n to trigger scheduled calls."""
    try:
        session = await telephony.initiate_call(
            customer_phone=request.customer_phone,
            customer_name=request.customer_name,
            context=request.context,
        )
        return {
            "call_id": session.call_id,
            "status": session.status.value,
            "twilio_call_sid": session.twilio_call_sid,
        }
    except RuntimeError as e:
        return JSONResponse(status_code=429, content={"error": str(e)})
    except Exception as e:
        logger.error("Failed to initiate call", error=str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/calls/batch")
async def batch_calls(request: BatchCallRequest):
    """Initiate multiple outbound calls. Respects concurrency limits."""
    results = []
    for customer in request.customers:
        try:
            session = await telephony.initiate_call(
                customer_phone=customer.customer_phone,
                customer_name=customer.customer_name,
                context=customer.context,
            )
            results.append({
                "customer_phone": customer.customer_phone,
                "call_id": session.call_id,
                "status": session.status.value,
            })
        except RuntimeError as e:
            results.append({
                "customer_phone": customer.customer_phone,
                "call_id": None,
                "status": "rejected",
                "error": str(e),
            })
        except Exception as e:
            results.append({
                "customer_phone": customer.customer_phone,
                "call_id": None,
                "status": "failed",
                "error": str(e),
            })

    return {"results": results}


@app.get("/api/calls/{call_id}/status")
async def get_call_status(call_id: str):
    """Get the current status of a call."""
    # Check active sessions first
    session = telephony.get_session_status(call_id)
    if session:
        duration = None
        if session.started_at and session.ended_at:
            duration = (session.ended_at - session.started_at).total_seconds()
        elif session.started_at:
            from datetime import datetime
            duration = (datetime.utcnow() - session.started_at).total_seconds()

        return CallStatusResponse(
            call_id=session.call_id,
            status=session.status,
            customer_phone=session.customer_phone,
            customer_name=session.customer_name,
            duration_seconds=duration,
            created_at=session.created_at,
        )

    # Check database for completed calls
    log = await database.get_call_log(call_id)
    if log:
        return log

    return JSONResponse(status_code=404, content={"error": "Call not found"})


@app.get("/api/calls/{call_id}/transcript")
async def get_call_transcript(call_id: str):
    """Get the transcript of a call."""
    # Check active session
    session = telephony.get_session_status(call_id)
    if session:
        return {"call_id": call_id, "transcript": [t.model_dump() for t in session.transcript]}

    # Check database
    transcript = await database.get_call_transcript(call_id)
    if transcript is not None:
        return {"call_id": call_id, "transcript": transcript}

    return JSONResponse(status_code=404, content={"error": "Call not found"})


# ─── Twilio Webhooks ─────────────────────────────────────────────────────────


@app.post("/webhooks/twilio/voice")
async def twilio_voice_webhook(call_id: str = Query(...)):
    """Twilio voice webhook - returns TwiML to connect media stream."""
    twiml = telephony.get_twiml_for_stream(call_id)
    return Response(content=twiml, media_type="application/xml")


@app.post("/webhooks/twilio/status")
async def twilio_status_webhook(
    request: Request,
    call_id: str = Query(...),
):
    """Twilio call status callback."""
    form = await request.form()
    call_status = form.get("CallStatus", "")

    logger.info(
        "Twilio status callback",
        call_id=call_id,
        status=call_status,
    )

    active_call = telephony.get_active_call(call_id)
    if not active_call:
        return {"status": "ok"}

    status_map = {
        "initiated": CallStatus.QUEUED,
        "ringing": CallStatus.RINGING,
        "in-progress": CallStatus.IN_PROGRESS,
        "completed": CallStatus.COMPLETED,
        "busy": CallStatus.BUSY,
        "no-answer": CallStatus.NO_ANSWER,
        "failed": CallStatus.FAILED,
        "canceled": CallStatus.CANCELED,
    }

    new_status = status_map.get(call_status)
    if new_status:
        active_call.session.status = new_status

        if new_status in (
            CallStatus.COMPLETED,
            CallStatus.BUSY,
            CallStatus.NO_ANSWER,
            CallStatus.FAILED,
            CallStatus.CANCELED,
        ):
            await active_call.end_call()

    return {"status": "ok"}


# ─── Twilio Media Stream WebSocket ───────────────────────────────────────────


@app.websocket("/ws/twilio/stream/{call_id}")
async def twilio_media_stream(websocket: WebSocket, call_id: str):
    """WebSocket endpoint for Twilio media streams (bidirectional audio)."""
    await websocket.accept()

    active_call = telephony.get_active_call(call_id)
    if not active_call:
        logger.error("No active call for stream", call_id=call_id)
        await websocket.close()
        return

    stream_sid = None

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "connected":
                logger.info("Twilio stream connected", call_id=call_id)

            elif event == "start":
                stream_sid = data.get("start", {}).get("streamSid")
                logger.info("Twilio stream started", call_id=call_id, stream_sid=stream_sid)
                await active_call.start_stream(websocket, stream_sid)

            elif event == "media":
                await active_call.handle_media(data)

            elif event == "mark":
                # TTS playback mark reached
                mark_name = data.get("mark", {}).get("name")
                logger.debug("Stream mark", call_id=call_id, mark=mark_name)

            elif event == "stop":
                logger.info("Twilio stream stopped", call_id=call_id)
                break

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected", call_id=call_id)
    except Exception as e:
        logger.error("WebSocket error", call_id=call_id, error=str(e))
    finally:
        if active_call:
            await active_call.end_call()


# ─── Knowledge Base Management ───────────────────────────────────────────────


@app.post("/api/knowledge-base/ingest")
async def ingest_document(
    text: str = Form(None),
    source: str = Form("manual"),
    file_path: str = Form(None),
):
    """Ingest a document into the knowledge base."""
    from app.services import rag

    if file_path:
        if file_path.lower().endswith(".pdf"):
            count = await rag.ingest_pdf(file_path)
        else:
            with open(file_path) as f:
                text = f.read()
            count = await rag.ingest_text(text, source=source)
    elif text:
        count = await rag.ingest_text(text, source=source)
    else:
        return JSONResponse(
            status_code=400,
            content={"error": "Provide either 'text' or 'file_path'"},
        )

    return {"status": "ok", "chunks_ingested": count, "source": source}


@app.post("/api/knowledge-base/search")
async def search_knowledge_base(query: str = Form(...)):
    """Search the knowledge base."""
    from app.services import rag

    results = await rag.search(query)
    return {"query": query, "results": results}
