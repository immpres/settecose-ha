"""Regelmässiges Abholen von Aufgaben, Orten und Items."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SettecoseApi, SettecoseAuthError, SettecoseError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class SettecoseData:
    """Stand des Space zum letzten Abruf."""

    tasks: list[dict[str, Any]] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
    item_count: int = 0

    def groups(self) -> dict[str, dict[str, Any]]:
        """Offene Aufgaben nach Ziel (wie die Gruppen in der App)."""
        out: dict[str, dict[str, Any]] = {}
        for task in self.tasks:
            target = task["target"]
            group = out.setdefault(target["id"], {"target": target, "tasks": []})
            group["tasks"].append(task)
        return out


class SettecoseCoordinator(DataUpdateCoordinator[SettecoseData]):
    """Holt den Stand des Space; Fehler beim Token führen zur erneuten Anmeldung."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: SettecoseApi, interval: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api

    async def _async_update_data(self) -> SettecoseData:
        try:
            tasks = await self.api.tasks()
            locations = await self.api.locations()
            items = await self.api.items()
        except SettecoseAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SettecoseError as err:
            raise UpdateFailed(str(err)) from err
        return SettecoseData(tasks=tasks, locations=locations, item_count=len(items))
