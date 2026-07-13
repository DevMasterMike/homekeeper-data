# homekeeper-data

Data companion for the HomeKeeper iOS app. Served via GitHub Pages from `docs/`.

## What's here

- **`docs/carseat-recalls.json`** — child car seat recalls. NHTSA regulates car
  seats (not CPSC) and offers no searchable API for them; a nightly GitHub
  Action downloads NHTSA's bulk flat file
  (`FLAT_RCL_POST_2010.zip`), filters to child-seat records
  (`RCLTYPECD == 'C'`), and publishes this compact feed. The app matches
  recalls by brand/model plus the seat's manufacture-date window
  (`BGMAN`/`ENDMAN`).
- **`docs/config.json`** — remote provider configuration for the app: lookup
  provider order, kill switches for lookup providers (`disabledProviders`)
  and recall sources (`disabledSources`), and an optional user-facing notice.
  Lets a dead or misbehaving free API be disabled without an App Store
  release. The app caches this for 24 h and falls back to a bundled copy.

## Operations

- The workflow runs nightly (06:17 UTC) and on manual dispatch.
- The feed script fails loudly (and publishes nothing) if the flat-file column
  layout stops validating.
- The app warns in Diagnostics if the feed is more than 8 days old.

Data source: U.S. National Highway Traffic Safety Administration (public domain).
