# Voice Customer Service Agent - Implementation Plan

## Overview
Build a voice-based customer service agent for Osus Real Estate (أُسُس العقارية) that makes scheduled outbound calls to customers in Saudi Arabic, qualifies leads by collecting required information, and takes actions (analysis, CRM updates).

## Architecture

```
┌──────────────┐     ┌─────────────────────────────────────────────────┐
│  n8n / API   │────▶│              FastAPI Application                │
│  (trigger)   │     │                                                 │
└──────────────┘     │  ┌───────────┐     ┌──────────────────────┐    │
                     │  │ Twilio    │◀───▶│  Call Session Manager │    │
┌──────────────┐     │  │ Telephony │     │  (async, concurrent) │    │
│   Twilio     │◀───▶│  └───────────┘     └──────────┬───────────┘    │
│  (phone)     │     │                               │               │
└──────────────┘     │       ┌───────────────────────┼──────┐        │
                     │       ▼                       ▼      ▼        │
                     │  ┌─────────┐  ┌──────────────────┐ ┌──────┐  │
                     │  │Deepgram │  │  Anthropic Claude │ │Eleven│  │
                     │  │  STT    │─▶│  Agent + Tools    │▶│Labs  │  │
                     │  │(stream) │  │                  │ │ TTS  │  │
                     │  └─────────┘  │  - RAG search    │ │(strm)│  │
                     │               │  - analysis      │ └──────┘  │
                     │               │  - CRM update    │           │
                     │               └───────┬──────────┘           │
                     │                ┌──────┼──────┐               │
                     │                ▼      ▼      ▼               │
                     │           ┌───────┐┌──────┐┌──────────┐     │
                     │           │ChromaDB││Mongo ││ Twilio   │     │
                     │           │ (RAG)  ││Atlas ││ (stream) │     │
                     │           └───────┘└──────┘└──────────┘     │
                     └─────────────────────────────────────────────┘
```

## Tech Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI (async, WebSocket support)
- **LLM**: Anthropic Claude (via anthropic Python SDK) with tool use
- **Telephony**: Twilio Programmable Voice + Media Streams (WebSocket)
- **STT**: Deepgram (real-time streaming, Arabic support)
- **TTS**: Hamsa (high-quality Arabic voices, streaming)
- **RAG**: ChromaDB (vector DB) + sentence-transformers (multilingual embeddings)
- **Database**: MongoDB Atlas (customer data, call logs, analysis)
- **Deployment**: Docker + Docker Compose

## Project Structure

```
voice-agent/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Settings (pydantic-settings)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── call.py             # Call session data models
│   │   └── customer.py         # Customer & analysis models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── telephony.py        # Twilio: make calls, handle streams
│   │   ├── stt.py              # Deepgram streaming STT
│   │   ├── tts.py              # Hamsa streaming TTS
│   │   ├── agent.py            # Claude agent with conversation + tools
│   │   ├── rag.py              # RAG retrieval (ChromaDB + embeddings)
│   │   └── database.py         # MongoDB Atlas operations
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── analysis.py         # Lead analysis/qualification tool
│   │   ├── knowledge_base.py   # RAG search tool for Claude
│   │   └── crm.py              # CRM/MongoDB update tool
│   └── prompts/
│       ├── __init__.py
│       └── sales_agent.py      # System prompt (Arabic, adapted for voice)
├── knowledge_base/
│   └── .gitkeep                # Place PDF/text documents here
├── scripts/
│   ├── ingest_documents.py     # Ingest docs into ChromaDB
│   └── test_call.py            # Test outbound call
└── tests/
    ├── __init__.py
    ├── test_agent.py
    └── test_rag.py
```

## Implementation Steps

### Phase 1: Project Setup & Configuration
1. Initialize Python project with requirements.txt
2. Create .env.example with all required API keys
3. Set up FastAPI app structure
4. Create pydantic config/settings module
5. Set up Docker + Docker Compose (FastAPI + ChromaDB)

### Phase 2: Core Agent (Claude + Tools)
6. Adapt the WhatsApp text prompt for voice conversations
   - Shorter responses (voice-friendly)
   - Add voice-specific instructions (pauses, confirmations)
   - Keep all business logic, qualification criteria, and safety rules
7. Implement Claude agent service using anthropic SDK
   - System prompt with voice adaptations
   - Conversation history management per call session
   - Tool use integration
8. Implement tools:
   - `analysis` tool: Qualify leads, classify customer interest
   - `search_knowledge_base` tool: Query RAG for project info
   - `update_crm` tool: Save customer data to MongoDB

### Phase 3: RAG / Knowledge Base
9. Set up ChromaDB with multilingual embeddings (intfloat/multilingual-e5-large)
10. Create document ingestion script (PDF + text support)
11. Implement RAG retrieval service with Arabic-aware chunking
12. Wire RAG as a Claude tool

### Phase 4: Voice Pipeline (STT + TTS)
13. Implement Deepgram streaming STT service
    - WebSocket connection for real-time transcription
    - Arabic language (ar) configuration
    - Endpointing / silence detection for turn-taking
14. Implement Hamsa streaming TTS service
    - Arabic voice selection/configuration
    - Streaming audio generation for low latency
    - Audio format conversion (mulaw 8kHz for Twilio)

### Phase 5: Telephony (Twilio)
15. Implement Twilio outbound call service
    - Initiate calls with TwiML / Media Streams
    - WebSocket handler for bidirectional audio streaming
16. Implement call session manager
    - Track active calls (async, concurrent)
    - Per-call state: conversation history, collected info, call status
    - Handle call events (answered, ended, failed, no-answer)
17. Build the real-time audio pipeline:
    - Twilio WebSocket → Deepgram STT (streaming)
    - Customer text → Claude agent → Response text
    - Response text → Hamsa TTS (streaming) → Twilio WebSocket

### Phase 6: Database & CRM
18. Set up MongoDB Atlas connection (motor async driver)
19. Implement data models and CRUD operations:
    - Customer records
    - Call logs (with full transcript)
    - Analysis results (lead qualification)
20. Implement the CRM update tool

### Phase 7: API Endpoints
21. `POST /api/calls/initiate` - Trigger a single outbound call
    - Input: customer phone, name, any context
    - Used by n8n to trigger scheduled calls
22. `POST /api/calls/batch` - Trigger multiple calls
    - Input: list of customers
    - Respects concurrency limits
23. `GET /api/calls/{call_id}/status` - Check call status
24. `GET /api/calls/{call_id}/transcript` - Get call transcript
25. Twilio webhook endpoints:
    - `POST /webhooks/twilio/voice` - Call status callbacks
    - `WebSocket /ws/twilio/stream/{call_id}` - Media stream

### Phase 8: Docker & Deployment
26. Create Dockerfile (Python app)
27. Create docker-compose.yml (app + ChromaDB)
28. Environment configuration and health checks

## Call Flow (Detailed)

1. **n8n triggers** `POST /api/calls/initiate` with customer info
2. **FastAPI** creates a call session, stores in memory
3. **Twilio** initiates outbound call to customer
4. Customer **answers** → Twilio connects **Media Stream** WebSocket
5. **Agent speaks first** (greeting adapted from the WhatsApp opener):
   "السلام عليكم، حياك الله [اسم العميل]، معكم مُبايع من شركة أُسُس العقارية..."
6. **TTS** converts greeting to audio → streams to Twilio → customer hears it
7. **Customer speaks** → audio streams via Twilio WebSocket
8. **Deepgram STT** transcribes in real-time
9. **Silence detected** (end of utterance) → text sent to **Claude agent**
10. Claude processes with conversation history, may call tools:
    - `search_knowledge_base`: retrieve project info from RAG
    - `update_crm`: save collected info
    - `analysis`: qualify lead (at conversation end)
11. Claude returns response text
12. **Hamsa TTS** streams audio → Twilio → customer
13. Repeat 7-12 until conversation ends
14. On end: `analysis` tool called, results saved to MongoDB, call logged

## Key Design Decisions

- **Streaming everywhere**: STT and TTS use streaming for minimal latency
- **Async architecture**: FastAPI + asyncio for concurrent calls
- **Conversation state per call**: Each active call has its own Claude conversation history
- **Turn-taking via silence detection**: Deepgram's endpointing detects when customer stops speaking
- **Barge-in support**: If customer speaks while TTS is playing, stop TTS and process new input
- **Arabic-first**: All prompts, embeddings, and voice config optimized for Saudi Arabic

## Required API Keys / Services
- `ANTHROPIC_API_KEY` - Claude API
- `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` - Twilio
- `TWILIO_PHONE_NUMBER` - Outbound caller ID (Saudi or international)
- `DEEPGRAM_API_KEY` - Speech-to-Text
- `HAMSA_API_KEY` - Hamsa Text-to-Speech (tryhamsa.com)
- `HAMSA_VOICE_ID` - Arabic voice ID
- `MONGODB_URI` - MongoDB Atlas connection string
- `APP_BASE_URL` - Public URL for Twilio webhooks (use ngrok for dev)
