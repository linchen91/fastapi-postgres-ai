import importlib

import database

POOL_ENV_KEYS = (
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT",
    "DB_POOL_RECYCLE",
    "DB_ECHO",
)


def _reload_with_env(monkeypatch, **env):
    for key in POOL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(database)


def test_pool_defaults(monkeypatch):
    db = _reload_with_env(monkeypatch)
    assert db.engine.pool.size() == 10
    assert db.engine.pool._max_overflow == 20
    assert db.engine.pool._timeout == 30
    assert db.engine.pool._pre_ping is True
    assert db.engine.pool._recycle == 1800
    assert db.engine.echo is True


def test_pool_env_overrides(monkeypatch):
    db = _reload_with_env(
        monkeypatch,
        DB_POOL_SIZE="3",
        DB_MAX_OVERFLOW="7",
        DB_POOL_TIMEOUT="5",
        DB_POOL_RECYCLE="60",
        DB_ECHO="false",
    )
    assert db.engine.pool.size() == 3
    assert db.engine.pool._max_overflow == 7
    assert db.engine.pool._timeout == 5
    assert db.engine.pool._recycle == 60
    assert db.engine.echo is False


def test_pool_total_capacity(monkeypatch):
    db = _reload_with_env(monkeypatch, DB_POOL_SIZE="4", DB_MAX_OVERFLOW="1")
    assert db.engine.pool.size() + db.engine.pool._max_overflow == 5
