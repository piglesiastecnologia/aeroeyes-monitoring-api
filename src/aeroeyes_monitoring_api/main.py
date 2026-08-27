from fastapi import FastAPI

from aeroeyes_monitoring_api.api.health import router as health_router

app = FastAPI(
    title="AeroEyes Monitoring API",
    description="Monitoring API for the AeroEyes Distributed Monitoring Platform.",
    version="0.1.0",
)

app.include_router(health_router)
