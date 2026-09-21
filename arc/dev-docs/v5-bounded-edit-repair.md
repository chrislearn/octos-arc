# Bounded native repair follow-up

## Changes

- Enforce a local, hard model-request limit instead of merely deleting tool
  schemas. The local terminal response has zero **local** usage, is not logged
  as provider usage, and cannot silently declare success: Flow explicitly marks
  the turn incomplete, restores protected files, and measures partial edits.
- Structured editing defaults to 8 requests and 4096 output tokens per request.
  Legacy repair turns default to 12 requests, independent of task size. Explicit
  environment overrides still work (legacy 0 means unlimited). These are
  per-turn limits, not a shared allowance across every fallback/repair round.
- During structured editing, replace superseded results of identical read_file
  arguments with an explicit omission marker. Keep the latest result, distinct
  line ranges, call ordering/ids, edit arguments and edit results. Do not infer
  that an old observation is still the current file.
- Add short repair guidance to inspect all callers of changed component props
  and callbacks, including alternative rendering branches, and preserve record
  shape invariants across seed/create/update/read. This is guidance, not an AST
  proof that all callers were updated. It adds no task-specific fixtures or rules.
- After reviewing the paid run, reject suite fallback when less than 30 seconds
  remain or a hard request limit has already terminated the attempt. Do not start
  an additional tool allowance to bypass that limit. Partial edits still go to
  acceptance. Both branches have offline regression coverage.
- Count actual upstream admissions, including model-routing fallback attempts,
  rather than relying solely on the number of kernel HTTP requests. Identical
  in-flight requests still share an admission. A route fallback cannot bypass
  the limit without another kernel request.

The real bundled kernel requires a usage object even on local terminal responses;
the fake-provider integration test covers this and an uncooperative provider that
continues requesting tools. It also verifies reset on the next turn. Flow's test
verifies that a local request cap is incomplete, not success or run-wide budget
exhaustion. Repeated-read tests preserve edit results even if tool ids are reused.

## Real-model check

One Qwen3.7 Plus repair-only experiment starts from the preceding final 18/32 app,
with unchanged requirements/traceability and official specs. Thinking is off,
one grading worker, 600-second harness allowance, 500,000-token admission guard,
900-second external watchdog. No hand edits to generated application code.
This is **not** a fresh-generation or old/new randomized comparison.

Frozen runtime source archive SHA256:
`fc68d5f948f222449714ca4566d0b76fb048a08cbcf7943d9ec8ebed6c42566d`.
Working source subsequently adds a conservative reused-call-id fix in read
compaction, the no-short-fallback rule and stricter upstream-admission counting,
with regression tests; the running
snapshot was not changed. These extra fixes are covered offline, not by this
frozen paid run.

The fresh baseline measurement reproduced 18/32 in 141 seconds. The first
structured repair issued exactly 8 provider requests, used 228,140 reported
tokens and took 159 seconds. The ninth request was handled locally, and the
turn was explicitly recorded as incomplete with partial edits.

## Results

| Measurement | Result |
| --- | ---: |
| Full-suite baseline | 18/32 |
| Full-suite after first bounded repair | 25/32 |
| Independent final full-suite grade | 25/32 |
| Harness duration reported by event metrics | 484 seconds |
| Provider requests | 13 (2 missing usage) |
| Reported input tokens | 286,829 |
| Reported output tokens | 4,347 |
| Reported total tokens | 291,176 |

The independent final grade executed all 32 specs with no build/report error.
Remaining failures: archive notification, color change/creation, label assignment/
removal/default assignment, detailed settings. Only the first repair changed files
(Sidebar.jsx and NoteCard.jsx); it made 16 reads and 2 edits. The next
repair read 20 times but made no changes before its 86-second time slice expired.
A subsequent one-second fallback also timed out; the added admission rule now
rejects that case. Both timed-out requests lack usage, so 291,176 is not proof of
the complete provider bill.

The request cap worked on real traffic, and the measured app improved by 7 specs.
This does **not** establish a fresh-generation improvement, superiority to the old
repair policy under the same checkpoint/budget, or a total-token reduction against
the preceding from-zero runs. No second model/full half-hour run was conducted
in this follow-up. The repeated-read compactor has deterministic regression
coverage; do not attribute the observed score gain or a measured token saving
to it without an ablation experiment.

Artifacts: `arc/arc-output/v5-bounded-repair-20260921/` contains frozen runtime
source, logs, request/event metrics, final generated application archive and the
independent grading report. Final working source additionally contains the three
offline-tested fixes documented above. No official tests or generated app code
were manually changed.

## Final verification

- Final working source: **675 tests passed in 81.177 seconds**, npm/browser
  integrations enabled; no skips reported. The final suite includes the real
  bundled-kernel limit test, route-fallback admission check, reused-id compaction
  test and the short-fallback rejection test.
- `git diff --check` passed. Existing unrelated workspace changes were preserved.
- `delivery-review.log` and `delivery-source.tar` in the artifact directory
  correspond to the final offline-tested source. `source.tar` is the earlier
  runtime snapshot used for the paid experiment; these are intentionally distinct.
- No git commit or release ZIP was created in this follow-up.
