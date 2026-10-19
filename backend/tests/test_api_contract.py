"""The generated API contract docs must match the live FastAPI schema."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gen_api_contract.py"


def test_api_contract_docs_are_up_to_date() -> None:
    spec = importlib.util.spec_from_file_location("gen_api_contract", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    stale = module.stale_files()

    assert not stale, f"Regenerate with `task be:api-contract`: {[p.name for p in stale]} are stale"
