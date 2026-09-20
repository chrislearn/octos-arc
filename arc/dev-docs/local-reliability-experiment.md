# Local generation diagnostics — 2026-09-20

Model: `deepseek-v4-flash`, thinking disabled (all recorded reasoning usage zero).
Credentials were read from the ignored root `.test_data`; no credential values,
configuration file, generated applications or raw benchmark artifacts are committed.
No official task/acceptance file was changed.

## Full Keep diagnostic (interrupted intentionally)

Source baseline: `28764a31` (the run started immediately before committing those changes).
Output: `arc/arc-output/keep-reliability-20260920`.
Log: `/tmp/arc-keep-reliability-live.log`.

Experiment settings: time budget 1500s plus external 1800s stop; model turn 240s,
design 90s, node total 300s, minimum repair 60s, whole-app turn 240s;
2 node repair rounds; 1 final pass of up to 2 repair rounds;
soft/absolute token thresholds both 1,000,000; 40 model turns;
implement/repair request budget 8; local Playwright; ports 43520/43521.
These are diagnostic caps, not production defaults or a matched cloud benchmark.

Findings:

1. Design completed in 24s. Initial 3-node generation emitted bare FILE headings
   without delimiters: 7805 output tokens discarded, followed by a 7279-token
   format retry (about 39s + 40s).
2. Two later requests (3 nodes, then 1 node) each reached 32768 output tokens in
   about 133s and were discarded by the kernel. Merely reducing leaf count did
   not prevent excessive output.
3. Only 7 leaves had reached generation before the partial application was measured.
   The first complete suite was **2/32**, taking 312s. This is not the score of a
   completed 32-leaf implementation. Its clean source checkpoint was preserved.
4. Generated callers used `res.ok/res.value` after `requestJson`, although that
   helper returned parsed JSON directly. The initial async adapter's different
   `{ok,value}` contract encouraged this mismatch. The UI stayed empty despite
   successful API responses. Per-node repairs did not promptly fix the shared cause.
5. The experiment was manually interrupted once the common cause and two truncated
   requests were established, instead of spending the remaining budget on the
   superseded contract. It did not complete final grading. Recorded usage at stop:
   **26 requests, 514461 total tokens**, 95170 completion tokens, 69.3% input cache
   hit ratio, one exchange without usage. An interrupted in-flight request may be
   absent from the log; these are not authoritative account billing totals.

## Bounded prompt replay (same recorded wave prompt)

One tools-disabled request per variant, both capped at 8192 output tokens. Inputs
were the same recorded user prompt/source snapshot; the second changed the system
instruction to ask for a final, minimal, non-revisiting patch. No generated response
was injected into the running benchmark app.

| Variant | Output tokens | Total tokens | Time | Finish / dry-run application |
| --- | ---: | ---: | ---: | --- |
| Explicit delimiters only | 8192 | 23394 | 46.022s | length; 20 terminated edits, 3 no-ops, one invalid anchor |
| Final minimal patch instruction | 3634 | 18924 | 36.750s | stop; 10 edits, no no-ops, all anchors valid |

Anchors were checked against an isolated archive of the recorded source commit
`a09ec9a`, not the later repaired application. This measures output/protocol
efficiency, **not business correctness**; the response still inherited existing
application return-contract mistakes. One stochastic pair is not a statistical
estimate of expected savings.

Raw responses: `arc/arc-output/keep-reliability-20260920-diagnostics/`.
Developer tool: `replay-codegen.py` (explicit API config, one bounded request,
never modifies app sources, refuses an existing response output file).

## Three-requirement integration probe (NOT full Keep)

The same unchanged official specs for REQ-1.1, REQ-2.1 and REQ-2.2 were copied with
their helpers into a labeled subset. Ancestor descriptions and atomic dependencies
were retained; the official task and public tests remained untouched.
`prepare-subset.py` makes this a reproducible diagnostic, not a smaller full score.

Both variants: 300s run/360s external cap; 120s model turn; 60s design; one node
repair round; one final pass with no additional final repair; 120000 token threshold;
same model/thinking mode and test subset. Each was a fresh app with npm production
build and real Chromium.

| Variant | First / final pass | Model requests | Total tokens | Output tokens | Wall time | Repair turns |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Unified raw-data contract | 2/3 → 2/3 | 3 | 20748 | 3151 | 105s | 1 |
| Also require visible completion action | 3/3 → 3/3 | 2 | 13556 | 4619 | 58s | 0 |

Outputs: `arc/arc-output/keep-core-contract-20260920` and
`arc/arc-output/keep-core-completion-20260920`.
The last variant passed its first suite and two final confirmation measurements,
then startup rehearsal. It generated more initial output but needed fewer total
tokens and less time because it avoided a repair. This supports optimizing total
workflow cost, not minimizing every individual completion at the expense of clarity.

All five experiments recorded **591083 total tokens** combined. The interrupted
full run has the accounting caveat above. No paid experiments remain running.

## Regression verification

The final Python regression suite passed **584 tests**, including real npm build,
Chromium interaction and failure-observer integration checks. Rust verification
passed 127 library tests (one ignored) plus one integration test. These validate
the runner and reusable helpers, not all generated Keep business requirements.

## Next high-value experiments

- Repeat full Keep with the corrected contracts and new diagnostics under matching
  model/resource limits, then repeat another task to check generalization.
- Compare dependency/module-oriented generation against leaf batches; large shared
  components and repeated overlapping patches can outweigh prompt cache savings.
- Add cheap shared-contract smoke checks before a long failing suite: startup alone
  misses successful HTTP whose data never renders. Network shapes are evidence,
  not proof of a specific root cause or permission to change assertions.
- Consider bounded shared-cause repair when many failures converge on one data
  loading path. Do not merge unrelated timeouts solely because their messages match.
- Only adjust reasoning/model routing after controlled whole-task comparisons.
  No claim is made that thinking off, a particular batch size, or these templates
  is globally optimal, or that this version has passed all 32 Keep tests.
