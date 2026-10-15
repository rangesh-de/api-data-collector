"""All settings in one place. Secrets come from environment variables (or a .env file), never from code."""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader so no extra package is needed. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class City:
    name: str
    latitude: float
    longitude: float


@dataclass
class Settings:
    db_path: Path = Path(os.getenv("COLLECTOR_DB", ROOT / "data" / "collector.db"))

    # Job postings (Adzuna)
    adzuna_app_id: str | None = os.getenv("ADZUNA_APP_ID")
    adzuna_app_key: str | None = os.getenv("ADZUNA_APP_KEY")
    job_searches: tuple[str, ...] = (
        "data analyst",
        "data engineer",
        "business intelligence analyst",
        "analytics engineer",
    )
    job_pages_per_search: int = 2        # 4 searches x 2 pages = 8 calls/day; free limit is 250/day
    job_results_per_page: int = 50
    job_max_days_old: int = 2

    # Weather (Open-Meteo, no key)
    cities: tuple[City, ...] = (
        City("Ames", 42.0308, -93.6319),
        City("Des Moines", 41.5868, -93.6250),
        City("Chicago", 41.8781, -87.6298),
    )

    # Reddit (optional: only runs when credentials are set)
    reddit_client_id: str | None = os.getenv("REDDIT_CLIENT_ID")
    reddit_client_secret: str | None = os.getenv("REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = os.getenv("REDDIT_USER_AGENT", "api-data-collector/1.0 (personal project)")
    subreddits: tuple[str, ...] = ("dataengineering", "datascience", "analytics")
    posts_per_subreddit: int = 100

    request_timeout: int = 30
    extra: dict = field(default_factory=dict)


settings = Settings()
