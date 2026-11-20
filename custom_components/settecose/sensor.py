"""Sensoren: offene Aufgaben, Items, Orte mit Koordinaten."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SettecoseConfigEntry
from .coordinator import SettecoseCoordinator, SettecoseData
from .todo import device_info


@dataclass(frozen=True, kw_only=True)
class SettecoseSensorDescription(SensorEntityDescription):
    value: Callable[[SettecoseData], int]


SENSORS = (
    SettecoseSensorDescription(
        key="open_tasks",
        translation_key="open_tasks",
        icon="mdi:checkbox-marked-circle-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: len(d.tasks),
    ),
    SettecoseSensorDescription(
        key="items",
        translation_key="items",
        icon="mdi:package-variant-closed",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d.item_count,
    ),
    SettecoseSensorDescription(
        key="places_on_map",
        translation_key="places_on_map",
        icon="mdi:map-marker-radius",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: sum(1 for p in d.locations if p.get("lat") is not None),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SettecoseConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(SettecoseSensor(coordinator, entry, d) for d in SENSORS)


class SettecoseSensor(CoordinatorEntity[SettecoseCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: SettecoseSensorDescription

    def __init__(
        self,
        coordinator: SettecoseCoordinator,
        entry: SettecoseConfigEntry,
        description: SettecoseSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}-{description.key}"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> int:
        return self.entity_description.value(self.coordinator.data)
