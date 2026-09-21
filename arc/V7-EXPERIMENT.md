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
