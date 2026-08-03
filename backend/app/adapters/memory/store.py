"""The in-memory store: identity map, column defaults, unique indexes, snapshots.

Holds **live ORM instances**, never copies. Every service in this codebase relies
on implicit dirty tracking — ``category.name = name; await uow.flush()`` with no
``add`` in between — so a store that handed back copies would turn those writes
into silent no-ops that no test could catch. Snapshots are the one place clones
appear, and they are never handed out.

Rollback is deliberately stricter than SQLAlchemy: it invalidates the instances
the store is holding, so any code that keeps using one after a rollback raises
:class:`~app.ports.errors.StaleObject` immediately instead of quietly writing to
an object nothing is watching. Under the real stack the equivalent mistake
surfaces as ``MissingGreenlet`` from a lazy refresh, arbitrarily far from the
rollback that caused it.

Not emulated, on purpose: ``ON DELETE CASCADE``, CHECK constraints, and any
relationship loading. Code depending on those is Postgres tier.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NoReturn, TypeVar
from uuid import UUID

from sqlalchemy import UniqueConstraint
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.sql.schema import Column, ColumnDefault

from app.ports.errors import StaleObject, UniqueViolation

T = TypeVar("T")


def postgres_tier(qualname: str, capability: str) -> NoReturn:
    """Raise for a port method the in-memory adapter cannot honestly fake.

    ``qualname`` should read as ``ClassName.method_name``, so the error names
    both the adapter and the operation; ``capability`` names what a fake would
    have to re-implement rather than test (pg_trgm scoring, a GROUP BY ranking,
    a 5-way aggregate...). Shared by every adapter module with a Postgres-tier
    method, so the wording stays consistent instead of drifting per module.
    """
    raise NotImplementedError(
        f"{qualname} is Postgres tier and has no in-memory implementation: it "
        f"depends on {capability}. Test it against real Postgres "
        f"(tests/test_sqlalchemy_adapter.py)."
    )


# type -> primary key -> instance
_Snapshot = dict[type[Any], dict[UUID, Any]]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class UniqueIndex:
    """A composite unique constraint the store enforces at flush time."""

    name: str
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """What :meth:`MemoryStore.flush` has to do for a given model.

    ``defaults`` covers every column the database fills in by itself, keyed by
    attribute name. ``unique`` covers the composite unique constraints; primary
    keys need no entry because the store is keyed by them.

    Both are *derived* from the mapper by :func:`model_spec`, never hand-written.
    Restating them per model would be a second source of truth that a human has
    to keep in sync for each of the seven aggregates still to be migrated.
    """

    defaults: Mapping[str, Callable[[], Any]]
    unique: tuple[UniqueIndex, ...]


# The one thing the mapper cannot hand over as a Python value: a server default is
# opaque DDL, so the fake needs an explicit stand-in for each one the schema uses.
# Keyed by the rendered SQL. Every server default in this schema is func.now().
_SERVER_DEFAULT_SHIMS: dict[str, Callable[[], Any]] = {"now()": _utcnow}


def _python_default(default: ColumnDefault, model: type[Any], key: str) -> Callable[[], Any]:
    """Turn a column's Python-side ``default=`` into a zero-argument factory."""
    if default.is_callable:
        # SQLAlchemy wraps plain callables so they accept an ExecutionContext.
        wrapped = default.arg
        return lambda: wrapped(None)
    if default.is_scalar:
        value = default.arg
        return lambda: value
    raise LookupError(
        f"{model.__name__}.{key} has a SQL-expression default the in-memory store "
        f"cannot evaluate; either give the column a Python default or treat the "
        f"code that needs it as Postgres tier"
    )


def _server_default(column: Column[Any], model: type[Any], key: str) -> Callable[[], Any]:
    """Return the Python stand-in for a column's ``server_default``."""
    rendered = str(column.server_default.arg).lower()  # type: ignore[union-attr]
    shim = _SERVER_DEFAULT_SHIMS.get(rendered)
    if shim is None:
        raise LookupError(
            f"{model.__name__}.{key} has server_default {rendered!r}, which the "
            f"in-memory store has no stand-in for; add it to "
            f"app.adapters.memory.store._SERVER_DEFAULT_SHIMS"
        )
    return shim


def _build_spec(model: type[Any]) -> ModelSpec:
    mapper = sa_inspect(model)
    defaults: dict[str, Callable[[], Any]] = {}
    for attr in mapper.column_attrs:
        column = attr.columns[0]
        if column.default is not None:
            defaults[attr.key] = _python_default(column.default, model, attr.key)
        elif column.server_default is not None:
            defaults[attr.key] = _server_default(column, model, attr.key)

    unique = tuple(
        UniqueIndex(
            str(constraint.name) if constraint.name else f"unnamed unique constraint on {model.__tablename__}",
            tuple(mapper.get_property_by_column(column).key for column in constraint.columns),
        )
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    return ModelSpec(defaults=defaults, unique=unique)


_SPECS: dict[type[Any], ModelSpec] = {}


def model_spec(model: type[Any]) -> ModelSpec:
    """Return the flush-time rules for ``model``, reading its mapper once."""
    cached = _SPECS.get(model)
    if cached is None:
        cached = _build_spec(model)
        _SPECS[model] = cached
    return cached


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------

_STALE_CLASSES: dict[type[Any], type[Any]] = {}

# Stamped onto every generated stale class so _mark_stale can recognise one it
# already produced, without a second registry to keep in sync.
_STALE_MARKER = "_memory_store_stale"


def _stale_class(model: type[Any]) -> type[Any]:
    """Return a subclass of ``model`` whose every attribute read raises StaleObject.

    ``__abstract__`` is what keeps this out of SQLAlchemy's mapper registry:
    declarative maps new subclasses automatically via ``__init_subclass__``, and
    an accidental single-table-inheritance mapper would pollute ``Base.metadata``
    for the whole process. Dunder reads are let through so ``isinstance``,
    ``repr`` and pytest's own introspection still work on a stale instance.
    """
    cached = _STALE_CLASSES.get(model)
    if cached is not None:
        return cached

    label = model.__name__

    def __getattribute__(self: Any, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            return object.__getattribute__(self, name)
        raise StaleObject(f"this {label} was discarded by a rollback; re-read it through the repository")

    cached = type(
        f"Stale{label}",
        (model,),
        {"__abstract__": True, "__getattribute__": __getattribute__, _STALE_MARKER: True},
    )
    _STALE_CLASSES[model] = cached
    return cached


def _mark_stale(row: Any) -> None:
    """Make every future attribute read on ``row`` raise StaleObject."""
    model = type(row)
    if getattr(model, _STALE_MARKER, False):
        return
    row.__class__ = _stale_class(model)


# ---------------------------------------------------------------------------
# Cloning
# ---------------------------------------------------------------------------


_COLUMN_NAMES: dict[type[Any], tuple[str, ...]] = {}


def _column_names(model: type[Any]) -> tuple[str, ...]:
    """Return ``model``'s mapped column names, asking the mapper once per class."""
    cached = _COLUMN_NAMES.get(model)
    if cached is None:
        cached = tuple(attr.key for attr in sa_inspect(model).column_attrs)
        _COLUMN_NAMES[model] = cached
    return cached


def _clone(row: T) -> T:
    """Copy a row's column values onto a fresh unattached instance.

    Column-by-column rather than ``copy.deepcopy`` because deepcopy would also
    walk SQLAlchemy's ``InstanceState`` — which holds a weakref back to the
    original instance that deepcopy treats as atomic, quietly producing a clone
    whose state points at the wrong object. Relationships are not copied;
    snapshots are column data only.
    """
    model = type(row)
    clone = model()
    for name in _column_names(model):
        setattr(clone, name, getattr(row, name))
    return clone


class MemoryStore:
    """Single-transaction store shared by the in-memory repositories."""

    def __init__(self) -> None:
        self._rows: _Snapshot = {}
        self._pending_adds: list[Any] = []
        self._pending_deletes: list[Any] = []
        self._committed: _Snapshot = {}
        self._savepoints: list[_Snapshot] = []

    # -- staging ---------------------------------------------------------

    def add(self, row: Any) -> None:
        """Stage an insert. Invisible to reads until :meth:`flush`."""
        self._pending_adds.append(row)

    def add_all(self, rows: Iterable[Any]) -> None:
        """Stage a batch of inserts."""
        self._pending_adds.extend(rows)

    def delete(self, row: Any) -> None:
        """Stage a delete. Applied by :meth:`flush`."""
        self._pending_deletes.append(row)

    # -- reads -----------------------------------------------------------

    def rows(self, model: type[T]) -> list[T]:
        """Return every flushed instance of ``model``, in insertion order.

        Staged-but-unflushed writes are excluded, matching the real session's
        ``autoflush=False``.
        """
        return list(self._rows.get(model, {}).values())

    def get(self, model: type[T], primary_key: UUID) -> T | None:
        """Return the flushed instance with that primary key, or None."""
        found: T | None = self._rows.get(model, {}).get(primary_key)
        return found

    # -- transaction -----------------------------------------------------

    def flush(self) -> None:
        """Apply staged writes, fill in defaults, then enforce unique constraints.

        Deletes are applied before inserts so a single flush can free a unique key
        and re-use it. Raises :class:`~app.ports.errors.UniqueViolation` on a
        duplicate; like an aborted Postgres transaction, the store is left dirty
        and the caller is expected to roll back.
        """
        for row in self._pending_deletes:
            self._rows.get(type(row), {}).pop(row.id, None)
        self._pending_deletes.clear()

        for row in self._pending_adds:
            self._apply_defaults(row)
            self._rows.setdefault(type(row), {})[row.id] = row
        self._pending_adds.clear()

        self._enforce_unique()

    def commit(self) -> None:
        """Flush, then make this state the point a rollback returns to."""
        self.flush()
        self._committed = self._snapshot()
        self._savepoints.clear()

    def rollback(self) -> None:
        """Discard everything since the last commit and invalidate live instances."""
        self._savepoints.clear()
        self._invalidate_live_rows()
        self._rows = self._copy(self._committed)

    def push_savepoint(self) -> int:
        """Flush, snapshot, and return the new savepoint's depth (1-based)."""
        self.flush()
        self._savepoints.append(self._snapshot())
        return len(self._savepoints)

    def rollback_to_savepoint(self, depth: int) -> None:
        """Restore the state captured at ``depth``, discarding any inner savepoints.

        A no-op if the savepoint is already gone, which happens when an enclosing
        ``rollback()`` cleared the stack from inside the block.
        """
        if len(self._savepoints) < depth:
            return
        snapshot = self._savepoints[depth - 1]
        del self._savepoints[depth - 1 :]
        self._invalidate_live_rows()
        self._rows = self._copy(snapshot)

    def release_savepoint(self, depth: int) -> None:
        """Drop the savepoint, keeping the writes made inside it."""
        if len(self._savepoints) < depth:
            return
        del self._savepoints[depth - 1 :]

    # -- internals -------------------------------------------------------

    @staticmethod
    def _apply_defaults(row: Any) -> None:
        for name, factory in model_spec(type(row)).defaults.items():
            if getattr(row, name, None) is None:
                setattr(row, name, factory())

    def _enforce_unique(self) -> None:
        for model, rows in self._rows.items():
            for index in model_spec(model).unique:
                seen: set[tuple[Any, ...]] = set()
                for row in rows.values():
                    key = tuple(getattr(row, name) for name in index.fields)
                    # Postgres treats NULLs as distinct, so a partial key never collides.
                    if any(part is None for part in key):
                        continue
                    if key in seen:
                        raise UniqueViolation(index.name)
                    seen.add(key)

    def _snapshot(self) -> _Snapshot:
        return self._copy(self._rows)

    @staticmethod
    def _copy(snapshot: _Snapshot) -> _Snapshot:
        # Clones on the way in *and* out, so restoring twice from the same
        # snapshot cannot hand out instances that share state.
        return {model: {pk: _clone(row) for pk, row in rows.items()} for model, rows in snapshot.items()}

    def _invalidate_live_rows(self) -> None:
        for rows in self._rows.values():
            for row in rows.values():
                _mark_stale(row)
        for row in (*self._pending_adds, *self._pending_deletes):
            _mark_stale(row)
        self._pending_adds.clear()
        self._pending_deletes.clear()
