"""Minimal async client for the Légifrance API (PISTE, OAuth2 client credentials)."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
API_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
SANDBOX_OAUTH_URL = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
SANDBOX_API_URL = "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app"


class LegifranceError(RuntimeError):
    pass


class LegifranceClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        sandbox: bool | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id or os.environ.get("LEGIFRANCE_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("LEGIFRANCE_CLIENT_SECRET", "")
        if sandbox is None:
            sandbox = os.environ.get("LEGIFRANCE_SANDBOX", "").lower() in ("1", "true", "yes")
        self.oauth_url = SANDBOX_OAUTH_URL if sandbox else OAUTH_URL
        self.api_url = SANDBOX_API_URL if sandbox else API_URL
        self._http = http or httpx.AsyncClient(timeout=30)
        self._token: str | None = None
        self._expires_at = 0.0

    async def _get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 30:
            return self._token
        if not self.client_id or not self.client_secret:
            raise LegifranceError(
                "LEGIFRANCE_CLIENT_ID et LEGIFRANCE_CLIENT_SECRET doivent être définis "
                "(identifiants PISTE, https://piste.gouv.fr)."
            )
        resp = await self._http.post(
            self.oauth_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "openid",
            },
        )
        if resp.status_code != 200:
            raise LegifranceError(f"Échec OAuth PISTE ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._token

    async def post(self, path: str, body: dict[str, Any]) -> Any:
        for attempt in (1, 2):
            token = await self._get_token()
            resp = await self._http.post(
                f"{self.api_url}{path}",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 401 and attempt == 1:
                self._token = None  # token revoked/expired early: refresh once
                continue
            break
        if resp.status_code != 200:
            raise LegifranceError(f"Légifrance {path} → {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    async def get(self, path: str) -> Any:
        token = await self._get_token()
        resp = await self._http.get(
            f"{self.api_url}{path}", headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code != 200:
            raise LegifranceError(f"Légifrance {path} → {resp.status_code}: {resp.text[:500]}")
        return resp.json()
