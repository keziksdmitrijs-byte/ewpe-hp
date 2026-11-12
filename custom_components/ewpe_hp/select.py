"""Operating mode, and what goes first when heating or cooling shares the unit with hot water."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COOL_PRIORITY, HEAT_PRIORITY, MOD, MODES
from .coordinator import EwpeConfigEntry, UnitCoordinator
from .entity import UnitEntity, reporting

SELECTS = (
    ("mode", MOD, MODES, None),
    ("heat_priority", HEAT_PRIORITY, {"heating": 0, "hot_water": 1}, EntityCategory.CONFIG),
    ("cool_priority", COOL_PRIORITY, {"cooling": 0, "hot_water": 1}, EntityCategory.CONFIG),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EwpeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(
        UnitSelect(coordinator, key, name, choices, category)
        for key, name, choices, category in SELECTS
        for coordinator in reporting(entry, name)
    )


class UnitSelect(UnitEntity, SelectEntity):
    def __init__(
        self,
        coordinator: UnitCoordinator,
        key: str,
        name: str,
        choices: dict[str, int],
        category: EntityCategory | None,
    ) -> None:
        super().__init__(coordinator, key)
        self._name = name
        self._choices = choices
        self._attr_options = list(choices)
        self._attr_entity_category = category

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.get(self._name)
        return next((option for option, number in self._choices.items() if number == value), None)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.send({self._name: self._choices[option]})
