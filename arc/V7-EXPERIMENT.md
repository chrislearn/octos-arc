# v7-thinking experiment

Phase 1 retains the React scaffold but defaults to low reasoning, sequential
single-requirement implementation and immediate test/repair. Existing checkpoint
regression and final acceptance remain enabled. Whole-app generation is opt-in
with OCTOS_ARC_WHOLE_APP=1; sibling batching is opt-in with
OCTOS_ARC_SIBLING_BATCH_SIZE>=2. Explicit reasoning overrides remain supported.

The comparison runner defaults to --reasoning low and records the selected mode.
Each model has a strict generation deadline (--seconds), with up to 30 seconds
for process cleanup. Independent grading is outside that generation budget.
Its existing two-million-token limit is unchanged.

Phase 2 replaces the fresh-app React baseline with local HTML/CSS/JavaScript,
while retaining compatibility with existing React applications. Bookstack runs
use deepseek-v4-flash and qwen3.7-plus, 3600 seconds each. Comparing this phase to
the earlier whole-app/no-thinking baseline changes several variables together;
it cannot isolate React's effect without a phase-1 runtime control. The legacy
React scaffold remains opt-in with OCTOS_ARC_REACT=1 for controlled experiments;
fresh default apps receive no React dependencies, JSX entry or React library hints.

The initial runtime probe exposed a sequential-mode regression-selection bug:
after a shared repair, affected regression included not-yet-implemented specs.
The probe was stopped without a final score. Affected regression now covers
previously passing requirements plus the current target, leaving complete
coverage to final acceptance. The paired experiment restarts from clean output.

## Measured outcome

Frozen code revision 1d715d61: DeepSeek completed in 3458.359 seconds and scored
27/34 independently, versus the prior whole-app/React/no-thinking run's 4/34.
Recorded tokens increased from 1,160,872 to 1,806,085; input cache hits rose from
38.74% to 61.78%. Missing usage on interrupted requests makes these incomplete
billing totals. Multiple variables changed; this is not a React-only ablation.

Qwen was stopped at the user's request after about 51 minutes during requirement
19, with no independent final grade. Recorded tokens: 859,985. Its existing wire
adapter maps low to enable_thinking=true, not an effort level; do not describe it
as equivalent to DeepSeek's reasoning_effort=low. Repeated single-turn timeouts
and regressions limited progress. No further run is scheduled.

The next priorities are a genuinely protected final repair budget, budgeting
generation plus testing plus repair together, model-specific thinking control,
and fewer source-requoting/protocol retries. No further behavioral changes were
made during the frozen paired test.
