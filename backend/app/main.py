from fastapi import FastAPI
from app.routers import health, setup, sync, trades

app = FastAPI()

app.include_router(health.router)

app.include_router(setup.router)

app.include_router(sync.router)

app.include_router(trades.router)