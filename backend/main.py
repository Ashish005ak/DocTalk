from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router as api_router
from backend.api.websocket import router as ws_router
from backend.config import settings
from backend.cost.tracker import cost_tracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info(
        "DocTalk API starting  port=%d  default_domain=%s  llm_provider=%s",
        settings.ws_port,
        settings.default_domain,
        settings.llm_provider,
    )
    yield
    cost_tracker.finalize_all()
    logger.info("DocTalk API shutting down")


app = FastAPI(title="DocTalk API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)
