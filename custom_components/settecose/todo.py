"""Aufgaben-Gruppen als To-do-Listen: eine Liste pro Ziel (Ort, Ortstyp, Person, Item)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SettecoseConfigEntry
from .api import SettecoseError
from .const import DEFAULT_TYPE_FOR_TARGET, DOMAIN
from .coordinator import SettecoseCoordinator

VERB = {
    "kaufen": "kaufen",
    "abholen": "abholen",
    "bringen": "bringen",
    "zurueckgeben": "zurückgeben",
    "erledigen": "erledigen",
    "aufraeumen": "aufräumen",
}


def device_info(entry: SettecoseConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Settecose {entry.runtime_data.space_name}",
        manufacturer="immpres",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=entry.data["url"],
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: SettecoseConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        # Neue Ziele bekommen eine Liste; verschwundene bleiben leer stehen
        new = [
            SettecoseTodoList(coordinator, entry, target_id, group["target"])
            for target_id, group in coordinator.data.groups().items()
            if target_id not in known
        ]
        known.update(e.target_id for e in new)
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class SettecoseTodoList(CoordinatorEntity[SettecoseCoordinator], TodoListEntity):
    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM | TodoListEntityFeature.UPDATE_TODO_ITEM
    )

    def __init__(
        self,
        coordinator: SettecoseCoordinator,
        entry: SettecoseConfigEntry,
        target_id: str,
        target: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self.target_id = target_id
        self._target = target
        self._attr_unique_id = f"{entry.entry_id}-todo-{target_id}"
        self._attr_name = target["name"].split(" › ")[-1]
        self._attr_device_info = device_info(entry)
        self._api = entry.runtime_data.api

    @property
    def todo_items(self) -> list[TodoItem]:
        group = self.coordinator.data.groups().get(self.target_id)
        if group is None:
            return []
        return [
            TodoItem(
                uid=t["id"],
                summary=f"{t['title']} {VERB.get(t['task_type'], '')}".strip(),
                status=TodoItemStatus.NEEDS_ACTION,
                due=None,
            )
            for t in group["tasks"]
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"target_kind": self._target["kind"], "target_path": self._target["name"]}

    async def async_create_todo_item(self, item: TodoItem) -> None:
        key = {"person": "person_id", "item": "item_id"}.get(self._target["kind"], "target_id")
        body = {
            "task_type": DEFAULT_TYPE_FOR_TARGET.get(self._target["kind"], "erledigen"),
            "title": item.summary or "",
            key: self.target_id,
        }
        try:
            await self._api.create_task(body)
        except SettecoseError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.uid is None:
            return
        try:
            await self._api.set_done(item.uid, item.status == TodoItemStatus.COMPLETED)
        except SettecoseError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
