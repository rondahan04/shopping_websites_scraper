"""In-memory search jobs with live progress (for the web UI)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from api.progress import (
    message_all_stores_started,
    message_done,
    message_recheck_start,
    message_recheck_store,
    message_starting,
    message_store_finished,
    message_wrapping_up,
    friendly_store,
)
from api.schemas import SearchResponse, build_search_response
from api.service import scrape_query_with_progress
from api.timeline_log import timeline_log_session
from models import ProductRow, row_has_scraped_price
from sites import ALL_ADAPTERS

SITE_ORDER = [a.display_name for a in ALL_ADAPTERS]
STORES_TOTAL = len(ALL_ADAPTERS)

JobStatus = Literal["running", "done", "error"]


@dataclass
class JobProgress:
    percent: int
    message: str
    stores_done: list[str] = field(default_factory=list)
    stores_total: int = 4


@dataclass
class SearchJob:
    job_id: str
    query: str
    status: JobStatus
    progress: JobProgress
    result: SearchResponse | None = None
    partial_rows: dict[str, ProductRow] = field(default_factory=dict)
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, SearchJob] = {}
        self._lock = threading.Lock()

    def create(self, query: str, *, rescrape_price_gaps: bool) -> SearchJob:
        job_id = uuid.uuid4().hex
        job = SearchJob(
            job_id=job_id,
            query=query.strip(),
            status="running",
            progress=JobProgress(
                percent=0,
                message=message_starting(),
                stores_total=STORES_TOTAL,
            ),
        )
        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, query.strip(), rescrape_price_gaps),
            daemon=True,
        )
        thread.start()
        return job

    def get(self, job_id: str) -> SearchJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _update(self, job_id: str, **kwargs: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in kwargs.items():
                setattr(job, key, value)

    def _set_progress(
        self,
        job_id: str,
        *,
        percent: int,
        message: str,
        stores_done: list[str] | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.progress.percent = max(0, min(100, percent))
            job.progress.message = message
            if stores_done is not None:
                job.progress.stores_done = stores_done

    def _publish_partial(self, job_id: str, query: str, rows_by_site: dict[str, ProductRow]) -> None:
        ordered = [rows_by_site[name] for name in SITE_ORDER if name in rows_by_site]
        if not ordered:
            return
        partial = build_search_response(query, ordered, total_sites=STORES_TOTAL)
        self._update(job_id, result=partial, partial_rows=rows_by_site)

    def _run_job(self, job_id: str, query: str, rescrape_price_gaps: bool) -> None:
        stores_done: list[str] = []
        rows_by_site: dict[str, ProductRow] = {}
        total = STORES_TOTAL

        def on_first_pass_begin() -> None:
            self._set_progress(
                job_id,
                percent=5,
                message=message_all_stores_started(),
                stores_done=[],
            )

        def on_site_finished(website: str, row: ProductRow) -> None:
            rows_by_site[website] = row
            self._publish_partial(job_id, query, rows_by_site)
            name = friendly_store(website)
            if name not in stores_done:
                stores_done.append(name)
            pct = 10 + int((len(stores_done) / total) * 70)
            self._set_progress(
                job_id,
                percent=pct,
                message=message_store_finished(website, got_price=row_has_scraped_price(row)),
                stores_done=list(stores_done),
            )

        def on_recheck_begin(sites: list[str]) -> None:
            self._set_progress(
                job_id,
                percent=82,
                message=message_recheck_start(sites),
                stores_done=list(stores_done),
            )

        def on_recheck_site(website: str, row: ProductRow) -> None:
            rows_by_site[website] = row
            self._publish_partial(job_id, query, rows_by_site)
            self._set_progress(
                job_id,
                percent=88,
                message=message_recheck_store(website),
                stores_done=list(stores_done),
            )

        def on_wrapping_up() -> None:
            self._set_progress(
                job_id,
                percent=95,
                message=message_wrapping_up(),
                stores_done=list(stores_done),
            )

        try:
            with timeline_log_session(job_id, query):
                rows = scrape_query_with_progress(
                    query,
                    rescrape_price_gaps=rescrape_price_gaps,
                    on_first_pass_begin=on_first_pass_begin,
                    on_site_finished=on_site_finished,
                    on_recheck_begin=on_recheck_begin,
                    on_recheck_site=on_recheck_site,
                    on_wrapping_up=on_wrapping_up,
                )
            response = build_search_response(query, rows, total_sites=STORES_TOTAL)
            self._set_progress(
                job_id,
                percent=100,
                message=message_done(response.success_count, response.total_sites),
                stores_done=list(stores_done),
            )
            self._update(job_id, status="done", result=response)
        except Exception as e:
            self._update(
                job_id,
                status="error",
                error="Something went wrong while searching. Please try again.",
            )
            self._set_progress(
                job_id,
                percent=100,
                message="Search stopped because of a problem. Please try again.",
                stores_done=list(stores_done),
            )
            # Keep real error in logs
            import logging

            logging.getLogger(__name__).exception("Job %s failed: %s", job_id, e)


job_store = JobStore()
