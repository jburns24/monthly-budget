"""Per-aggregate repository protocols.

One module per aggregate. Repositories are reached through
:class:`app.ports.unit_of_work.UnitOfWork` rather than injected individually,
because several services touch three or four aggregates in one request and
something has to own ``flush``.
"""
