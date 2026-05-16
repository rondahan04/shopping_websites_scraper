"""Per API job: mirror terminal logs to run/logs/timelineofthelog/."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
TIMELINE_LOG_ROOT = _PROJECT_ROOT / "run" / "logs" / "timelineofthelog"

# Set for the duration of an API search job (including thread-pool workers via copy_context).
api_job_id: ContextVar[str | None] = ContextVar("api_job_id", default=None)


def _slugify(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s.strip().lower())
    return (s[:max_len].strip("-") or "query")


class _JobLogFilter(logging.Filter):
    def __init__(self, job_id: str) -> None:
        super().__init__()
        self._job_id = job_id

    def filter(self, record: logging.LogRecord) -> bool:
        return api_job_id.get() == self._job_id


@contextmanager
def timeline_log_session(job_id: str, query: str):
    """Attach a file handler for this job; write under run/logs/timelineofthelog/."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = TIMELINE_LOG_ROOT / f"{stamp}_{job_id[:8]}_{_slugify(query)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "timeline.log"

    (run_dir / "meta.txt").write_text(
        f"job_id={job_id}\nquery={query}\nstarted_utc={stamp}\nlog_file={log_path.name}\n",
        encoding="utf-8",
    )

    token = api_job_id.set(job_id)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    handler.addFilter(_JobLogFilter(job_id))

    root = logging.getLogger()
    prev_level = root.level
    if prev_level > logging.INFO:
        root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.info("=== API search job %s started: %r ===", job_id, query)
    logging.info("Timeline log file: %s", log_path)
    logger.info("Writing API timeline log to %s", log_path)

    status = "done"
    try:
        yield log_path
    except Exception:
        status = "error"
        raise
    finally:
        logging.info("=== API search job %s finished: %s ===", job_id, status)
        root.removeHandler(handler)
        handler.close()
        root.setLevel(prev_level)
        api_job_id.reset(token)


def job_worker_context():
    """Context snapshot for ThreadPoolExecutor workers (propagates api_job_id)."""
    return copy_context()
