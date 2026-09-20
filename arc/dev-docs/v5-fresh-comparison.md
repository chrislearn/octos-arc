# v5 bounded repair context and fresh-model comparison

## Scope

This iteration remains on v5, with thinking disabled. It adds no task-specific
fixtures and changes neither the official tests nor their assertions.

Changes:

- Allocate failure-evidence space across all failures before DOM detail. Keep
  browser diagnostics before large page snapshots; preserve head/tail of
  unstructured infrastructure errors. Use the same policy for node and suite
  repairs. Runtime evidence also informs source ranking.
- In tool-mode repair, replace the full inline source snapshot with a source
  index. Tools must read current files before editing. Keep requirements,
  test locations and bounded failure evidence.
- A reply identified as repetitive no longer gets an identical-format retry.
  Valid partial changes still get measured before more model work. Anchor
  failures include their concrete error in the rebuilt retry prompt.
- Generation recovery has a 16384-token default ceiling, distinct from the
  8192-token repair ceiling. Two clean applied generation replies exit recovery.
  Explicit `OCTOS_ARC_DEGENERATE_MAX_TOKENS` still overrides both unless the
  generation-specific `OCTOS_ARC_DEGENERATE_GENERATION_MAX_TOKENS` is set.
- Context-budget splits stay local to that group. Actual generation failures
  temporarily lower the wave ceiling; two successful waves increase it again,
  up to the configured ceiling. This avoids both permanent tiny waves and
  immediately repeating failed large batches.
- Post-rollback score fluctuations do not count as applied repair progress.
  Metrics explicitly identify measurements after restoration. Stop additional
  suite passes/model calls when the budget is winding down, while preserving
  the final-measurement path.
- Include the new evidence helper in deployment bundles.

## Experiment protocol

Freeze one adapter revision for both runs. Generate Keep from zero (no
`--template`, no previous generated frontend/backend), once per model:
`deepseek-v4-flash` and `qwen3.7-plus`. Run sequentially, with identical official
tests, thinking off, 1800-second harness budget and 2,000,000-token admission
limit. An in-flight request can exceed the token admission limit. A 2100-second
external watchdog bounds abnormal harness overrun; cleanup has a 90-second grace.

Independently grade each final application in a disposable copy, all 32 official
specs, one worker. Runtime and token comparisons exclude this separate grade.
Cache hits are provider-reported input cache tokens, not inferred from prompt
similarity. Missing reasoning-token counters do not prove zero reasoning cost.

One run per model is descriptive, not a statistically reliable ranking or a
controlled before/after estimate. The earlier 27/32 repair-only experiments are
not directly comparable to these fresh-generation runs.

Results will be appended after both executions and independent grades finish.
