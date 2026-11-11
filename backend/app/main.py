from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import accounts, auth, categories
from app.db import get_sessionmaker
from app.seed import seed_categories


@asynccontextmanager
async def lifespan(_: FastAPI):
    with get_sessionmaker()() as db:
        seed_categories(db)
    yield


app = FastAPI(title="Wallet perso", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(categories.router)


@app.get("/api/health", tags=["système"])
def health() -> dict:
    return {"status": "ok"}
