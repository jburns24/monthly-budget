"""Driver-independent errors raised across the persistence seam.

Adapters translate their own failure modes into these, so a service can handle
"that name is already taken" without importing ``sqlalchemy.exc`` or knowing
that asyncpg exists. The in-memory adapter raises exactly the same types, which
is what lets unit tests exercise the HTTP 409 paths.
"""


class PortError(Exception):
    """Base class for every error a persistence adapter raises deliberately."""


class ConstraintViolation(PortError):
    """A named database constraint rejected a write."""

    def __init__(self, constraint: str) -> None:
        super().__init__(f"{type(self).__name__}: {constraint}")
        self.constraint = constraint


class UniqueViolation(ConstraintViolation):
    """A unique index or constraint rejected a write."""


class ForeignKeyViolation(ConstraintViolation):
    """A foreign key constraint rejected a write."""


class StaleObject(PortError):
    """An object was read after the transaction that produced it was rolled back.

    Only the in-memory adapter raises this. It stands in for the real failure a
    rollback causes under SQLAlchemy + asyncpg, where the instance's attributes
    are expired and the refetch blows up with ``MissingGreenlet`` far away from
    the rollback that caused it.
    """
