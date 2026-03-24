"""Config flow for UK Fuel Prices integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_BATCH,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_FUEL_TYPES,
    CONF_NODE_ID,
    CONF_PRICE_THRESHOLD_HIGH,
    CONF_PRICE_THRESHOLD_LOW,
    CONF_STATION_NAME,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_PRICE_THRESHOLD_HIGH,
    DEFAULT_PRICE_THRESHOLD_LOW,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FUEL_TYPE_LABELS,
    SEARCH_MAX_BATCH,
    STATIONS_URL,
    TOKEN_URL,
)


_LOGGER = logging.getLogger(__name__)


async def _validate_credentials(hass, client_id: str, client_secret: str) -> str | None:
    """Try to fetch a token. Returns error key string on failure, None on success."""
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "fuelfinder.read",
            },
        ) as resp:
            if resp.status == 401:
                return "invalid_credentials"
            if resp.status == 429:
                return "rate_limited"
            if resp.status != 200:
                return "cannot_connect"
    except Exception:
        return "cannot_connect"
    return None


async def _search_stations(hass, client_id: str, client_secret: str, search_term: str) -> list[dict]:
    """Search for stations using the stations API across all batches."""
    session = async_get_clientsession(hass)

    try:
        async with session.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "fuelfinder.read",
            },
        ) as resp:
            if resp.status != 200:
                return []
            body = await resp.json()
        token = body["data"]["access_token"]
    except Exception:
        return []

    headers = {"Authorization": f"Bearer {token}"}
    semaphore = asyncio.Semaphore(5)
    term = search_term.lower()

    async def _fetch_batch(batch: int) -> tuple[int, list]:
        async with semaphore:
            try:
                async with session.get(
                    f"{STATIONS_URL}?batch-number={batch}",
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        return batch, []
                    data = await resp.json()
                    return batch, data if isinstance(data, list) else []
            except Exception:
                return batch, []

    batch_results = await asyncio.gather(
        *[asyncio.ensure_future(_fetch_batch(b)) for b in range(1, SEARCH_MAX_BATCH + 1)]
    )

    matches = []
    for batch, stations in batch_results:
        for s in stations:
            if not isinstance(s, dict):
                continue
            location = s.get("location") or {}
            searchable = " ".join(filter(None, [
                s.get("brand_name", ""),
                s.get("trading_name", ""),
                location.get("postcode", ""),
                location.get("address_line_1", ""),
                location.get("city", ""),
            ])).lower()
            if term in searchable:
                matches.append({
                    "node_id": s["node_id"],
                    "name": s.get("trading_name", ""),
                    "brand": s.get("brand_name") or None,
                    "postcode": location.get("postcode") or None,
                    "address": location.get("address_line_1") or None,
                    "city": location.get("city") or None,
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                    "batch": batch,
                })

    return matches


class FuelFinderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup: credentials."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _validate_credentials(
                self.hass, user_input[CONF_CLIENT_ID], user_input[CONF_CLIENT_SECRET]
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="UK Fuel Prices",
                    data={
                        CONF_CLIENT_ID: user_input[CONF_CLIENT_ID],
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                    },
                    options={CONF_STATIONS: []},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLIENT_ID): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_CLIENT_SECRET): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FuelFinderOptionsFlow(config_entry)


class FuelFinderOptionsFlow(OptionsFlow):
    """Manage stations after initial setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._stations: list[dict] = list(
            config_entry.options.get(CONF_STATIONS, [])
        )
        self._new_station: dict = {}
        self._search_results: list[dict] = []
        self._edit_index: int | None = None

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        """Handle configuration from the device page Configure button."""
        device_id = self.context.get("device_id")
        device_reg = dr.async_get(self.hass)
        device_entry = device_reg.async_get(device_id)

        node_id = next(
            (identifier[1] for identifier in device_entry.identifiers if identifier[0] == DOMAIN),
            None,
        )

        self._edit_index = next(
            (i for i, s in enumerate(self._stations) if s["node_id"] == node_id),
            None,
        )

        if self._edit_index is None:
            return self.async_abort(reason="device_not_found")

        return await self.async_step_edit_station(user_input)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        """Show current stations and offer to add/remove."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "search":
                return await self.async_step_search_station()
            if action == "add":
                return await self.async_step_add_station()
            if action == "thresholds":
                return await self.async_step_thresholds()
            if action == "settings":
                return await self.async_step_settings()
            if action and action.startswith("edit_"):
                self._edit_index = int(action.split("_")[1])
                return await self.async_step_edit_station()
            # Save with no changes
            return self.async_create_entry(
                title="", data={CONF_STATIONS: self._stations}
            )

        station_list = "\n".join(
            f"{i + 1}. {s['name']}" for i, s in enumerate(self._stations)
        ) or "No stations configured yet."

        options = {"search": "Search for a station by name", "add": "Add a station manually", "thresholds": "Configure price thresholds", "settings": "Update interval"}
        for i, s in enumerate(self._stations):
            options[f"edit_{i}"] = f"Edit: {s['name']}"
        options["save"] = "Save and close"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="save"): SelectSelector(
                        SelectSelectorConfig(
                            options=[{"value": k, "label": v} for k, v in options.items()],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"stations": station_list},
        )

    async def async_step_search_station(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        """Search for a station by name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            search_term = user_input.get("search_term", "").strip()
            if search_term:
                self._search_results = await _search_stations(
                    self.hass,
                    self._config_entry.data[CONF_CLIENT_ID],
                    self._config_entry.data[CONF_CLIENT_SECRET],
                    search_term,
                )
                if self._search_results:
                    return await self.async_step_search_results()
                errors["base"] = "no_stations_found"

        return self.async_show_form(
            step_id="search_station",
            data_schema=vol.Schema(
                {
                    vol.Required("search_term"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_search_results(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        """Pick a station from the search results."""
        if user_input is not None:
            key = user_input["station"]
            batch_str, node_id = key.split(":", 1)
            station = next(
                s for s in self._search_results
                if s["node_id"] == node_id and s["batch"] == int(batch_str)
            )
            self._new_station = {
                CONF_STATION_NAME: station["name"],
                "batch": station["batch"],
                "node_id": station["node_id"],
                "name": station["name"],
                "brand": station.get("brand") or None,
                "postcode": station.get("postcode") or None,
                "address": station.get("address") or None,
                "latitude": station.get("latitude"),
                "longitude": station.get("longitude"),
            }
            return await self.async_step_add_fuel_types()

        options = []
        for s in self._search_results:
            name = s["name"]
            brand = s.get("brand", "")
            postcode = s.get("postcode", "")
            city = s.get("city", "")
            label = f"{name} ({brand})" if brand and brand.upper() != name.upper() else name
            details = ", ".join(filter(None, [postcode, city]))
            if details:
                label = f"{label} — {details}"
            options.append({"value": f"{s['batch']}:{s['node_id']}", "label": label})

        return self.async_show_form(
            step_id="search_results",
            data_schema=vol.Schema(
                {
                    vol.Required("station"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"count": str(len(self._search_results))},
        )

    async def async_step_edit_station(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        """Edit fuel types for an existing station, or remove it."""
        station = self._stations[self._edit_index]

        if user_input is not None:
            self._stations[self._edit_index] = {
                **station,
                CONF_FUEL_TYPES: user_input[CONF_FUEL_TYPES],
            }
            return self.async_create_entry(
                title="", data={CONF_STATIONS: self._stations}
            )

        return self.async_show_form(
            step_id="edit_station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FUEL_TYPES, default=station.get(CONF_FUEL_TYPES, [])): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": k, "label": v}
                                for k, v in FUEL_TYPE_LABELS.items()
                            ],
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders={"station": station["name"]},
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        """Configure global price level thresholds."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_STATIONS: self._stations,
                    CONF_PRICE_THRESHOLD_LOW: int(user_input[CONF_PRICE_THRESHOLD_LOW]),
                    CONF_PRICE_THRESHOLD_HIGH: int(user_input[CONF_PRICE_THRESHOLD_HIGH]),
                },
            )

        current_low = self._config_entry.options.get(CONF_PRICE_THRESHOLD_LOW, DEFAULT_PRICE_THRESHOLD_LOW)
        current_high = self._config_entry.options.get(CONF_PRICE_THRESHOLD_HIGH, DEFAULT_PRICE_THRESHOLD_HIGH)

        return self.async_show_form(
            step_id="thresholds",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRICE_THRESHOLD_LOW, default=current_low): NumberSelector(
                        NumberSelectorConfig(min=50, max=300, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="p")
                    ),
                    vol.Required(CONF_PRICE_THRESHOLD_HIGH, default=current_high): NumberSelector(
                        NumberSelectorConfig(min=50, max=300, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="p")
                    ),
                }
            ),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        """Configure the update interval."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **self._config_entry.options,
                    CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL]) * 60,
                },
            )

        current_minutes = self._config_entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL) // 60

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPDATE_INTERVAL, default=current_minutes): NumberSelector(
                        NumberSelectorConfig(min=5, max=1440, step=5, mode=NumberSelectorMode.BOX, unit_of_measurement="min")
                    ),
                }
            ),
        )

    async def async_step_add_station(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        """Step 1 of adding a station: name, batch, node_id."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._new_station = {
                CONF_STATION_NAME: user_input[CONF_STATION_NAME],
                "batch": int(user_input[CONF_BATCH]),
                "node_id": user_input[CONF_NODE_ID].strip(),
                "name": user_input[CONF_STATION_NAME],
            }
            return await self.async_step_add_fuel_types()

        return self.async_show_form(
            step_id="add_station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_NAME): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_BATCH): NumberSelector(
                        NumberSelectorConfig(min=1, max=100, mode=NumberSelectorMode.BOX)
                    ),
                    vol.Required(CONF_NODE_ID): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_add_fuel_types(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        """Step 2 of adding a station: choose fuel types to track."""
        if user_input is not None:
            self._new_station[CONF_FUEL_TYPES] = user_input[CONF_FUEL_TYPES]
            self._stations.append(self._new_station)
            return self.async_create_entry(
                title="", data={CONF_STATIONS: self._stations}
            )

        return self.async_show_form(
            step_id="add_fuel_types",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FUEL_TYPES, default=["E10", "B7_STANDARD"]): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": k, "label": v}
                                for k, v in FUEL_TYPE_LABELS.items()
                            ],
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={"station": self._new_station.get(CONF_STATION_NAME, "")},
        )
