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