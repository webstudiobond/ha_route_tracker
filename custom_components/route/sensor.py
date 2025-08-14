"""Route sensor platform."""
import logging
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config: ConfigType, async_add_entities: AddEntitiesCallback, discovery_info: DiscoveryInfoType | None = None) -> None:
    if DOMAIN not in hass.data:
        return
    sensors_gps = hass.data[DOMAIN].get("sensors_gps")
    if not sensors_gps:
        return
    entities = [GPSSensor(sensors_gps, key) for key in sensors_gps.states.keys()]
    async_add_entities(entities)


class GPSSensor(Entity):
    def __init__(self, sensors_gps, entity_id: str) -> None:
        self._sensors_gps = sensors_gps
        self._entity_id = entity_id
        self._attr_name = f"virtual_{self._entity_id.replace('.', '_')}"
        self._attr_unique_id = f"route_gps_{self._entity_id.replace('.', '_')}"
        self._icon = "mdi:crosshairs-gps"

    @property
    def name(self):
        return self._attr_name

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def state(self):
        return self._sensors_gps.states.get(self._entity_id, ["unknown"])[0]

    @property
    def icon(self):
        return self._icon

    @property
    def extra_state_attributes(self):
        st = self._sensors_gps.states.get(self._entity_id)
        if st:
            return {
                "latitude": st[1],
                "longitude": st[2],
                "source_entity": self._entity_id,
                "last_updated": st[0],
            }
        return {"source_entity": self._entity_id, "last_updated": None}

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, DOMAIN, self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        try:
            self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)
        except Exception:
            _LOGGER.exception(
                "Failed to schedule async_write_ha_state for %s", self._entity_id
            )
