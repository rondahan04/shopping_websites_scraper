"""FastAPI application — exposes the CLI scraper over HTTP."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")

from api.jobs import job_store  # noqa: E402
from api.schemas import (  # noqa: E402
    JobProgressOut,
    JobStartRequest,
    JobStartResponse,
    JobStatusResponse,
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    yield
    try:
        from extraction.playwright_extract import shutdown_browser

        shutdown_browser()
    except Exception:
        pass


app = FastAPI(
    title="Shopping Websites Scraper API",
    description="Search Amazon, Best Buy, Walmart, and Newegg for product comparison data.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/search/jobs", response_model=JobStartResponse)
def start_search_job(body: JobStartRequest) -> JobStartResponse:
    """Start a background search. Poll GET /api/search/jobs/{job_id} for progress and results."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Please enter a product to search for.")
    job = job_store.create(query, rescrape_price_gaps=body.rescrape_price_gaps)
    return JobStartResponse(job_id=job.job_id)


@app.get("/api/search/jobs/{job_id}", response_model=JobStatusResponse)
def get_search_job(job_id: str) -> JobStatusResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="This search has expired. Please start again.")
    return JobStatusResponse(
        job_id=job.job_id,
        query=job.query,
        status=job.status,
        progress=JobProgressOut(
            percent=job.progress.percent,
            message=job.progress.message,
            stores_done=job.progress.stores_done,
            stores_total=job.progress.stores_total,
        ),
        result=job.result,
        error=job.error,
    )
