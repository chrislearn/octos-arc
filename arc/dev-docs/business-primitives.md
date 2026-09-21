# Task-neutral business primitives (2026-09-21)

This update extends the fresh-app blueprint, not any benchmark task, official
test, generated application, or external database. Existing/evolution apps are
not rewritten. The installed helpers are omitted from model source quotations
while pristine; their short API contract appears in the generation prompt.

## Included

- `collection(name, {idKey, initial, migrations, normalize})` retains its
  `all/list/get/create/patch/remove` API. The optional synchronous `normalize`
  callback receives a copy of a record and must return an object with the same
  ID. It is used on reads, create, patch, and before/after `transact`. This can
  supply task-specified shape defaults without embedding any field or fixture
  in the blueprint. Reads do not persist normalization: use an explicit,
  versioned migration when stored bytes themselves must change.
- `transact(items => result)` runs one synchronous read-modify-write of one
  collection. It checks the resulting records for unique, present IDs. A
  callback error, invalid result, or async callback leaves the file unchanged.
  It does **not** provide cross-file or multi-process transactions; related
  effects spanning collections must be modeled in one aggregate or use a real
  transactional store chosen for the application.
- `HttpError(status, message)` expresses only explicit 4xx errors. The existing
  Express entry maps them to `{error: message}` and hides 5xx details. The
  frontend `requestJson` helper now exposes that message and HTTP status while
  preserving its raw-data-on-success contract.

These helpers write only the generated application's local
`backend/data/<collection>.json` when a mutating method runs. They never connect
to MySQL, PostgreSQL, an external API, or a benchmark database.

## Deliberately not included

No prebuilt CRUD HTTP endpoints, account schema, authentication policy, seed
records, entity fields, validation rules, lifecycle states, labels, prices, or
expected test outputs. Even ordinary CRUD routes may require different ownership,
status codes, request shapes, and commit behavior. The model still writes those
task-specific choices. The collection itself is the parameterized CRUD template;
installing a universal route factory would hide too many business decisions.

## Evaluation boundary

Local tests cover shape consistency, create/patch/remove, multi-record atomic
changes, failed-transaction rollback, HTTP error construction, response error
parsing, and prompt/scaffold integration. This verifies the primitive contracts,
not benchmark pass rate or token savings. A comparable paid A/B run should hold
model, requirements, public specs, budget, and grading fixed, then compare final
independent acceptance, total/input-cache-miss/output tokens, request count, and
wall time. Cache-hit percentage alone is not a success criterion.
