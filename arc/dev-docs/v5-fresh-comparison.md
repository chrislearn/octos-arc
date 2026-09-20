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

## Results: frozen revision `783908cb`

Both model runs used this exact archived revision, not the later hardening below.
Independent grades used untouched final applications in disposable copies. Both
grades executed all 32 specs with no build/report error.

| Model | Independent score | Run seconds | API requests | Input tokens | Output tokens | Reported total tokens | Input cache hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DeepSeek v4 Flash | 0/32 | 1807 | 24 | 454358 | 330288 | 784646* | 52.91% |
| Qwen3.7 Plus | 20/32 | 1808 | 33 | 663319 | 111172 | 774491 | 23.89% |

\* DeepSeek had one HTTP 502 response without usage. Its total is reported usage,
not proof of the complete billed amount. Qwen reported usage for every request;
all its recorded requests explicitly had `enable_thinking=false`. Neither
provider supplied a usable reasoning-token breakdown here.

This is **not a demonstrated time or total-token improvement**. Both consumed
their time allowance. Qwen's reported output was 66.3% lower, but its input was
46.0% higher; reported total tokens were only 1.3% lower (subject to the missing
DeepSeek usage). One fresh run per model cannot establish a stable model ranking.

### What actually happened

- DeepSeek: 23 generation requests after design. At the first full suite, six
  leaves were recorded as generated, 12 partial, five deferred, and nine had
  not reached generation. The first suite was 0/32 and took about 336 seconds;
  essentially no model-repair time remained. Independent grading was also
  0/32, about 334 seconds. Generation output repeatedly reached its limit.
  One captured reply contained 256 EDIT blocks, 114 identical replacements and
  222 repeated blocks. Another had 52 no-op edits out of 53. Six generation
  replies failed anchor validation. Splitting alone did not cure degeneration.
- Qwen: all 32 leaves were attempted in 15 applied waves (27 complete, five
  partial), with 23 generation requests after design. It often put a whole
  file inside an EDIT envelope without SEARCH/REPLACE; a bounded format retry
  usually helped, but some groups still needed splitting. Its first suite was
  also 0/32, about 333 seconds. Nine repair requests followed. Codegen patches
  eventually corrected the imports and other issues; the final tool fallback
  timed out without edits. Independent grading improved to 20/32, about 123
  seconds. The earlier switch-to-tools log was not itself a successful repair.
- Both generated `import * as Dialog/DropdownMenu from 'radix-ui'`, then used
  `.Root`. The installed aggregate package has no top-level `Root`, whereas
  its `Dialog.Root` and `DropdownMenu.Root` exports exist. The browser reported
  React error #130. The existing build accepted missing namespace exports as
  warnings, so an application that built successfully could blank every page.
- The shared-runtime repair classifier looked only at assertion messages, not
  the separately captured browser diagnostics. A locator timeout therefore hid
  the underlying shared React failure. Its fixed admission floor also failed
  to use the measured suite reserve and short-codegen repair allowance.
- The compact tool prompt was exercised: its initial user message was 18312
  characters versus approximately 78000–88000 for codegen repair snapshots.
  That tool request timed out, so this is context-size evidence, not evidence
  that compact tools caused the score improvement.
- Replaying the previous five-failure report: old `[:8000]` retained only two
  failure headers; balanced compression retained all five in 7996 characters.

### Remaining Qwen failures

REQ-2.6.1 (existing-note color); REQ-2.7.1, 2.7.2, 2.7.4, 2.7.5 and 2.7.6.1–3
(label assignment/removal, creation, editing and filtered views); REQ-2.8.1–2
(pin/unpin); REQ-3.1 (suggested filters); REQ-6.1 (sidebar items/styling).

The observations include missing target records/controls and an unchanged
color snapshot. Card action buttons remain simultaneously visible, while the
acceptance helpers hover one record and then select the first matching action;
this is a concrete risk of acting on another record and contaminating later
tests. Do not assume every missing-target failure is absent seed data: some
required records exist in the delivered store. Isolated action/state tracing
is still needed to attribute every remaining failure. No test assertions or
generated application files were patched to inflate these grades.

## Additional hardening after freezing the comparison

The working branch includes these evidence-driven fixes, **not present in the
two paid runs above**:

1. The Vite blueprint treats `MISSING_EXPORT` as a build failure with the source
   location. Other warnings still follow normal handling. A disposable copy of
   the actual DeepSeek output, with only this build config changed, failed in
   **521 ms** at `NoteCard.jsx:163:22`, identifying the missing `Root` export.
   This proves early detection, not a predicted future acceptance score.
2. Shared-runtime repair includes captured browser diagnostics and recognizes
   exact TypeError/React runtime signatures. Identical assertion timeouts alone
   still do not qualify; distinct exception signatures are not merged. Edits
   still require full verification with rollback on regression/unknown results.
3. Startup/shared repair admission uses the phase repair minimum plus the
   measured final-suite reserve, and limits repair time to preserve that reserve.
4. The compact output protocol explicitly distinguishes EDIT from whole-file
   content and forbids identical/repeated edits. It was shortened to keep the
   existing 6600-character context-budget regression test passing unchanged.

No second paid fresh run was added after these fixes. Their verification is
local unit/integration regression and the real failed-build replay, **not a new
DeepSeek/Qwen end-to-end score**.

## Verification and artifacts

Final working-code review: **654 tests passed in 82.526 seconds**, with real npm,
Vite, Playwright, proxy and bundle integration enabled; no skipped tests.
`git diff --check` was clean. Frozen pre-run review passed 649 tests (17 optional
integration tests skipped in that final fast pass; the later full review covers
the current code including the extra fixes).

Artifacts: `arc/arc-output/v5-fresh-20260921/`, including both metrics/usage/flow
logs, original generated frontend/backend archives, independent grade reports,
captured DeepSeek truncated replies, build-guard replay and full review logs.
The frozen adapter is reproducible with `git archive 783908cb arc`; the local
snapshot used was `/tmp/arc-v5-fresh.9FWU7s/arc`. Credentials were read from the
existing local configuration and are not copied into these artifacts.
