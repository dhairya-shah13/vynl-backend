import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

logger = logging.getLogger(__name__)

class Database:
    client: AsyncIOMotorClient = None
    db = None
    audio_db = None

db_manager = Database()

async def init_indexes():
    """Ensure indexes for rapid lookups and constraints across collections."""
    if db_manager.db is None:
        return
    try:
        await db_manager.db.users.create_index("user_id", unique=True)
        await db_manager.db.users.create_index("google_sub", unique=True, sparse=True)
        await db_manager.db.users.create_index("email", unique=True, sparse=True)
        await db_manager.db.user_profiles.create_index("user_id", unique=True)
        await db_manager.db.playlists.create_index([("user_id", 1), ("playlist_id", 1)], unique=True)
        await db_manager.db.listening_history.create_index([("user_id", 1), ("played_at", -1)])
        await db_manager.db.listening_history.create_index([("user_id", 1), ("track_id", 1)])
        await db_manager.db.library.create_index([("user_id", 1), ("track_id", 1)], unique=True)
        await db_manager.db.lyrics_cache.create_index("cache_key", unique=True)
        await db_manager.db.lyrics_cache.create_index("expire_at", expireAfterSeconds=0)
        logger.info("MongoDB indexes verified successfully.")
    except Exception as exc:
        logger.warning("Index creation deferred or failed (MongoDB might be connecting): %s", exc)

async def connect_to_mongo():
    logger.info("Connecting to MongoDB at %s...", settings.MONGO_URI)
    db_manager.client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
    db_manager.db = db_manager.client[settings.MONGO_DB]
    db_manager.audio_db = db_manager.client["vynl_audio"]
    await init_indexes()

async def close_mongo_connection():
    if db_manager.client:
        logger.info("Closing MongoDB connection pool.")
        db_manager.client.close()
        db_manager.client = None
        db_manager.db = None
        db_manager.audio_db = None

def get_db():
    return db_manager.db

def get_audio_db():
    return db_manager.audio_db

