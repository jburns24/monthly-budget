"""Translate SQLAlchemy/asyncpg integrity failures into port errors.

This is the single highest-value piece of the adapter: it is what lets the
in-memory fake exercise the HTTP 409 paths, and it is why no service imports
``sqlalchemy.exc`` any more.
"""

import re

from sqlalchemy.exc import IntegrityError

from app.ports.errors import ForeignKeyViolation, PortError, UniqueViolation

# PostgreSQL class 23 (integrity constraint violation) SQLSTATE codes.
_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"

# asyncpg exposes ``constraint_name`` on its own exception classes, but
# SQLAlchemy's asyncpg DBAPI shim does not re-export it — the real asyncpg error
# is the shim's ``__cause__``. Fall back to the message, which always names the
# constraint, so a driver change degrades to "still correct" rather than
# "silently returns None".
_CONSTRAINT_IN_MESSAGE = re.compile(r'constraint "([^"]+)"')


def _constraint_name(exc: IntegrityError) -> str:
    """Return the constraint the database named, or ``"unknown"``."""
    cause = getattr(exc.orig, "__cause__", None)
    named = getattr(cause, "constraint_name", None)
    if named:
        return str(named)
    match = _CONSTRAINT_IN_MESSAGE.search(str(exc))
    return match.group(1) if match else "unknown"


def translate_integrity_error(exc: IntegrityError) -> PortError | None:
    """Return the port error for ``exc``, or None if it has no port equivalent.

    Returning None rather than a catch-all keeps NOT NULL and CHECK violations
    surfacing as their original ``IntegrityError``. Relabelling those as
    ``UniqueViolation`` would turn a genuine bug into a plausible-looking HTTP
    409 telling the user their name is taken.
    """
    sqlstate = getattr(exc.orig, "sqlstate", None)
    if sqlstate == _UNIQUE_VIOLATION:
        return UniqueViolation(_constraint_name(exc))
    if sqlstate == _FOREIGN_KEY_VIOLATION:
        return ForeignKeyViolation(_constraint_name(exc))
    return None
