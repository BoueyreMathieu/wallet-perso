from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import accounts, auth, categories, data, imports, merchants, tags, transactions
from app.db import get_sessionmaker
from app.seed import seed_all


@asynccontextmanager
async def lifespan(_: FastAPI):
    with get_sessionmaker()() as db:
        seed_all(db)
    yield


app = FastAPI(title="Wallet perso", version="0.4.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(imports.router)
app.include_router(transactions.router)
app.include_router(merchants.router)
app.include_router(data.router)
app.include_router(tags.router)


@app.get("/api/health", tags=["système"])
def health() -> dict:
    return {"status": "ok"}
