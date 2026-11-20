"""Client für die öffentliche Settecose-API (/api/v1) mit persönlichem Token."""

from __future__ import annotations

from typing import Any

import aiohttp


class SettecoseError(Exception):
    """Allgemeiner Fehler beim Zugriff auf Settecose."""


class SettecoseAuthError(SettecoseError):
    """Token ungültig, abgelaufen oder ohne Recht."""


class SettecoseApi:
    """Dünner Client: ein Space, ein Token (Header x-api-key)."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self._session = session
        self._base = url.rstrip("/") + "/api/v1"
        self._headers = {"x-api-key": token, "accept": "application/json"}
        self.space_id: str | None = None

    async def _request(self, method: str, path: str, json: Any | None = None) -> Any:
        try:
            async with self._session.request(
                method,
                self._base + path,
                headers=self._headers,
                json=json,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as res:
                if res.status in (401, 403):
                    raise SettecoseAuthError(f"{res.status} bei {path}")
                if res.status >= 400:
                    text = await res.text()
                    raise SettecoseError(f"{res.status} bei {path}: {text[:200]}")
                if res.status == 204:
                    return None
                return await res.json()
        except aiohttp.ClientError as err:
            raise SettecoseError(str(err)) from err

    async def me(self) -> dict[str, Any]:
        """Konto und den Space des Tokens; merkt sich die Space-ID."""
        data = await self._request("GET", "/me")
        token = data.get("token") or {}
        self.space_id = token.get("space_id") or (data.get("spaces") or [{}])[0].get("id")
        return data

    def _space(self) -> str:
        if not self.space_id:
            raise SettecoseError("Space unbekannt; zuerst me() aufrufen")
        return f"/spaces/{self.space_id}"

    async def tasks(self) -> list[dict[str, Any]]:
        return await self._request("GET", self._space() + "/tasks")

    async def items(self) -> list[dict[str, Any]]:
        return await self._request("GET", self._space() + "/items")

    async def locations(self) -> list[dict[str, Any]]:
        return await self._request("GET", self._space() + "/locations")

    async def create_task(self, body: dict[str, Any]) -> str:
        data = await self._request("POST", self._space() + "/tasks", body)
        return data["id"]

    async def set_done(self, task_id: str, done: bool) -> None:
        await self._request("PATCH", f"{self._space()}/tasks/{task_id}", {"done": done})

    async def set_position(
        self, location_id: str, lat: float, lng: float, radius_m: float | None
    ) -> None:
        body: dict[str, Any] = {"lat": lat, "lng": lng}
        if radius_m:
            body["geofence_m"] = radius_m
        await self._request("PATCH", f"{self._space()}/locations/{location_id}", body)

    async def event(self, location_id: str, source: str = "ha_presence") -> list[dict[str, Any]]:
        return await self._request(
            "POST", self._space() + "/events", {"source": source, "location_id": location_id}
        )
