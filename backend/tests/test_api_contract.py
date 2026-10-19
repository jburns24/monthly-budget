"""The generated API contract docs must match the live FastAPI schema."""

import importlib.util
from pathlib import Path
from types import ModuleType

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gen_api_contract.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_api_contract", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_api_contract_docs_are_up_to_date() -> None:
    module = _load_module()

    stale = module.stale_files()

    assert not stale, f"Regenerate with `task be:api-contract`: {[p.name for p in stale]} are stale"


def test_every_frontend_api_path_has_a_backend_route() -> None:
    """A frontend call to a missing route only fails at runtime (e.g. the old receipts retry call)."""
    module = _load_module()

    orphans = module.frontend_orphans(module.build_openapi())

    assert orphans == [], f"frontend/src/api calls paths with no backend route: {orphans}"
