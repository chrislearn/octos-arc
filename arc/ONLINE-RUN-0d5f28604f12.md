# Online run 0d5f28604f12: stalled progress, not a dead process

Inspected the authenticated run page and its generated files on 2026-09-21.
Source: https://arc-bench.com/runs/0d5f28604f12

## Observations

- The page reports cancellation by the user after 84m56s; platform evaluation was never reached.
- Agent started at 13:28:49 UTC with a 51,000-second allowance, 85,000,000-token guard and 136-turn guard. The platform explicitly waited for the container without a timeout.
- Requirements 1–3 passed. Requirement 4 generated 26 files, then failed startup because a migration did not have the required unique string id and synchronous up function.
- After a backend repair, login failed. A tool repair added an auth Context provider to `frontend/src/hooks/useAuth.js`; Vite reported `Expression expected` at line 47. Subsequent changes to the build scripts did not fix this source error.
- At 13:55:32 UTC the sequential loop deferred the other 30 requirements and switched to full-suite repair, without a path back to implementation.
- Final repair passes could repeat up to 136 times. The visible full-suite results were 3, 6, 6, 7, 6, 6 out of 34, with roughly five-minute measurements between repairs. No-change repairs still led to new passes.
- Last visible agent heartbeat was 14:53:24; container removed at 14:53:41 after cancellation. This is evidence of continued work with poor progress, not proof of a deadlock.
- The final file browser shows `useAuth.jsx`, with `<AuthContext.Provider>` at line 47. The extension issue was eventually corrected, but far too late to recover the intended implementation workflow. The last internal result is not an independent platform grade.

## Current-source coverage

Already committed in `64a6ec8d`: bounded startup recovery followed by resumption of sequential implementation; helper export validation; checks after tracked repair writes; stop final passes when repairs produce no effective source changes; repair-budget reminders.

Additional fixes after inspecting this online run:

1. Default final-suite passes capped at 3, independent of requirement count/turn budget. Explicit `OCTOS_FINAL_SUITE_PASSES` remains available.
2. Stop after two consecutive passes with no measured improvement, including when source files changed. An improving pass resets this counter. This does not treat incomplete measurements as success.
3. Explicit JSX extension/import guidance in the runtime shared-template contract and reference prompt.
4. Vite `.js/.ts` parse diagnostics preserve the source location and advise inspecting for misplaced JSX before rewriting the build configuration. Advice is conditional, not an automatic source rewrite.
5. State the migration-array element contract explicitly in design/shared-helper guidance; invalidate old cached application designs.

The overall task-size-derived time/token defaults are unchanged. The issue is wasteful continuation, not evidence that every large task should be forcibly cut to one hour. Deployments needing that ceiling should set `OCTOS_TIME_BUDGET=3600` explicitly.

## Validation boundary

Added unit regressions for default pass cap, repeated stalled passes, progress reset, and Vite diagnostic preservation. No official acceptance tests or generated benchmark application were modified.

Full local regression: 730 tests, 18 skipped, all remaining tests passed (33.650 seconds, Node 22.23.2). `git diff --check` passed. This is adapter regression validation, not a new model benchmark or proof of improved application scores.

The already-running local comparison uses the frozen `64a6ec8d` adapter at `arc/arc-output/v7-react-resume-bookstack-6k0dA7`. It does **not** contain the later online-run fixes described above. Per user instruction, do not start another model benchmark round for these additional fixes.
