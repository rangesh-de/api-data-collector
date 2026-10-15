"""
Runs each source independently. If one API is down, the others still load,
and every attempt is recorded in run_log (success, failed or skipped).
"""
import logging
import re
import time

from collector.config import Settings
from collector.db import connect, now_utc
from collector.http import make_session
from collector.sources import ALL_SOURCES

log = logging.getLogger("collector")
SECRET_PARAM = re.compile(r"(app_id|app_key|client_secret|access_token)=[^&\s'\"]+", re.IGNORECASE)


def redact(text: str, settings: Settings) -> str:
    """Error messages often contain the request URL. Strip keys so they never reach logs."""
    text = SECRET_PARAM.sub(r"\1=***", text)
    for secret in (settings.adzuna_app_id, settings.adzuna_app_key,
                   settings.reddit_client_id, settings.reddit_client_secret):
        if secret:
            text = text.replace(secret, "***")
    return text


def run(settings: Settings, only: list[str] | None = None) -> dict[str, str]:
    session = make_session(settings.reddit_user_agent)
    results = {}
    with connect(settings.db_path) as conn:
        for source_cls in ALL_SOURCES:
            source = source_cls(settings, session)
            if only and source.name not in only:
                continue

            started = now_utc()
            run_id = conn.execute(
                "INSERT INTO run_log (source, started_at, status) VALUES (?, ?, 'running')",
                (source.name, started),
            ).lastrowid
            conn.commit()

            ready, reason = source.is_configured()
            if not ready:
                status, rows, message = "skipped", 0, reason
            else:
                t0 = time.monotonic()
                try:
                    rows = source.run(conn)
                    status, message = "success", f"{time.monotonic() - t0:.1f}s"
                except Exception as err:                       # one source failing must not stop the rest
                    conn.rollback()
                    status, rows, message = "failed", 0, redact(f"{type(err).__name__}: {err}", settings)[:500]

            conn.execute(
                "UPDATE run_log SET finished_at = ?, status = ?, rows_loaded = ?, message = ? WHERE run_id = ?",
                (now_utc(), status, rows, message, run_id),
            )
            conn.commit()
            log.info("%-8s %-8s %5d rows  %s", source.name, status, rows, message)
            results[source.name] = status
    return results
