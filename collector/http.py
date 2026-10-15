"""One shared HTTP session with automatic retries, so a single network hiccup doesn't fail a run."""
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# urllib3 logs every retry with the full URL, which would include API keys. Keep it quiet.
logging.getLogger("urllib3").setLevel(logging.ERROR)


def make_session(user_agent: str = "api-data-collector/1.0") -> requests.Session:
    retry = Retry(
        total=4,
        backoff_factor=2,                         # waits 2s, 4s, 8s ... between attempts
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = user_agent
    return session
