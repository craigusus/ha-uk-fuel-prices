"""Constants for the UK Fuel Prices integration."""

DOMAIN = "uk_fuel_prices"

TOKEN_URL = "https://www.fuel-finder.service.gov.uk/api/v1/oauth/generate_access_token"
PRICES_URL = "https://www.fuel-finder.service.gov.uk/api/v1/pfs/fuel-prices"
STATIONS_URL = "https://www.fuel-finder.service.gov.uk/api/v1/pfs"

CONF_PRICE_THRESHOLD_LOW = "price_threshold_low"
CONF_PRICE_THRESHOLD_HIGH = "price_threshold_high"
DEFAULT_PRICE_THRESHOLD_LOW = 140
DEFAULT_PRICE_THRESHOLD_HIGH = 155

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_STATIONS = "stations"
CONF_STATION_NAME = "name"
CONF_BATCH = "batch"
CONF_NODE_ID = "node_id"
CONF_FUEL_TYPES = "fuel_types"

FUEL_TYPES = ["E5", "E10", "B7_STANDARD", "B7_PREMIUM"]

FUEL_TYPE_LABELS = {
    "E5": "E5 Premium Unleaded",
    "E10": "E10 Unleaded",
    "B7_STANDARD": "Diesel",
    "B7_PREMIUM": "Premium Diesel",
}

CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 1800  # 30 minutes in seconds

TOKEN_EXPIRY_BUFFER_SECONDS = 60
STATION_METADATA_CACHE_SECONDS = 86400  # Refresh station metadata once per day
SEARCH_MAX_BATCH = 15
