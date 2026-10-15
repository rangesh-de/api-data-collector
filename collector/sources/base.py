"""
Every source follows the same three steps: extract -> transform -> load.

Adding a new API means writing one new subclass. The runner, logging,
retries and scheduling all work for it automatically.
"""
import sqlite3
from abc import ABC, abstractmethod

import requests

from collector.config import Settings


class Source(ABC):
    name: str = "base"

    def __init__(self, settings: Settings, session: requests.Session):
        self.settings = settings
        self.session = session

    def is_configured(self) -> tuple[bool, str]:
        """Return (ready, reason). Sources that need API keys override this."""
        return True, ""

    @abstractmethod
    def extract(self):
        """Call the API and return the raw JSON responses, untouched."""

    @abstractmethod
    def transform(self, raw) -> dict[str, list[dict]]:
        """Turn raw JSON into clean rows, grouped by target table."""

    @abstractmethod
    def load(self, conn: sqlite3.Connection, tables: dict[str, list[dict]]) -> int:
        """Write rows to the database and return how many were loaded."""

    def run(self, conn: sqlite3.Connection) -> int:
        return self.load(conn, self.transform(self.extract()))
