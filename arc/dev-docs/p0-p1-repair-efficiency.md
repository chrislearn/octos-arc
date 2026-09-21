# P0/P1 repair-efficiency changes

Scope: task-independent harness changes on `v5`. P2 model switching,
multi-candidate search, additional model services, and default thinking changes
are deliberately excluded. Acceptance specifications are unchanged.

## Stages

1. `0869c3e6`: source-scoped tool routing, retained current small source quotations,
   bounded dependency/caller/component-prop index.
2. `33e69c6c`: concrete-runtime-error / source-ownership failure groups,
   related regression selection, conservative global escalation, short-window
   fallback admission guard.
3. `34790095`: bounded version-validated repair observations, separately labelled
   measured versus unmeasured outcomes, duplicate and covered-range read masking.
4. Generation-batch syntax/build gates, final integration fixes, and regression
   verification. This stage also binds routing to actual source candidates, so a
   large backend entry quoted merely as context cannot override a small target.

## Invariants and limits

- File relationships are heuristic, not a JavaScript/TypeScript semantic proof.
  Displayed direct callers, signatures, routes, and component props guide edits;
  they are not hard file-access restrictions. Transitive callers inform regression
  selection. Unknown ownership and backend/shared/config/data changes escalate.
- An identical generic timeout is not evidence of an identical root cause.
  Unknown failures remain a fallback group. Group scheduling is round-robin by
  visit count, prioritizing larger groups among equally visited candidates.
  Groups are packed into the remaining configured repair rounds; the last round
  can cover all remaining groups instead of silently starving late groups. This
  does not increase the configured round or request limits.
- The complete original requirement constraints remain in full-suite tool repair
  prompts, including constraints belonging to currently passing features.
- Targeted checks do not certify the full application. Related regression checks
  run after applied target repairs; final full-suite measurement, confirmation,
  and best-checkpoint restoration remain authoritative. No passing-result cache
  replaces testing. Thus full-suite costs are intentionally retained.
- Repair records contain harness observations, not a model-generated diagnosis.
  They are bounded to eight records; at most three applicable records enter a
  prompt. Any application source, data, manifest or lockfile change invalidates
  the previous version's observations conservatively. Hashes stay out of prompts.
  Records do not persist an entire conversation across a new run.
- Covered-range masking requires actual matching numbered lines. Distinct or
  changed observations remain available; the latest result is never removed.
- Early generation checks have a 30-second batch budget, do not install packages,
  and do not start servers. Frontend builds require dependency readiness; absent
  dependencies, unsupported syntax, and timeouts are not fabricated failures.
  They are deferred to normal acceptance. Pending checker errors are supplied to
  the next batch without an extra model call. Early checks are not acceptance.

## Verification and interpretation

New tests cover source routing, caller closure, fault grouping, conservative
regression selection, dependency-version invalidation, overlapping read masking,
and generation checks. Existing protected-file, repair-budget, partial-write,
best-checkpoint, packaging, npm and browser integration tests remain relevant.

Use `generation_gate`, `repair_group`, `repair_memory`, `affected_regression`,
existing `structured_edit`, and provider-usage records to attribute subsequent
benchmarks. Compare frozen baseline/candidate sources on the same app snapshot,
provider, time/token budgets and independent final grader. Report input, cached
input, output, missing usage, elapsed time and final pass count separately.

Unit/integration correctness does not demonstrate improved model token use or
ARC pass rate. No new paid DeepSeek/Qwen A/B result is claimed by this change.

Final verification: **704 tests passed**, 79.362 seconds, with
`ARC_TEST_NPM_INTEGRATION=1` and both Playwright-root variables pointing to
`arc/local-grader`. This includes isolated bundle imports. Existing stdio
ResourceWarnings remain visible; they did not fail the suite. `git diff --check`
also passed. Test-generated root metrics were restored to their pre-test state.
