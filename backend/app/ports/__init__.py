"""Persistence ports: the protocols application code depends on.

``app.ports`` describes *what* the data layer can do; ``app.adapters`` supplies
the *how* (SQLAlchemy against Postgres, or an in-memory fake for unit tests).
Services and routers import from here and never from ``app.adapters``.

The ports are persistence-*indirect*, not persistence-*ignorant*: SQLAlchemy ORM
instances are the data type crossing the seam, so this package transitively
imports SQLAlchemy. That is a deliberate trade recorded in
``docs/data-layer-ports-design.md`` risk (c) — introducing separate domain
entities would double the diff and add a mapper per aggregate for no behaviour
change.
"""
