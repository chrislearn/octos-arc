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
  and a duplicate-submit guard preserving the action's raw value/rejection contract. Neither chooses
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

## Follow-up after real local experiments

- Unify `requestJson()` and `useAsyncAction().run()` around raw resolved data or
  rejection. The original adapter's `{ok,value}` result confused generated calls
  to requestJson, causing successful HTTP reads to leave lists empty. Do not apply
  the new adapter contract to older/custom helpers: only advertise it when the
  installed source exactly matches the current blueprint.
- Every expanded editor has a visible completion action, even when it autosaves;
  keyboard/outside dismissal supplements this. Code generation previously omitted
  a Close action and the helper's fallback ran only after the test deadline.
- Dialog surfaces isolate click/keyboard bubbling, not pointerdown. A real-browser
  regression reproduced the old wrapper requiring a second outside click after a
  checkbox interaction; preserving Radix's pointer event path fixes it.
- Require final, non-overlapping patches rather than successive self-revisions,
  no-op edits or whole-function anchors for one-line changes. Explicit NO CHANGE
  advances a generation wave to verification, without claiming any tests passed.
- Completed bare `FILE frontend/...` sections can be normalized deterministically
  and then go through the normal write guards. Mixed/unsafe/duplicate/empty envelopes
  are rejected. EOF is never used to complete a truncated bare reply.
- Capture tools-disabled provider responses whose finish reason is `length` before
  the kernel discards their text. Retain only the current turn/label, save local
  diagnostics under `.arc/truncated-replies/`, and apply only terminated FILE/EDIT
  blocks through the existing guards. The turn remains incomplete, never successful.
  Invalid anchors still reject the staged edit set; recovery is not a bypass.
- On failed UI tests, record up to three successful JSON API response **shapes**
  (array length/object keys), not body values or query values. This helps distinguish
  empty server data from a client return-contract mistake. No assertion is changed.
- Metrics now separate phase usage, reasoning (already included in completion),
  missing usage, first whole-app measurement, repairs and protocol outcomes.
- Final-suite outer passes continue only when the preceding pass increased its
  measured pass count. Merely editing files does not reset a stalled retry budget.
  This deliberately trades another speculative retry for bounded work; within-pass
  changes of approach, regression rollback and green confirmation still remain.

The tool-request budget removes tools and requests a final answer when reached; it
is not a strict count of all subsequent HTTP retries. Use the explicit absolute
token threshold as the per-upstream-request guard. It is usage-based, not a prepaid
monetary limit, and cannot retroactively cancel an already issued provider request.

Local measurements and caveats: [local-reliability-experiment.md](local-reliability-experiment.md).
