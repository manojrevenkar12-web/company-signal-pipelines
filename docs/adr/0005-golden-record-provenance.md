# 5. Golden records keep the source, date and reason of every field

## Decision
Each field has a source priority in config:

- names: CRM, then register, then vendor;
- status: register, then press, then vendor, then jobs.

Within a source the freshest value wins. Values past `max_age_days` are used only when nothing fresher exists. A
terminal status (acquired, shut down) from any trusted source beats a fresher "active", because companies do not
come back from either. `core.field_value` stores the value, source, observed date and reason, and the API shows
them.

## Consequences
After a rebrand the vendor keeps the old name for weeks. Register priority fixes the name. The status quo's
"last write wins" lets the vendor's stale "active" overwrite an acquisition.
