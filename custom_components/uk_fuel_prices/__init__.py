"""The UK Fuel Prices integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_STATIONS, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN
from .coordinator import FuelFinderCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UK Fuel Prices from a config entry."""
    coordinator = FuelFinderCoordinator(
        hass,
        client_id=entry.data[CONF_CLIENT_ID],
        client_secret=entry.data[CONF_CLIENT_SECRET],
        stations=entry.options.get(CONF_STATIONS, []),
        update_interval=entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change (e.g. stations added/removed)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove a station device via the HA device 3-dot menu."""
    node_id = next(
        (identifier[1] for identifier in device_entry.identifiers if identifier[0] == DOMAIN),
        None,
    )
    if node_id is None:
        return False

    stations = [s for s in entry.options.get(CONF_STATIONS, []) if s["node_id"] != node_id]
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_STATIONS: stations})
    return True
