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
