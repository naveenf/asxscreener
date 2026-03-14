"""
Settings Routes

Global screener configuration managed by the admin user.
"""

import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import List
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from firebase_admin import firestore

from ..firebase_setup import db
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings")

BEST_STRATEGIES_PATH = settings.METADATA_DIR / "best_strategies.json"


async def get_current_user_email(authorization: str = Header(...)) -> str:
    """Dependency to verify Google ID token and return email."""
    try:
        token = authorization.replace("Bearer ", "")
        id_info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )
        email = id_info.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Email missing from token")
        return email
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def _build_combos(disabled: set, direction_overrides: dict = None) -> List[dict]:
    """
    Parse best_strategies.json and return full combo list with enabled/disabled status
    and direction preference (both/buy/sell).
    Each combo is identified by 'PAIR::StrategyName'.
    """
    if direction_overrides is None:
        direction_overrides = {}
    combos = []
    try:
        with open(BEST_STRATEGIES_PATH, "r") as f:
            strategy_map = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read best_strategies.json: {e}")
        return combos

    for pair, config in strategy_map.items():
        strategies_list = config.get("strategies", [config])
        for s in strategies_list:
            strategy_name = s.get("strategy", "Unknown")
            timeframe = s.get("timeframe", "?")
            key = f"{pair}::{strategy_name}"
            combos.append({
                "key": key,
                "pair": pair,
                "strategy": strategy_name,
                "timeframe": timeframe,
                "enabled": key not in disabled,
                "direction": direction_overrides.get(key, "both")
            })

    return combos


@router.get("/strategy-overrides")
async def get_strategy_overrides(email: str = Depends(get_current_user_email)):
    """
    Return all pair+strategy combos with their enabled/disabled state.
    Any logged-in user can read this.
    """
    disabled = set()
    direction_overrides = {}
    try:
        doc = db.collection("config").document("strategy_overrides").get()
        if doc.exists:
            data = doc.to_dict()
            disabled = set(data.get("disabled", []))
            direction_overrides = data.get("direction_overrides", {})
    except Exception as e:
        logger.warning(f"Could not read strategy_overrides from Firestore: {e}")

    combos = _build_combos(disabled, direction_overrides)
    return {
        "combos": combos,
        "disabled": list(disabled),
        "direction_overrides": direction_overrides,
        "is_admin": email == settings.AUTHORIZED_AUTO_TRADER_EMAIL
    }


class StrategyOverridesUpdate(BaseModel):
    disabled: List[str]
    direction_overrides: dict = {}


@router.put("/strategy-overrides")
async def update_strategy_overrides(
    body: StrategyOverridesUpdate,
    email: str = Depends(get_current_user_email)
):
    """
    Update the global disabled strategy list.
    Only the authorized auto-trader email can write.
    """
    if email != settings.AUTHORIZED_AUTO_TRADER_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Validate submitted keys against known combos.
    # Keys for pairs/strategies that have since been removed from best_strategies.json are
    # silently dropped — they cannot re-disable anything and would otherwise cause a 422
    # every time the admin saves after a pair is pruned from the active config.
    known_keys = {c["key"] for c in _build_combos(set())}
    stale = [k for k in body.disabled if k not in known_keys]
    valid_disabled = [k for k in body.disabled if k in known_keys]
    if stale:
        logger.info(f"Dropping {len(stale)} stale strategy keys no longer in config: {stale}")

    # Validate direction_overrides: keep only known keys with valid values
    valid_directions = {"both", "buy", "sell"}
    valid_direction_overrides = {
        k: v for k, v in body.direction_overrides.items()
        if k in known_keys and v in valid_directions and v != "both"
    }

    try:
        db.collection("config").document("strategy_overrides").set({
            "disabled": valid_disabled,
            "direction_overrides": valid_direction_overrides,
            "updated_by": email,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Strategy overrides updated by {email}: {len(valid_disabled)} disabled, {len(valid_direction_overrides)} direction overrides")
        return {"success": True, "disabled": valid_disabled, "direction_overrides": valid_direction_overrides}
    except Exception as e:
        logger.error(f"Failed to update strategy_overrides: {e}")
        raise HTTPException(status_code=500, detail="Failed to save overrides")
