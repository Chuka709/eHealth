import os

# Unit tests need no database; DB tests point DATABASE_URL at the compose test database.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unit@localhost:1/unit")
os.environ.setdefault("ENVIRONMENT", "test")

from hypothesis import settings as hypothesis_settings

# The container filesystem is read-only for the app user; keep examples in memory.
hypothesis_settings.register_profile("labtrack", database=None)
hypothesis_settings.load_profile("labtrack")
