# Journey data accessibility workflow

## Purpose

The train-side controller is autonomous. The human workflow is asynchronous journey
audit: locating a run, understanding what happened, and exporting evidence without
having to perceive a fast 3D scene or live graph. AeroPINN therefore converts the same
telemetry that drives the dashboard into persistent, documented records usable with a
keyboard, screen reader, spreadsheet, script, or specialist accessibility tool.

## Automatic lifecycle

Each backend WebSocket simulation creates a journey automatically. There is no Record
button and no risk that an operator forgets to enable evidence collection. A normal
end marks the journey `COMPLETED`; records left open across a process restart become
`INTERRUPTED`. Running summaries checkpoint approximately once per second.

Every journey receives:

- a stable session ID and UTC timestamps;
- train, route, origin/destination, direction, track and scenario metadata;
- start/end GPS coordinates and route chainage;
- weather, ambient/wire temperature and wind documentation;
- compact plant/controller evidence at the native 1 kHz simulation step;
- complete nested dashboard telemetry at the approximately 30 Hz server stream rate;
- automatically indexed contact-loss, gust, estimator-fallback and actuator-limit
  transitions;
- every dashboard physics input as a timestamped event;
- model/control provenance already present in the telemetry frame.

SQLite stores the searchable catalogue and append-only NDJSON files store telemetry
and events. Set `AEROPINN_DATA_DIR` to relocate the persistent store. The default is
`data/journeys/`, which is intentionally excluded from Git.

## Accessible interface

Open **Journey Logs** without interacting with the 3D scene. The modal uses native
headings, labels, buttons, links, a data table, keyboard focus indicators, Escape to
close, and a polite live-status region. It provides text summaries and an explicitly
labelled field for every documentation value. Finished journeys can be archived or
permanently deleted only after typing the full session ID; deletion remains in the
catalogue audit log.

## Export formats

- CSV: flattened dotted columns for screen readers, spreadsheets and statistical
  tools.
- JSON: catalogue metadata, summary, events and complete nested telemetry.
- ZIP audit package: CSV and JSON telemetry/events, summary, manifest, data dictionary,
  README and SHA-256 hashes.

All generated sample and live demo records identify their data source as `SIMULATION`.
The deterministic bundled example uses the production Engine path: a nominal
Lastochka journey transitions into a 350 km/h high-wind section with reduced wire
tension, 3.5× turbulence and a transient gust. No hand-written outcome values are
inserted.

## API

- `GET /api/journeys`
- `GET /api/journeys/{id}`
- `PATCH /api/journeys/{id}/metadata`
- `POST /api/journeys/{id}/archive`
- `DELETE /api/journeys/{id}?confirm={id}`
- `GET /api/journeys/{id}/export?format=csv|json|audit`

The current implementation records both a compact 1 kHz physics stream and complete
dashboard frames at approximately 30 Hz. A train integration should preserve each
physical sensor's native timestamp and sample rate; the export schema must not pretend
heterogeneous sensors are perfectly synchronous.
