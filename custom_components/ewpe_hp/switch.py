"""Power, quiet running and fast hot water."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import FAST_HOT_WATER, POW, QUIET
from .coordinator import EwpeConfigEntry, UnitCoordinator
from .entity import UnitEntity, reporting

SWITCHES = (
    ("power", POW, None),
    ("quiet", QUIET, EntityCategory.CONFIG),
    ("fast_hot_water", FAST_HOT_WATER, None),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EwpeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(
        UnitSwitch(coordinator, key, name, category) for key, name, category in SWITCHES for coordinator in reporting(entry, name)
    )


class UnitSwitch(UnitEntity, SwitchEntity):
    def __init__(self, coordinator: UnitCoordinator, key: str, name: str, category: EntityCategory | None) -> None:
        super().__init__(coordinator, key)
        self._name = name
        self._attr_entity_category = category

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.get(self._name)
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.send({self._name: 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.send({self._name: 0})
