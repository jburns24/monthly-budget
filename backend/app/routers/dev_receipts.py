"""Dev-only Claude mock-scenario toggle endpoint.

Only accessible when environment is development or test — raises HTTP 404 otherwise.
Matches the gating pattern used by routers/dev_auth.py.
"""

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["dev"])


@router.post("/api/dev/mock-claude", status_code=status.HTTP_200_OK)
async def set_mock_scenario(scenario: str = "success") -> dict:
    """Set the active Claude mock scenario for this process.

    Raises HTTP 404 unless running in development or test environment.
    Updates settings.anthropic_mock_scenario in-process so subsequent
    receipt uploads use the specified mock branch without a restart.
    """
    if settings.environment.lower() not in ("development", "test"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    settings.anthropic_mock_scenario = scenario
    logger.info("mock_claude_scenario_set", scenario=scenario)
    return {"scenario": scenario}
