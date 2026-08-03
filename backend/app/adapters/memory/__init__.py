"""In-memory implementation of the persistence ports, for unit tests only.

This is not a second production backend and must never be wired into the app. It
exists so service logic can be tested without a database — and it deliberately
refuses to fake anything a fake would get wrong. Methods marked Postgres tier in
the ports raise :class:`NotImplementedError` here; ``ON DELETE CASCADE`` and
CHECK constraints are not emulated at all.

What it *does* reproduce faithfully, because services depend on it:

- staged writes are invisible to queries until ``flush()`` (the real session runs
  with ``autoflush=False``);
- ``flush()`` applies the Python-side and server-side column defaults, so
  ``id`` and ``created_at`` are populated exactly as Postgres would;
- ``flush()`` enforces the declared composite unique constraints and raises the
  same :class:`~app.ports.errors.UniqueViolation` the SQLAlchemy adapter
  translates ``IntegrityError`` into;
- repositories hand back the *same* ORM instance they store, never a copy, so
  ``category.name = name; await uow.flush()`` works;
- a rollback invalidates the instances it hands out, so code that keeps using one
  fails loudly instead of silently writing to nothing.
"""
