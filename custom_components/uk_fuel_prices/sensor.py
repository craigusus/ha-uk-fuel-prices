"""UK Fuel Prices sensor entities."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.location import distance as haversine_distance

from .const import (
    CONF_FUEL_TYPES,
    CONF_PRICE_THRESHOLD_HIGH,
    CONF_PRICE_THRESHOLD_LOW,
    CONF_STATIONS,
    DEFAULT_PRICE_THRESHOLD_HIGH,
    DEFAULT_PRICE_THRESHOLD_LOW,
    DOMAIN,
    FUEL_TYPE_LABELS,
)
from .coordinator import FuelFinderCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UK Fuel Prices sensors from a config entry."""
    coordinator: FuelFinderCoordinator = hass.data[DOMAIN][entry.entry_id]
    stations = entry.options.get(CONF_STATIONS, [])
    threshold_low = entry.options.get(CONF_PRICE_THRESHOLD_LOW, DEFAULT_PRICE_THRESHOLD_LOW)
    threshold_high = entry.options.get(CONF_PRICE_THRESHOLD_HIGH, DEFAULT_PRICE_THRESHOLD_HIGH)

    entities = [
        FuelPriceSensor(coordinator, station, fuel_type, threshold_low, threshold_high)
        for station in stations
        for fuel_type in station.get(CONF_FUEL_TYPES, [])
    ]
    async_add_entities(entities)

    # Remove devices for stations that are no longer configured
    station_ids = {station["node_id"] for station in stations}
    device_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
        for identifier in device.identifiers:
            if identifier[0] == DOMAIN and identifier[1] not in station_ids:
                device_reg.async_remove_device(device.id)
                break


class FuelPriceSensor(CoordinatorEntity, SensorEntity):
    """A sensor representing the price of a single fuel type at a single station."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "p"
    _attr_icon = "mdi:gas-station"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FuelFinderCoordinator,
        station: dict,
        fuel_type: str,
        threshold_low: int,
        threshold_high: int,
    ) -> None:
        super().__init__(coordinator)
        self._station = station
        self._fuel_type = fuel_type
        self._threshold_low = threshold_low
        self._threshold_high = threshold_high
        self._attr_unique_id = f"{station['node_id']}_{fuel_type}"
        self._attr_name = FUEL_TYPE_LABELS.get(fuel_type, fuel_type)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, station["node_id"])},
            "name": station["name"],
            "manufacturer": "UK Government Fuel Finder",
            "model": "Fuel Station",
            "entry_type": "service",
        }

    @property
    def native_value(self) -> float | None:
        """Return the current fuel price in pence."""
        if not self.coordinator.data:
            return None
        station_data = self.coordinator.data.get(self._station["node_id"])
        if not station_data:
            return None
        fuel_data = station_data["prices"].get(self._fuel_type)
        return fuel_data["price"] if fuel_data else None

    @property
    def extra_state_attributes(self) -> dict:
        """Return price last updated timestamp and other metadata."""
        if not self.coordinator.data:
            return {}
        station_data = self.coordinator.data.get(self._station["node_id"])
        if not station_data:
            return {}
        fuel_data = station_data["prices"].get(self._fuel_type, {})
        price = self.native_value
        if price is not None:
            if price < self._threshold_low:
                level = "low"
            elif price < self._threshold_high:
                level = "medium"
            else:
                level = "high"
        else:
            level = None

        attrs = {
            "price_last_updated": fuel_data.get("updated"),
            "fuel_type": self._fuel_type,
            "station_name": station_data.get("name"),
            "price_level": level,
        }

        for field in ("brand", "postcode", "address", "address_line_2", "city", "county", "country", "phone"):
            if station_data.get(field):
                attrs[field] = station_data[field]

        lat = station_data.get("latitude")
        lon = station_data.get("longitude")
        if lat is not None and lon is not None:
            try:
                attrs["latitude"] = float(lat)
                attrs["longitude"] = float(lon)
                dist_m = haversine_distance(
                    self.hass.config.latitude,
                    self.hass.config.longitude,
                    float(lat),
                    float(lon),
                )
                if dist_m is not None:
                    attrs["distance_miles"] = round(dist_m / 1609.344, 2)
            except (TypeError, ValueError):
                pass

        for field in ("is_motorway_service_station", "is_supermarket_service_station", "temporary_closure"):
            val = station_data.get(field)
            if val is not None:
                attrs[field] = val

        opening_hours = station_data.get("opening_hours")
        if opening_hours:
            attrs["opening_hours"] = opening_hours
            today = datetime.now().strftime("%A").lower()
            today_hours = opening_hours.get(today)
            if today_hours:
                attrs["opens_today"] = today_hours.get("open")
                attrs["closes_today"] = today_hours.get("close")
                attrs["is_24_hours_today"] = today_hours.get("is_24_hours", False)

        amenities = station_data.get("amenities")
        if amenities:
            attrs["amenities"] = amenities

        return attrs
