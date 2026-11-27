import os

# Unit tests need no database; DB tests point DATABASE_URL at the compose test database.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unit@localhost:1/unit")
os.environ.setdefault("ENVIRONMENT", "test")

from hypothesis import settings as hypothesis_settings

# The container filesystem is read-only for the app user; keep examples in memory.
# No per-example deadline: the suite shares a container CPU with Postgres and the timing check
# failed at random (a slow example is not a wrong one; properties are what we test).
hypothesis_settings.register_profile("labtrack", database=None, deadline=None)
hypothesis_settings.load_profile("labtrack")
