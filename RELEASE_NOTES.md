## v1.0.7

### Bug Fixes

- **Station not found during incremental refresh** — when an incremental fetch returned an empty batch (meaning "no changes since last run"), the cross-batch fallback search incorrectly treated that empty result as confirmation the station was absent. It now re-fetches those batches fully so stations that haven't changed are still found correctly.
- **Increased batch search ceiling** — the maximum number of batches searched when locating a missing station has been raised from 15 to 80, matching the API's real-world scale (~7,900 stations).

---

## v1.0.6

### Bug Fixes

- **Suppress spurious incremental-fetch warnings** — batches 7-10 (and others) can return HTTP 404 when no price changes exist since the `effective-start-timestamp`. The fallback to a full fetch always recovers correctly; the warning is now logged at DEBUG level instead of WARNING to keep logs clean.
- **Permanently closed station no longer warns** — stations marked as permanently closed in the Fuel Finder API no longer produce a WARNING when not found in any price batch. The event is now logged at INFO level with a clearer message.

---

## v1.0.5

### Improvements

- **Global 429 rate-limit cooldown** — when any config entry receives a rate-limit response from the Fuel Finder API, all instances now pause together until the cooldown elapses. This prevents multiple config entries from compounding a rate-limit violation against each other. The `Retry-After` header is respected where provided.
- **Incremental price refresh** — after the first successful update, subsequent polls only request stations with price changes since the last run using `effective-start-timestamp`. This significantly reduces API load on hourly updates.
- **`price_is_stale` sensor attribute** — each fuel price sensor now exposes a `price_is_stale` boolean attribute. It is `true` when `price_last_updated` is older than 24 hours, `false` when fresh, and `null` when no timestamp is available. Use this in automations to alert on stations that haven't reported recently.

---

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