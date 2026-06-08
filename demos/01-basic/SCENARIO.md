# Demo 01 — Basic status page

A small SaaS runs a self-hosted status page with STATUSKIT. The config in
`statuspage.json` describes four components (two in the `API` group, one
edge/CDN, one database), one **resolved** major incident with a full timeline,
one **active** partial-outage incident, and three subscribers — one global and
two scoped to specific components.

## Try it

```sh
# overall + per-component status (exit 1 because not all operational)
python -m statuskit status demos/01-basic/statuspage.json

# incident timeline (exit 1 because an incident is active)
python -m statuskit incidents demos/01-basic/statuspage.json

# uptime over trailing 30 days (downtime from major/critical incidents)
python -m statuskit --format json uptime demos/01-basic/statuspage.json

# who gets notified for the active incident inc-2026-002
python -m statuskit notify demos/01-basic/statuspage.json inc-2026-002

# CI/monitoring gate: non-zero exit when degraded or incidents are open
python -m statuskit check demos/01-basic/statuspage.json
```

## What to look for

- `status` rolls up the **worst** component (`major_outage`) as the page state.
- `notify` for `inc-2026-002` (touches `api-core`) returns the global subscriber
  plus the subscriber scoped to `api-core`, but **not** the CDN-only subscriber.
- `check` returns a non-zero exit code so it can fail a monitoring job or
  block a deploy while the page is unhealthy.
