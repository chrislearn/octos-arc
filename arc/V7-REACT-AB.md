# v7 React control

Control baseline: v7-thinking / 1d715d61 (latest documentation 0e9a7420).
Bookstack, deepseek-v4-flash, reasoning low; one requirement at a time,
immediate acceptance/repair, affected regression of proven requirements and
checkpoint/full regression. 3600 seconds, 2-million-token admission cap,
single-worker independent grading outside generation budget. No Qwen run.

Only restore the retained React/Vite/Radix/React Router frontend scaffold and
its existing pinned library recommendations. Remove the contradictory vanilla-only
wording from design/runtime prompts, preserving their other behavior rules.
Keep Express/store blueprint, model/API/binary, test suite, repair policy,
source context budgets, output limits and regression selection unchanged.
Prompt version changes to prevent reuse of a stale vanilla application design.

Reference run: arc-output/v7-thinking-bookstack-ypOCUP, 27/34, 3458.359 seconds,
1,806,085 recorded tokens, 61.78% input cache hits, 11 missing-usage requests.
This is a historical single-run control, not repeated simultaneous sampling;
provider/network variability and generation randomness remain confounders.
This comparison measures the retained React scaffold/library stack as a whole,
not the isolated causal effect of the react package.

Do not change prompts or applications during the measured run. Preserve logs,
then independently grade the final application copy without modifying tests.

## Result (2026-09-21)

Frozen React revision 28c9b390: **9/34**, compared with vanilla **27/34**.
Generation hit 3600.009 seconds (exit 124), entering requirement 32/34; last two
requirements and final repair were not completed. Independent grading succeeded
as a measurement, with build/start working, and took 268.792 seconds outside the
generation deadline. No application/test modifications were made by this agent.

Recorded tokens: 1,890,234 (+4.66%); prompt 1,637,436, completion 252,798
(includes reasoning 175,220). Cache input 1,071,360 (65.43%). 207 request records,
100 missing usage: 87 resets, 4 refused connections, 4 read timeouts, 3 remote
disconnects, 2 HTTP-200 turn deadlines. The network confound is much larger than
the vanilla baseline's 11 missing-usage records; this cannot prove React is worse.

First-pass 7/31 measured nodes versus vanilla 18/34. First 20 nodes: 6 vs 11;
build/start blocked 9 vs 1. Repair: 22 turns, 2016.631 seconds, 17 no-source-change
turns. Shared import/export and collection initial-shape mistakes persisted.
A FILE header reached backend/books.js and failed syntax validation. Some final
failures also show visible content with the test awaiting a different role.

Keep vanilla v7 as the stronger measured baseline. Prioritize strict output
parsing/atomic application, build-error closure, network-aware retry handling,
no-edit repair limits and protected final regression before changing frameworks.
Repeat under stable network conditions for a stronger framework comparison.

Local artifacts: arc-output/v7-react-bookstack-Ujz5xY/REPORT.md, PROTOCOL.md and
results/. Code validation: 706 tests, 18 skipped, all remaining passed.
