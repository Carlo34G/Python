"""Best-effort Sparky Fitness sync.

IMPORTANT: Sparky's REST API is still beta and its exact routes may differ between
versions. This client is intentionally defensive: every call is wrapped, failures
never propagate into the bot, and the local SQLite store (store.py) remains the
source of truth. If a route below is wrong for your Sparky version, adjust the
constants in the CONFIGURABLE ENDPOINTS block — nothing else needs to change.

Auth model (per Sparky docs): JWT via email/password login, sent as
`Authorization: Bearer <token>`; some health-write routes accept an API key instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

from config import settings

# ------------------------- CONFIGURABLE ENDPOINTS ----------------------------
# Adjust these if your Sparky version uses different paths.
LOGIN_PATH = "/api/auth/login"          # expects {"email","password"} -> {"token": ...}
WEIGHT_PATH = "/api/measurements/weight"  # POST body: {"weight","date"}
FOOD_PATH = "/api/food/diary"             # POST body: {"description","calories","protein","date"}
# -----------------------------------------------------------------------------


@dataclass
class SparkyStatus:
    ok: bool
    detail: str = ""


class SparkyClient:
    def __init__(self) -> None:
        self.base = settings.sparky_base_url.rstrip("/")
        self._token: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.base) and bool(
            settings.sparky_api_key or (settings.sparky_email and settings.sparky_password)
        )

    def _auth_headers(self) -> dict:
        if settings.sparky_api_key:
            return {"Authorization": f"Bearer {settings.sparky_api_key}"}
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _ensure_login(self, client: httpx.AsyncClient) -> bool:
        if settings.sparky_api_key or self._token:
            return True
        if not (settings.sparky_email and settings.sparky_password):
            return False
        try:
            resp = await client.post(
                f"{self.base}{LOGIN_PATH}",
                json={"email": settings.sparky_email, "password": settings.sparky_password},
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data.get("token") or data.get("accessToken") or data.get("jwt")
            return bool(self._token)
        except Exception:
            return False

    async def push_weight(self, weight_kg: float, on: str | None = None) -> SparkyStatus:
        if not self.configured:
            return SparkyStatus(False, "Sparky not configured")
        on = on or date.today().isoformat()
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                if not await self._ensure_login(client):
                    return SparkyStatus(False, "Sparky login failed")
                resp = await client.post(
                    f"{self.base}{WEIGHT_PATH}",
                    headers=self._auth_headers(),
                    json={"weight": weight_kg, "date": on},
                )
                resp.raise_for_status()
            return SparkyStatus(True, "synced to Sparky")
        except Exception as exc:
            return SparkyStatus(False, f"Sparky sync skipped ({type(exc).__name__})")

    async def push_food(self, description: str, calories: float, protein_g: float,
                        on: str | None = None) -> SparkyStatus:
        if not self.configured:
            return SparkyStatus(False, "Sparky not configured")
        on = on or date.today().isoformat()
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                if not await self._ensure_login(client):
                    return SparkyStatus(False, "Sparky login failed")
                resp = await client.post(
                    f"{self.base}{FOOD_PATH}",
                    headers=self._auth_headers(),
                    json={
                        "description": description,
                        "calories": calories,
                        "protein": protein_g,
                        "date": on,
                    },
                )
                resp.raise_for_status()
            return SparkyStatus(True, "synced to Sparky")
        except Exception as exc:
            return SparkyStatus(False, f"Sparky sync skipped ({type(exc).__name__})")


sparky = SparkyClient()
