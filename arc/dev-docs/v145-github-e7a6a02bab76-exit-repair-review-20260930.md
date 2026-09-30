# v14.5 GitHub run e7a6a02bab76: exit cause and repair review

## Observed exit

The ARC-Bench runner reported that `main.py` exited with status 1. Its final
startup rehearsal first found JSX syntax errors in
`frontend/src/pages/PullRequestDetailPage.jsx`, then an undefined backend
`requireAuth`. Those were repaired far enough for the frontend to build and the
backend to start. The final browser health checks still failed on undefined
frontend bindings. The second final repair turn exhausted its 12-request
allowance without changing source; the hard-coded third rehearsal attempt then
gave up. This happened after about 193 minutes of a 600-minute run. The log's
memory events recorded `oom 0` and `oom_kill 0`.

The downloaded final `PullRequestDetailPage.jsx` places reviewer state and
handlers in `PullRequestDetailPage`, but references them inside the separate
`FilesChangedView` function. The bundled lexical checker reports 15 undefined
references in that file. These are application source errors, independent of
generated test approval.

## Generator changes

1. `generation_checks.check_batch` now runs the existing frontend and backend
   lexical binding checks on changed JavaScript source during generation. A
   confirmed failure becomes exact source evidence for the next repair window;
   unavailable analysis is deferred rather than treated as a code error.
2. Startup rehearsal no longer quits solely because it reached three attempts.
   It remeasures after each repair while source, time and cost budgets allow.
   After one unchanged-source repair it tries the focused whole-app source
   regeneration path; a final distinct tool attempt is allowed before declaring
   repeated no-progress. Existing protections for unavailable measurement,
   exhausted budgets and restoring a previously measured startable tree remain.
3. A rehearsal tool repair receives 32 requests by default, configurable via
   `OCTOS_ARC_REHEARSAL_REPAIR_REQUESTS`. The previous generic default was 12.
4. Each startup rehearsal now admits at most six repair actions and at most one
   hour of repair time by default (`OCTOS_ARC_REHEARSAL_REPAIR_ACTIONS`,
   `OCTOS_ARC_REHEARSAL_REPAIR_SECONDS`); the run-wide remaining time and final
   measurement reserve can make the allowance smaller. A source rewrite that
   still fails therefore cannot consume the entire run indefinitely. The log
   records the exact stop reason and action count.
5. Focused source regeneration can quote a named 62 KiB component when it fits
   the actual codegen context, instead of rejecting every file over 50 KiB.
   Its codegen and tool prompts retain the generated-test protection rule.

## Verification

- 831 relevant unit tests ran; 829 passed and 2 skipped. New cases cover continuation past
  three source errors, focused regeneration after a stalled repair, bounded
  no-progress termination, action and time limits, early frontend/backend
  binding detection and quoting a large named component. Four focused cases also passed after the final
  generated-test protection prompt adjustment.
- Running `check_batch` against the failed final page reproduced one confirmed
  generation error listing all 15 undefined references.
- In a separate local copy of the final application, passing the existing
  reviewer state and handlers into `FilesChangedView` cleared the lexical check
  (`passed`, 0 findings). `npm run build` passed and the backend served `/` with
  HTTP 200. The repository's independent browser health probe passed at `/`.
- No new archive was produced for the final action/time limit change.

## Remaining verification

The completed cloud run cannot resume. The local startup check does not
establish that all 100 requirement scenarios pass. A new ARC-Bench submission
of the updated adapter is required to measure complete generation, independent
case approval, acceptance execution and final evaluation.
