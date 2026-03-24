"""DataUpdateCoordinator for UK Fuel Prices."""

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PRICES_URL,
    STATION_METADATA_CACHE_SECONDS,
    STATIONS_URL,
    TOKEN_URL,
    TOKEN_EXPIRY_BUFFER_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class FuelFinderCoordinator(DataUpdateCoordinator):
    """Fetches fuel prices from the UK Government Fuel Finder API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client_id: str,
        client_secret: str,
        stations: list[dict],
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self._client_id = client_id
        self._client_secret = client_secret
        self._stations = stations
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._station_metadata: dict[str, dict] = {}
        self._station_metadata_last_fetched: float = 0

    async def _get_token(self) -> str:
        """Return a valid access token, fetching a new one if necessary."""
        if self._token and time.time() < self._token_expires_at:
            return self._token

        session = async_get_clientsession(self.hass)
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "fuelfinder.read",
        }

        async with session.post(TOKEN_URL, data=data) as resp:
            if resp.status == 401:
                raise UpdateFailed("Invalid API credentials")
            if resp.status != 200:
                raise UpdateFailed(f"Token request failed with status {resp.status}")
            body = await resp.json()

        token_data = body["data"]
        self._token = token_data["access_token"]
        self._token_expires_at = (
            time.time() + token_data["expires_in"] - TOKEN_EXPIRY_BUFFER_SECONDS
        )
        _LOGGER.debug("Fetched new access token (expires in %ss)", token_data["expires_in"])
        return self._token

    async def _fetch_batch(self, token: str, batch: int) -> list:
        """Fetch a single batch of fuel price data."""
        session = async_get_clientsession(self.hass)
        async with session.get(
            f"{PRICES_URL}?batch-number={batch}",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            if resp.status == 401:
                raise UpdateFailed("Unauthorised — token rejected by API")
            if resp.status == 429:
                raise UpdateFailed("Rate limited by Fuel Finder API — will retry next interval")
            if resp.status != 200:
                raise UpdateFailed(f"Batch {batch} request failed with status {resp.status}")
            return await resp.json()

    async def _fetch_station_metadata(self, token: str) -> None:
        """Fetch rich station data from the stations API and cache it (refreshed daily)."""
        session = async_get_clientsession(self.hass)
        batches = list({s["batch"] for s in self._stations})
        metadata: dict[str, dict] = {}

        for batch in batches:
            async with session.get(
                f"{STATIONS_URL}?batch-number={batch}",
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Station metadata fetch failed for batch %s (status %s)", batch, resp.status)
                    continue
                stations = await resp.json()

            for s in stations:
                node_id = s.get("node_id", "")
                if not any(st["node_id"] == node_id for st in self._stations):
                    continue

                location = s.get("location") or {}
                amenities_list = s.get("amenities") or []

                usual_days = (s.get("opening_times") or {}).get("usual_days") or {}
                bank_holiday = (s.get("opening_times") or {}).get("bank_holiday") or {}
                opening_hours: dict = {}
                for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
                    day_data = usual_days.get(day) or {}
                    if day_data.get("open") or day_data.get("is_24_hours"):
                        opening_hours[day] = {
                            "open": day_data.get("open"),
                            "close": day_data.get("close"),
                            "is_24_hours": bool(day_data.get("is_24_hours")),
                        }
                if bank_holiday.get("open_time") or bank_holiday.get("is_24_hours"):
                    opening_hours["bank_holiday"] = {
                        "open": bank_holiday.get("open_time"),
                        "close": bank_holiday.get("close_time"),
                        "is_24_hours": bool(bank_holiday.get("is_24_hours")),
                    }

                metadata[node_id] = {
                    "city": location.get("city") or None,
                    "county": location.get("county") or None,
                    "country": location.get("country") or None,
                    "address_line_2": location.get("address_line_2") or None,
                    "phone": s.get("public_phone_number") or None,
                    "is_motorway_service_station": s.get("is_motorway_service_station"),
                    "is_supermarket_service_station": s.get("is_supermarket_service_station"),
                    "temporary_closure": s.get("temporary_closure"),
                    "opening_hours": opening_hours or None,
                    "amenities": {
                        "adblue_pumps": "adblue_pumps" in amenities_list,
                        "adblue_packaged": "adblue_packaged" in amenities_list,
                        "lpg_pumps": "lpg_pumps" in amenities_list,
                        "car_wash": "car_wash" in amenities_list,
                        "air_pump_or_screenwash": "air_pump_or_screenwash" in amenities_list,
                        "water_filling": "water_filling" in amenities_list,
                        "twenty_four_hour_fuel": "twenty_four_hour_fuel" in amenities_list,
                        "customer_toilets": "customer_toilets" in amenities_list,
                    } if amenities_list else None,
                }

        self._station_metadata = metadata
        self._station_metadata_last_fetched = time.time()
        _LOGGER.debug(
            "Station metadata cached for %s/%s configured stations. node_ids found: %s",
            len(metadata),
            len(self._stations),
            list(metadata.keys()),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch prices for all configured stations."""
        try:
            token = await self._get_token()
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Failed to get access token: {err}") from err

        # Refresh station metadata if cache is stale (once per day)
        if time.time() - self._station_metadata_last_fetched > STATION_METADATA_CACHE_SECONDS:
            try:
                await self._fetch_station_metadata(token)
            except Exception as err:
                _LOGGER.warning("Station metadata fetch failed, rich attributes unavailable: %s", err)

        # Deduplicate batches and fetch all in parallel
        batches = list({s["batch"] for s in self._stations})
        results = await asyncio.gather(
            *[self._fetch_batch(token, b) for b in batches],
            return_exceptions=True,
        )

        batch_data: dict[int, list] = {}
        for batch, result in zip(batches, results):
            if isinstance(result, Exception):
                raise UpdateFailed(f"Failed to fetch batch {batch}: {result}")
            batch_data[batch] = result

        # Extract prices for each configured station
        data: dict[str, Any] = {}
        for station in self._stations:
            station_list = batch_data.get(station["batch"], [])
            station_data = next(
                (s for s in station_list if s["node_id"] == station["node_id"]), None
            )
            if not station_data:
                _LOGGER.warning(
                    "Station '%s' (node_id: %s) not found in batch %s",
                    station["name"],
                    station["node_id"],
                    station["batch"],
                )
                continue

            prices: dict[str, Any] = {}
            for fp in station_data["fuel_prices"]:
                prices[fp["fuel_type"]] = {
                    "price": fp["price"],
                    "updated": fp["price_last_updated"],
                }

            api_location = station_data.get("location") or {}
            csv_meta = self._station_metadata.get(station["node_id"], {})

            data[station["node_id"]] = {
                "name": station_data["trading_name"],
                "prices": prices,
                "brand": station_data.get("brand") or station.get("brand") or None,
                "postcode": api_location.get("postcode") or station.get("postcode") or None,
                "address": api_location.get("address_line_1") or station.get("address") or None,
                "latitude": api_location.get("latitude") or station.get("latitude") or None,
                "longitude": api_location.get("longitude") or station.get("longitude") or None,
                # Enriched from stations API (refreshed daily)
                "address_line_2": csv_meta.get("address_line_2"),
                "city": csv_meta.get("city"),
                "county": csv_meta.get("county"),
                "country": csv_meta.get("country"),
                "phone": csv_meta.get("phone"),
                "is_motorway_service_station": csv_meta.get("is_motorway_service_station"),
                "is_supermarket_service_station": csv_meta.get("is_supermarket_service_station"),
                "temporary_closure": csv_meta.get("temporary_closure"),
                "opening_hours": csv_meta.get("opening_hours"),
                "amenities": csv_meta.get("amenities"),
            }

        return data
