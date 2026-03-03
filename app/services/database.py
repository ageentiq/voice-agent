"""MongoDB Atlas database service."""

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.models.call import CallSession, TranscriptEntry
from app.models.customer import CustomerAnalysis, CustomerRecord

logger = structlog.get_logger()

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect() -> None:
    """Connect to MongoDB Atlas."""
    global _client, _db
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    _db = _client[settings.mongodb_database]
    # Ensure indexes
    await _db.customers.create_index("phone", unique=True)
    await _db.call_logs.create_index("call_id", unique=True)
    await _db.call_logs.create_index("customer_phone")
    logger.info("Connected to MongoDB Atlas", database=settings.mongodb_database)


async def disconnect() -> None:
    """Disconnect from MongoDB Atlas."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
    logger.info("Disconnected from MongoDB Atlas")


def get_db() -> AsyncIOMotorDatabase:
    """Get database instance."""
    if _db is None:
        raise RuntimeError("Database not connected. Call connect() first.")
    return _db


async def save_call_log(session: CallSession) -> None:
    """Save or update a call log."""
    db = get_db()
    doc = session.model_dump(mode="json")
    await db.call_logs.update_one(
        {"call_id": session.call_id},
        {"$set": doc},
        upsert=True,
    )
    logger.info("Saved call log", call_id=session.call_id)


async def save_analysis(analysis: CustomerAnalysis) -> None:
    """Save analysis result and update customer record."""
    db = get_db()

    # Save analysis
    await db.analyses.insert_one(analysis.model_dump(mode="json"))

    # Update or create customer record
    await db.customers.update_one(
        {"phone": analysis.customer_phone},
        {
            "$set": {
                "name": analysis.customer_name,
                "updated_at": analysis.created_at,
                "last_call_at": analysis.created_at,
            },
            "$push": {"analyses": analysis.model_dump(mode="json")},
            "$inc": {"total_calls": 1},
            "$setOnInsert": {
                "created_at": analysis.created_at,
            },
        },
        upsert=True,
    )
    logger.info(
        "Saved analysis",
        call_id=analysis.call_id,
        lead_quality=analysis.lead_quality,
    )


async def get_customer(phone: str) -> dict | None:
    """Get customer record by phone number."""
    db = get_db()
    return await db.customers.find_one({"phone": phone}, {"_id": 0})


async def get_call_log(call_id: str) -> dict | None:
    """Get call log by call ID."""
    db = get_db()
    return await db.call_logs.find_one({"call_id": call_id}, {"_id": 0})


async def get_call_transcript(call_id: str) -> list[dict] | None:
    """Get call transcript."""
    db = get_db()
    doc = await db.call_logs.find_one(
        {"call_id": call_id},
        {"transcript": 1, "_id": 0},
    )
    if doc:
        return doc.get("transcript", [])
    return None
