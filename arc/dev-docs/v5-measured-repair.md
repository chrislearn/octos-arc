# v5 measured repair follow-up (2026-09-21)

This iteration stays on v5. It does not enable v6 module memory, dependency-graph
ranking, parallel feature branches, task-specific fixtures, or model thinking.

## Changes

- Parse empty EDIT replacements as deletions; malformed envelopes cannot swallow
  later patches. FILE payload examples are not independent EDIT operations.
- Treat build/start/load failures as unknown functional verdicts, not fabricated
  zero-pass suites. Do not trigger a whole-application rewrite on that evidence.
  A missing spec is not a pass; startup rehearsal is not feature acceptance.
- Record fatal provider turns and restore protected files before propagating the
  provider error. Keep the existing verified-delivery checkpoint mechanism.
- Treat the local token-admission guard as budget wind-down, not a provider
  outage: stop model calls but still measure pending edits in reserved time.
- For repair-only evolution (every requirement unchanged), measure the whole
  existing app first and repair its failing behaviors together. Fresh generation
  and partially changed requirement trees retain their existing paths.
- Reuse the immediately preceding unchanged-source failure when entering a node
  repair loop. Do not run that test again before the first edit.
- Admit final measurement independently of repair admission; reserve at least
  120 seconds, increasing with the observed full-suite duration. Bound the test
  subprocess by remaining time. No negative-time rehearsal model repairs.
- Default tool-less repair output ceiling: 8192 tokens. First generation retains
  its existing ceiling. Design ceiling scales from 4096 to 16384 tokens with
  requirement count. Thinking stays off. Caps bound individual replies, not the
  full request's input tokens or the entire run's billed cost.
- Clarify generic Router Outlet composition, inactive record action visibility,
  stable action ownership, menu/dialog lifetime and nested draft completion.
  Clarify collection migration object shape (`data.items`, not `data`).
- Qwen3.7 Plus adapter: send `enable_thinking=false` for disabled thinking, rather
  than relying on DeepSeek-only fields. Preserve passthrough and explicit enabled
  mode; strip vendor fields when routing to another model. The request-shape log
  records the boolean without recording credentials. See the provider's
  [thinking API documentation](https://www.alibabacloud.com/help/en/model-studio/deep-thinking).

## Overrides and limits

- `OCTOS_ARC_REPAIR_MAX_TOKENS`: tool-less repair ceiling; `0` disables this phase cap.
- `OCTOS_ARC_DESIGN_MAX_TOKENS`: override the adaptive design ceiling; `0` disables it.
- `OCTOS_ARC_DEGENERATE_MAX_TOKENS`: existing recovery ceiling still applies; the
  smaller positive ceiling wins. The route/provider may impose a lower ceiling.
- `OCTOS_ARC_FINAL_MEASUREMENT_SECONDS`: override the final measurement reserve
  (minimum 30 seconds). This is an admission reserve, not a guarantee that a slow
  npm build, provider, or teardown completes before the run deadline.
- Existing per-node/full-suite repair-round, turn, total-token and time limits
  remain. The absolute token guard is checked before requests; an in-flight
  request can overshoot. Closing a caller does not necessarily cancel upstream.
- Local runner accepts `--model qwen3.7-plus` to override the model without editing
  or copying the credential file. The default model has NOT been switched.

## Validation protocol

Old adapter: v5 `e6944198`. New adapter: frozen working-tree source snapshot.
Both use the same existing Keep app (independently measured 27/32), unchanged
official specs, DeepSeek v4 Flash with thinking disabled, 600-second run budget,
500000-token soft and absolute guards, and one grading worker. Runs are sequential.
Each delivered app is independently graded from a disposable copy afterwards.
That grading time is reported separately from generation/repair wall time.
At the user's request, a third run uses the same new adapter, seed, limits and
grading protocol with `qwen3.7-plus`, explicitly disabling thinking. The configured
API's read-only model catalog lists that exact model ID; no fallback model is used.

This measures repair efficiency, not fresh generation success. One paired run
cannot establish a stable expected score, and request ordering can affect provider
cache hits. Only provider usage records are used for billed-token comparisons;
missing usage is called out rather than treated as zero.

## Results

Final regression review: **641 tests passed**, 77.339 seconds, with real npm,
Playwright and proxy/bundle integration enabled; `git diff --check` was clean.

All three independent grades ran every official spec (32 total), with no build or
report error. API usage was present for every upstream request. Runtime below is
the harness run, excluding the subsequent disposable-copy independent grade.

| Adapter / model | Independent score | Run seconds | API requests | Input tokens | Output tokens | Total tokens | Input cache hit |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Old v5 / DeepSeek v4 Flash | 23/32 | 662 | 17 | 438996 | 89764 | 528760 | 56.22% |
| New v5 / DeepSeek v4 Flash | 27/32 | 288 | 11 | 486336 | 28976 | 515312 | 83.59% |
| New v5 / Qwen3.7 Plus | 28/32* | 487 | 3 | 68369 | 5345 | 73714 | 10.11% |

**The Qwen score is NOT evidence of a successful repair.** Its first two patches
still measured 27/32; its third patch regressed to 17/32. The harness restored the
initial verified checkpoint. Subsequent unchanged-source runs measured 28/32,
including independent grading. A recursive comparison of frontend/backend with
the original seed, excluding only node_modules and dist, found NO differences.
Thus the one-test difference is variability on the original app, not a retained
Qwen fix. REQ-2.7.1 (assign a label) is the fluctuating case. The Qwen run's six
suite measurements, including the 153-second regressed suite and rollback
confirmation, explain why its wall time exceeded new DeepSeek despite fewer tokens.

Interpretation:

- New DeepSeek: run time -56.5%, output tokens -67.7%, but total tokens only -2.5%
  versus old DeepSeek. Input tokens actually increased. No improvement above the
  original 27/32 baseline; the improvement was avoiding delivery regression.
- Qwen: total tokens -85.7% versus new DeepSeek; three short, applicable patches,
  no tool-mode fallback, but no retained functional improvement. Cheaper token
  generation is not proof of higher repair accuracy or lower wall time.
- Old DeepSeek exited on the local absolute-token guard without a complete suite
  checkpoint. It regressed unarchive, filtered/all-note views, and unpin in
  addition to the original five failures. New DeepSeek exhausted the same token
  guard but correctly measured and delivered its remaining 27/32 state.
- 600 seconds is the configured run budget, not forced runtime. Old flow overran
  to 662 seconds. Token guards checked before requests allowed overshoots to
  528760 and 515312. Qwen stopped after its configured repair rounds and no further
  measured progress, not because its token allowance was exhausted.
- All three Qwen requests logged model=qwen3.7-plus and enable_thinking=false.
  The provider did not return a reasoning-token counter for Qwen; do not treat a
  missing counter as independent proof of zero internal reasoning.
- Cache ratios are observations, not controlled cache experiments. Models have
  different tokenizers, prices and cache policies; these are token counts, not a
  monetary-cost comparison. One run per configuration is not statistical proof.

## Remaining bottlenecks observed in this round

1. `suite_repair_prompt` still clips the combined failure evidence at 8000
   characters. Replaying the 26353-character new-DeepSeek independent failure
   report through that limit retains headers for only TWO of the FIVE failures.
   Failure requirements/specs are still present, but later concrete failure
   evidence is lost. Next experiment should budget evidence per failure, putting
   all failure headers/observations before bounded DOM/network detail, rather
   than adding more generic prose. This was not changed mid-comparison.
2. DeepSeek still emitted repetitive output and invalid exact anchors; caps bound
   the loss but do not remove it. Two failed codegen attempts followed by a
   tool-mode context of increasing size consumed nearly the entire token budget.
3. Current UI contracts did not ensure correct active-record targeting and nested
   editor completion. Both models made plausible local changes without fixing
   the complete interaction path. Qwen additionally introduced a large regression.
4. Repeated full-suite runs on unchanged source can fluctuate. Do not promote one
   extra pass after rollback as a new implementation success.

## Reproduction and artifacts

Output directory: `arc/arc-output/v5-measured-repair-20260921/`.
Each case has metrics.json, llm-usage.jsonl, flow-metrics.jsonl, run log and an
application.tar.gz excluding dependencies/build output. The sibling `*-grade`
directories contain independent summaries and prepared Playwright reports.
No credentials are included. `comparison.json` carries the compact comparison.

Frozen new adapter: `/tmp/arc-v5-measured.fbNxKv/arc`.
Original seed: `/tmp/arc-v6-research.SasRig/repair-seed`.
Common environment: OCTOS_TIME_BUDGET=600, OCTOS_ARC_MAX_TOTAL_TOKENS=500000,
OCTOS_ARC_MAX_TOTAL_TOKENS_ABS=500000, OCTOS_ARC_REASONING=none. The local runner
uses `--template` for that seed and `--api-config` for the private credential
file. Only Qwen adds `--model qwen3.7-plus`; each case has separate free ports.
