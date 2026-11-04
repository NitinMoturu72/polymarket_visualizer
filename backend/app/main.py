from fastapi import FastAPI
from app.routers import health, setup

app = FastAPI()

app.include_router(health.router)

app.include_router(setup.router)