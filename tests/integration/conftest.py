"""
Shared fixtures for integration tests.

db_session:  real async SQLAlchemy session — skips if DATABASE_URL not set
             or DB is unreachable.  Used by e2e tests that need actual DB rows.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def db_session():
    """
    Yield a live async DB session for integration tests.

    Skips gracefully when:
      - DATABASE_URL env var is not set
      - The database cannot be reached (connection error)

    The session is rolled back after each test to keep the DB clean.
    """
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        pytest.skip("DATABASE_URL not set — integration DB tests require a live DB")

    try:
        # Lazy import to avoid touching SQLAlchemy engine at collection time
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

        engine = create_async_engine(database_url, pool_pre_ping=True, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            try:
                yield session
            finally:
                await session.rollback()
                await session.close()

        await engine.dispose()

    except Exception as exc:
        pytest.skip(f"DB connection failed — {exc}")
