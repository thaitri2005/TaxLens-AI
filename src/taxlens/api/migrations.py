"""Apply database migrations in the background when the API starts.

Running ``alembic upgrade`` before uvicorn starts left nothing answering the liveness
probe, so Container Apps killed the container after about 20 seconds and a slower
migration (rewriting the chunk table) rolled back and restarted in a loop. Now uvicorn
answers ``/health`` at once, ``/ready`` reports not ready until migrations finish, and a
failed migration keeps the API out of rotation with the error logged instead of looping.
"""

import logging
import threading
from enum import StrEnum

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)


class MigrationState(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


_state = MigrationState.NOT_STARTED
_state_lock = threading.Lock()


def migration_state() -> MigrationState:
    return _state


def mark_migrations_skipped() -> None:
    _set_state(MigrationState.COMPLETED)


def start_migrations(script_location: str = "migrations") -> threading.Thread:
    _set_state(MigrationState.RUNNING)
    thread = threading.Thread(
        target=_upgrade, args=(script_location,), name="alembic-upgrade", daemon=True
    )
    thread.start()
    return thread


def _upgrade(script_location: str) -> None:
    # Configured in code rather than from alembic.ini: env.py applies the ini's logging
    # configuration when given a config file, which would disable the API's loggers.
    config = Config()
    config.set_main_option("script_location", script_location)
    try:
        logger.info("migrations_started")
        command.upgrade(config, "head")
    except Exception:
        logger.exception("migrations_failed")
        _set_state(MigrationState.FAILED)
        return
    logger.info("migrations_completed")
    _set_state(MigrationState.COMPLETED)


def _set_state(state: MigrationState) -> None:
    global _state
    with _state_lock:
        _state = state
