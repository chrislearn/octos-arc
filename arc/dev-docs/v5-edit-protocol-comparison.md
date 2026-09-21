# v5 file generation / structured editing experiment

## Protocol and safety changes

- Tool-less generation now asks only for complete FILE blocks (or NO CHANGE).
  Legacy EDIT parsing remains for compatibility with captured replies; it is no
  longer advertised as a competing format in generation prompts.
- Repairs on nontrivial application code and generation touching a quoted file
  of at least 12,000 bytes use native read_file/edit_file/write_file tools.
  Keep requirements and acceptance evidence; replace verified whole-source
  quotations with read-on-demand entries. Existing short-file generation remains
  single-request. Native tool turns default to a **soft** finishing threshold of
  12 requests and 8192 output tokens per request, inside the caller's existing
  time allowance. The inherited request guard removes tools and asks for a final
  answer; it does not reject subsequent requests/tool calls. Both live models
  exceeded this threshold. It must not be described as a hard request cap.
- ARC's before-tool hook validates exact unique anchors; only an unambiguous
  contiguous CRLF/LF-equivalent window is admitted as a fallback. Reject no-op,
  empty, ambiguous and guessed edits. Failed anchors return a bounded current
  source excerpt. The hook never changes the official tests or writes application
  source itself. Native filesystem policy still applies when executing the edit.
- The kernel truncates hook arguments over 1 KB. A private temporary directory,
  keyed by provider tool-call id, carries complete edit arguments from the local
  proxy to the trusted ARC hook. Truncated calls without complete arguments fail
  closed. Conflicting ids are rejected. Sidecar contents are not model context
  and are removed when the proxy stops. This compatibility bridge is tested
  against the actual bundled Octos binary and a local fake provider.
- Codegen requests stream upstream and are collected into the response shape
  expected by the kernel. Strong repeated operation cycles/no-op edits or long
  exact periodic suffixes close the upstream response early. Interrupted output
  is marked length/incomplete, never successful. Only complete blocks reach the
  existing application guards. Provider usage missing after interruption is
  recorded as missing, not zero. Closing a connection does not prove cancellation
  or a final billing amount at the provider.

Controls: `OCTOS_ARC_STRUCTURED_EDITS=0`, `OCTOS_ARC_EDIT_FILE_CHARS`,
`OCTOS_ARC_EDIT_REQUESTS`, `OCTOS_ARC_EDIT_MAX_TOKENS`,
`OCTOS_ARC_SAFE_EDIT=0`, `OCTOS_ARC_STREAM_GUARD=0`. The structured-edit override
disables tool dispatch but does not restore the previous EDIT-advertising prompt;
use the prior commit/snapshot for an actual historical-control experiment.

## Measurement protocol

Both models start Keep from zero using the same frozen source, bundled binary,
task-neutral blueprint, official 32 specs, thinking disabled, 1800-second harness
budget, 2,000,000-token admission guard and one grading worker. Runs are sequential.
The wrapper watchdog is the harness budget plus 300 seconds. Each final application
is independently measured in a disposable copy; that grading time is separate.
The runner is `arc/run-model-comparison.py`. Local credentials are read from the
existing configuration and are not copied into the source snapshot or reports.

An initial startup attempt was aborted after discovering that changing the request
to SSE left a stale Content-Length header. A real HTTP regression now covers that
wire shape. During the same review, the hook's argument truncation was corrected
with the private full-argument bridge. This aborted startup is not a scored
half-hour run; its logs remain under `arc/arc-output/v5-edit-20260921/`.

## Final results

| Model | Previous independent score | New independent score | New run seconds | Requests | Input tokens | Output tokens | Reported total | Input cache hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DeepSeek v4 Flash | 0/32 | 0/32 | 1516 | 98 | 1,915,545 | 111,009 | 2,026,554 | 77.99% |
| Qwen3.7 Plus | 20/32 | 18/32 | 1619 | 106 | 1,903,008 | 103,374 | 2,006,382* | 65.47% |

Both independent grades executed all 32 specs without a build/report error.
Their separate wall times were 473 seconds (DeepSeek, including dependency
installation) and 148 seconds (Qwen). Both generation/repair runs stopped issuing
model calls at the 2M-token guard before using the full 1800-second allowance.
Shorter run time here is **not** evidence of faster successful completion.

The historical control is frozen revision `783908cb`, documented in
`v5-fresh-comparison.md`: DeepSeek 784,646 reported tokens / 1807 seconds;
Qwen 774,491 / 1808 seconds. New output tokens decreased by about 66.4% and 7.0%
respectively, but reported total tokens increased by about 158% and 159%.
Historical DeepSeek and new Qwen each have one request without usage, so those
totals are incomplete provider-reported amounts, not exact final invoices.
The new Qwen missing request was a connection-refused proxy HTTP 502.

This experiment does **not** demonstrate an overall optimization. Preserve the
protocol safety findings, but do not promote the broad native-tool repair policy
as a proven cheaper or higher-scoring default. One run per model cannot establish
a statistically reliable ranking or isolate each change's effect. The new run
also includes the startup/build and diagnostic hardening after `783908cb`, so
score changes cannot be attributed solely to editing format.

## Failure and cost analysis

DeepSeek finished after 1516 seconds because of the 2M-token admission guard,
not because all requirements passed. It consumed 2,026,554 reported tokens
(1,915,545 input, 111,009 output; 77.99% input cache hits). An in-flight request
can take the admission total over 2M. Independent grading returned 0/32.
Exit code zero only means the harness finished, not a successful application.

All 12 planned generation waves applied changes and attempted all 32 leaves.
No generation-format retry or streaming-repetition interruption was observed.
The final app instead crashes while rendering records whose `labels` field is
missing: `note.labels.includes(...)`. Seeded and newly created records do not
share the same normalization invariant. Earlier startup failures included a
malformed source-file boundary, missing icon dependency, aggregate Radix imports,
and an incorrect migration-store argument. Native editing did not prevent these
application-level mistakes.

Read/tool history is now an important cost: startup repairs and full-suite repair
account for most input tokens. The model also invoked a full verification through
the legacy shell-tool fallback, followed by the harness's own full verification;
each failed suite took about 333 seconds. Compacting only the first prompt is
insufficient when the subsequent tool loop repeatedly reads broad source context.

Next candidates (not silently changed during this frozen experiment):

- Enforce a real hard repair request budget shared across structured and legacy
  fallback paths, with an explicit incomplete result and checkpoint handling.
- Keep startup/compiler repairs narrowly scoped; avoid repeating whole-app reads.
- Make the harness the owner of full-suite scheduling to prevent duplicate runs.
- Validate dependencies/import contracts early and consistently normalize records
  across initialization, creation, updates, and reads. These are task-independent
  invariants, not Keep-specific answers.

Frozen adapter archive SHA256:
`04c2aebd80fadc9e80b33c4d9aa45b1b50e33f3d7cf8248b3731457609106681`.
Artifacts: `arc/arc-output/v5-edit-20260921-final/`, including the source archive,
per-model request/event logs, independent grading evidence, and application archives.

Qwen's generation also applied all 12 waves without format retries or streaming
guard interruptions. Its first executable full suite was 14/32 after two startup
import repairs. Node repairs then passed creation, deletion, undo notification,
and updating in individual tests. Updating alone took 220 seconds; archive
notification still failed after an 89-second repair. It reached the token guard
and finished its harness run in 1619 seconds. Independent grading returned 18/32:
cached per-node passes are not a fresh final full-suite score. In particular,
the three pin-related individual passes did not reproduce in the independent
full suite. Final artifacts, not cached node state, determine the reported score.

Both models' recorded `edit_file` calls succeeded (DeepSeek 17, Qwen 23).
DeepSeek performed 58 `read_file` calls and Qwen 78. This shows the original
anchor/protocol failure largely disappeared in this sample, but the diagnosis
and context-repetition costs did not. Qwen used 106 API requests versus 33 in the
historical run, with 1,903,008 input and 103,374 output tokens. Its 2,006,382
reported total excludes one connection-refused HTTP 502 with missing usage.
Input cache hits were 65.47%, up from 23.89%; reported total tokens nevertheless
increased by about 159%. Cache-hit ratio alone is not an efficiency verdict.

Qwen's 14 remaining failures cover archive (4), color (2), label assignment and
all-notes view (4), pinning (3), and settings menu (1). Compared with the historical
run, five previously failing specs passed (label editing, label/reminder views,
suggested filters, sidebar styling), while seven previously passing specs failed
(the four archive specs, creation color, creation pinning, settings options).
These are independently generated apps, not proof that a specific patch caused
each before/after difference.

A concrete incomplete repair exists in `frontend/src/views/NoteList.jsx`:
`onArchive` is wired on the pinned-card rendering branch but omitted from the
ordinary-card branch. `NoteCard` falls back to `onDelete` when that callback is
missing. Thus an edit can apply correctly yet leave the component contract
inconsistent across call sites. Checking all consumers of a changed callback,
and consolidating duplicate rendering paths, are stronger task-neutral remedies
than more patch-format examples. Color, label, and pin failures also include
off-viewport geometry and interaction-target problems; these remain separate
from the successful patch transport and require browser evidence.

## Final verification

- Full local adapter regression: **671 tests passed in 102.142 seconds**, with
  npm/browser integration enabled; no skips reported. This is adapter verification,
  not a claim that either generated app passes its 32 acceptance specs.
- The 17 new focused cases include real HTTP framing and the actual bundled
  Octos binary against a local fake provider (no extra paid model requests).
- `git diff --check` passed. Runtime source and test files were byte-identical
  to the frozen experiment copy at review; only this results document was updated
  after freezing. No official task/spec changes or manual generated-app repairs.
- Final regression log: `arc/arc-output/v5-edit-20260921-final/postrun-review.log`.
- No release archive or git commit was made by this experiment. Existing unrelated
  workspace changes were left untouched.
