"""FastAPI application factory for the Variant Viewer API.

Configures CORS for local development and mounts a ``/api/health``
liveness probe.  Routes are added in subsequent PRs.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import health, patients, samples, variants, config

app = FastAPI(
    title="Variant Viewer API",
    description="Genomic variant review and classification API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(patients.router)
app.include_router(samples.router)
app.include_router(variants.router)
app.include_router(config.router)
