## v1.0.4

### New Features

- **B10 and HVO fuel types** — B10 Biodiesel and HVO Renewable Diesel are now available as trackable fuel types when adding or editing a station.
- **Price effective timestamp** — sensor attributes now include `price_change_effective` alongside `price_last_updated`, showing when a price change became effective rather than just when it was submitted.
- **Permanent closure details** — `permanent_closure` and `permanent_closure_date` are now exposed as sensor attributes where available.

### Bug Fixes

- **Entities no longer go unknown during API outages** — transient server errors (HTTP 5xx) from the Fuel Finder API now preserve the last known prices instead of wiping all sensor values until the next successful poll.

---

## v1.0.3

### Bug Fixes

- **Permanent batch auto-correction** — when a station has moved to a different API batch, the correct batch is now automatically persisted to the integration config. No more repeated warnings on restart and no need to remove and re-add the station manually.

---

## v1.0.2

### Bug Fixes

- **Automatic batch reassignment recovery** — stations that have been moved to a different API batch since initial setup are now automatically found via a full batch scan. The corrected batch is cached in-memory for the session. Previously, affected stations would silently produce no data until the station was removed and re-added. To make the fix permanent across restarts, remove and re-add the affected station in the integration settings.

---

## v1.0.0

**Initial Release**