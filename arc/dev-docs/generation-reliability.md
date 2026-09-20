# Generation reliability after v5.3

## Changes

- Complete suite measurements now preserve a clean, committed delivery checkpoint.
  Only complete non-interrupted observations qualify. On permanent provider failure,
  preserve partial repair sources in a separate commit, restore the best measured
  application, and rebuild per-node verdicts from that measurement. If preservation
  fails, do not clean or overwrite the interrupted work. A recovered artifact returns
  exit code 0 to allow grading but still emits `run_failed`; it never claims all tests
  passed. Without a useful checkpoint, the fatal exit remains. Platform acceptance
  of this degraded handoff still needs a cloud run; source recovery is tested locally.
- Generation estimates output needs separately from input context. Default waves
  have at most 6 leaves and are halved before calling the model until their estimated
  output fits 60% of the configured output cap. Estimate: 3500 shared tokens + 3500
  per leaf + description chars/4 + spec chars/8. This is a conservative heuristic,
  not a token count or guarantee. Smaller waves can increase successful generation
  requests; the intended saving is avoiding truncated/discarded generations.
  `OCTOS_ARC_CODEGEN_OUTPUT_TOKENS` overrides the planning budget (clamped to output
  limits). Implement-route output caps are respected conservatively. A single leaf
  still gets the existing bounded fallback; input safeguards and dependency order stay.
- Invalid design JSON/schema gets one compact correction within the original design
  deadline, capped at 120 seconds. Transport failures do not buy another design turn.
- Domain-neutral adapters: `backend/lib/query.js` distinguishes absent/false query
  flags and combines constraints without unrelated visibility defaults. React
  `shared/interactions.jsx` supplies a Radix Dialog surface that isolates bubbling
  and a duplicate-submit guard returning explicit success/failure. Neither chooses
  business fields, save/cancel semantics, ownership, fixtures or expected outcomes.
- Design/prompt contracts cover server/client visibility, inverse transitions,
  multi-select lifetime, Portal bubbling, retained drafts and menu-to-dialog focus.
  Helpers are omitted from repeated source quotes while pristine.
- Explicit `OCTOS_ARC_MAX_TOTAL_TOKENS_ABS` is checked by the proxy before every
  upstream completion, including tool-loop requests. Requests already in flight may
  exceed the threshold; accounting depends on upstream usage reports. Blocked calls
  return a clearly identified local-budget error without contacting the provider.
  Usage counters work even if file logging is disabled. Normal adaptive token guard
  remains a soft wind-down mechanism, not a monetary ceiling.
- `run-task-local.py --api-config PATH` reads api_key/base_url/model without shell
  evaluation or printing credentials. Configuration and generated runs are not bundled.

## Checks

Python regression includes clean/dirty checkpoint eligibility, actual git recovery
with retained interrupted edits, planning before generation, routed output caps,
design retry bounds, all boolean filter combinations, and per-request absolute cap.
Real Chromium checks multi-selection, no parent-card activation, failed-save draft
retention, explicit success handling, duplicate submission, Escape and focus restoration.
Existing framework/library build tests still run with non-local browser traffic blocked.

Local fixtures test adapters, not the benchmark's business result. No official task
or acceptance spec was modified. Cloud token/latency/score improvements are unproven
until comparable real runs; see local experiment results when available.

## Default limits (Python orchestration)

| Scope | Default |
| --- | --- |
| Whole platform run | max(3600, 1500 × leaves) seconds; local runner defaults to 3600 |
| Model turn / design | 1200 / 420 seconds |
| Node total | 1500 seconds baseline, banked savings up to 3000; explicit override is hard |
| Node repair rounds | 3 for >2 leaves, otherwise 5 |
| Final suite | 3 passes × up to 3 repair rounds, plus measurement/confirmation |
| Tool requests per turn | 20 for small tasks; large tasks unlimited unless configured |
| Codegen requests per turn | 3 |
| Soft total token guard | max(6 million, 2.5 million × leaves) |
| Model turn guard | max(24, 4 × leaves) |
| Absolute token threshold | disabled unless explicitly configured |

Timeout, no-change and repeated-failure stopping can cut these short. Checkpoints,
startup repair and rehearsal have additional bounded loops: a node's repair count
is not the total number of repair calls in a run.
