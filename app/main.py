from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.config import settings
from app.db.mongo import connect_to_mongo, close_mongo_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("VYNL Backend starting up...")
    await connect_to_mongo()
    yield
    logger.info("VYNL Backend shutting down...")
    await close_mongo_connection()

app = FastAPI(
    title="VYNL Backend",
    description="Backend service for VYNL music platform",
    version="1.0.0",
    lifespan=lifespan
)

origins = list({
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    settings.FRONTEND_URL.rstrip("/"),
})

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["traceparent", "X-CSRF-Token"],
)


from app.api import auth, activity, recommendations, library, playlists, history, onboarding, tracks, lyrics

api_routers = [
    auth.router,
    activity.router,
    recommendations.router,
    library.router,
    playlists.router,
    history.router,
    onboarding.router,
    tracks.router,
    lyrics.router,
]

for router in api_routers:
    # Mount on /v1 for frontend direct clients (AuthContext, eventBuffer)
    app.include_router(router, prefix="/v1")
    # Dual-mount on /api/v1 for reverse proxies and SearchUI
    app.include_router(router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "vynl-backend",
        "version": "1.0.0",
    }

