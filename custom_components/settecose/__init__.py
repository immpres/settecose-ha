"""Settecose für Home Assistant: Aufgaben als To-do-Listen, Sensoren, Ankommen an Orten.

Spricht ausschliesslich die öffentliche API /api/v1 mit einem persönlichen Token an
(ein Token gilt für genau einen Space).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE, Platform
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event

from .api import SettecoseApi, SettecoseAuthError, SettecoseError
from .const import (
    CONF_PRESENCE,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_TASKS_HERE,
    TASK_TYPES,
)
from .coordinator import SettecoseCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.TODO]


@dataclass
class SettecoseRuntime:
    api: SettecoseApi
    coordinator: SettecoseCoordinator
    space_name: str


type SettecoseConfigEntry = ConfigEntry[SettecoseRuntime]


async def async_setup_entry(hass: HomeAssistant, entry: SettecoseConfigEntry) -> bool:
    api = SettecoseApi(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    try:
        me = await api.me()
    except SettecoseAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SettecoseError as err:
        raise ConfigEntryNotReady(str(err)) from err

    space_name = next(
        (s["name"] for s in me.get("spaces", []) if s["id"] == api.space_id), "Settecose"
    )
    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = SettecoseCoordinator(hass, entry, api, interval)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = SettecoseRuntime(api=api, coordinator=coordinator, space_name=space_name)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    if entry.options.get(CONF_PRESENCE, True):
        _track_presence(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SettecoseConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload(hass: HomeAssistant, entry: SettecoseConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


# ---------------------------------------------------------------------------
# Orte und Zonen


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def place_for_zone(hass: HomeAssistant, entry: SettecoseConfigEntry, zone_id: str) -> dict[str, Any] | None:
    """Settecose-Ort zu einer Zone: zuerst gleicher Name, sonst ein Ort mit Koordinaten in der Zone."""
    zone = hass.states.get(zone_id)
    if zone is None:
        return None
    places = entry.runtime_data.coordinator.data.locations
    name = (zone.attributes.get("friendly_name") or zone.name or "").strip().casefold()
    for place in places:
        if place["name"].strip().casefold() == name:
            return place
    lat, lng = zone.attributes.get(ATTR_LATITUDE), zone.attributes.get(ATTR_LONGITUDE)
    radius = float(zone.attributes.get("radius") or 100)
    if lat is None or lng is None:
        return None
    best: tuple[float, dict[str, Any]] | None = None
    for place in places:
        if place.get("lat") is None or place.get("lng") is None:
            continue
        d = _distance_m(lat, lng, place["lat"], place["lng"])
        if d <= radius + float(place.get("geofence_m") or 0) and (best is None or d < best[0]):
            best = (d, place)
    return best[1] if best else None


def _zone_of_state(hass: HomeAssistant, state: str) -> str | None:
    """Zustand einer Person («home», «Büro») → Entity-ID der Zone."""
    if state == "home":
        return "zone.home"
    for zone in hass.states.async_all("zone"):
        if zone.name == state or zone.attributes.get("friendly_name") == state:
            return zone.entity_id
    return None


@callback
def _track_presence(hass: HomeAssistant, entry: SettecoseConfigEntry) -> None:
    """Kommt eine Person in eine Zone, die zu einem Ort passt: Aufgaben dort als Ereignis."""

    async def _changed(event: Event[EventStateChangedData]) -> None:
        new, old = event.data["new_state"], event.data["old_state"]
        if new is None or (old is not None and old.state == new.state):
            return
        zone_id = _zone_of_state(hass, new.state)
        if zone_id is None:
            return
        place = place_for_zone(hass, entry, zone_id)
        if place is None:
            return
        try:
            tasks = await entry.runtime_data.api.event(place["id"])
        except SettecoseError as err:
            _LOGGER.warning("Aufgaben für %s nicht abrufbar: %s", place["name"], err)
            return
        if not tasks:
            return
        hass.bus.async_fire(
            EVENT_TASKS_HERE,
            {
                "person": new.entity_id,
                "zone": zone_id,
                "location_id": place["id"],
                "location": place["path"],
                "count": len(tasks),
                "tasks": [{"id": t["id"], "title": t["title"], "type": t["task_type"], "target": t["target"]["name"]} for t in tasks],
            },
        )

    persons = hass.states.async_entity_ids("person")
    if persons:
        entry.async_on_unload(async_track_state_change_event(hass, persons, _changed))


# ---------------------------------------------------------------------------
# Dienste


def _entry(hass: HomeAssistant) -> SettecoseConfigEntry:
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None)]
    if not entries:
        raise HomeAssistantError("Settecose ist nicht eingerichtet")
    return entries[0]


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "add_task"):
        return

    async def add_task(call: ServiceCall) -> None:
        entry = _entry(hass)
        body: dict[str, Any] = {"task_type": call.data["type"], "title": call.data["title"]}
        target = call.data["target"]
        places = entry.runtime_data.coordinator.data.locations
        groups = entry.runtime_data.coordinator.data.groups()
        # Ziel als ID oder Name eines Orts bzw. einer bestehenden Gruppe
        hit = next((p for p in places if target in (p["id"], p["name"], p["path"])), None)
        if hit:
            body["target_id"] = hit["id"]
        else:
            group = next((g for g in groups.values() if target in (g["target"]["id"], g["target"]["name"])), None)
            if group is None:
                raise HomeAssistantError(f"Ziel «{target}» nicht gefunden")
            key = {"person": "person_id", "item": "item_id"}.get(group["target"]["kind"], "target_id")
            body[key] = group["target"]["id"]
        try:
            await entry.runtime_data.api.create_task(body)
        except SettecoseError as err:
            raise HomeAssistantError(str(err)) from err
        await entry.runtime_data.coordinator.async_request_refresh()

    async def tasks_at(call: ServiceCall) -> ServiceResponse:
        entry = _entry(hass)
        location = call.data.get("location")
        zone = call.data.get("zone")
        place = None
        if zone:
            place = place_for_zone(hass, entry, zone)
        elif location:
            place = next(
                (p for p in entry.runtime_data.coordinator.data.locations if location in (p["id"], p["name"], p["path"])),
                None,
            )
        if place is None:
            raise HomeAssistantError("Kein passender Settecose-Ort")
        tasks = await entry.runtime_data.api.event(place["id"], "hand")
        return {"location": place["path"], "tasks": [{"id": t["id"], "title": t["title"], "type": t["task_type"], "target": t["target"]["name"]} for t in tasks]}

    async def import_zone(call: ServiceCall) -> None:
        """Lage einer Home-Assistant-Zone für einen Settecose-Ort übernehmen."""
        entry = _entry(hass)
        zone = hass.states.get(call.data["zone"])
        if zone is None:
            raise HomeAssistantError("Zone nicht gefunden")
        location = call.data["location"]
        place = next(
            (p for p in entry.runtime_data.coordinator.data.locations if location in (p["id"], p["name"], p["path"])),
            None,
        )
        if place is None:
            raise HomeAssistantError(f"Ort «{location}» nicht gefunden")
        try:
            await entry.runtime_data.api.set_position(
                place["id"],
                float(zone.attributes[ATTR_LATITUDE]),
                float(zone.attributes[ATTR_LONGITUDE]),
                float(zone.attributes.get("radius") or 100),
            )
        except SettecoseError as err:
            raise HomeAssistantError(str(err)) from err
        await entry.runtime_data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "add_task",
        add_task,
        schema=vol.Schema(
            {
                vol.Required("title"): cv.string,
                vol.Required("target"): cv.string,
                vol.Optional("type", default="kaufen"): vol.In(TASK_TYPES),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "tasks_at",
        tasks_at,
        schema=vol.Schema({vol.Optional("location"): cv.string, vol.Optional("zone"): cv.entity_id}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "import_zone",
        import_zone,
        schema=vol.Schema({vol.Required("zone"): cv.entity_id, vol.Required("location"): cv.string}),
    )
