"""DB package — persistence layer for PetitionsRadar.

Exposes a sqlite3-based session helper used by scrapers and the API.
"""

from db.session import get_connection, init_db

__all__ = ["get_connection", "init_db"]
