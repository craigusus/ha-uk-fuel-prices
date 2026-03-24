## v1.1.1

### Configurable Update Interval
You can now control how often the integration polls the Fuel Finder API.

Go to **Settings → Integrations → UK Fuel Prices → Configure → Update interval** to change it.

- Default remains **30 minutes** — no action required if you're happy with that
- Accepts values from **5 minutes** to **24 hours**

---

### Station Location & Distance
Stations added via search now store their GPS coordinates. Each fuel sensor exposes:

| Attribute | Description |
|---|---|
| `latitude` | Station latitude |
| `longitude` | Station longitude |
| `distance_miles` | Straight-line distance from your HA home location |

The `latitude` and `longitude` attributes allow stations to be shown on a Lovelace **Map card** — simply add the sensor entities to a map card in your dashboard.

---

### Richer Station Attributes
Sensors now expose additional metadata about each station where available:

| Attribute | Description |
|---|---|
| `brand` | Fuel brand/retailer (e.g. Tesco, BP, Shell) |
| `postcode` | Station postcode |
| `address` | Station street address |

---

## Upgrade Notes

> **Existing stations** added before this release will not have coordinates or address metadata until they are removed and re-added via the search flow.

- Update interval defaults to 30 minutes — unchanged, no action required
- No breaking changes
