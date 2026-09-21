# v7 branch split and React reliability fixes

Branches:
- v7-thinking-html starts at 0e9a7420: the measured no-React v7 baseline (27/34).
- v7-thinking-react starts at e967760a: the React control (9/34) and subsequent fixes.
- v7-thinking remains unchanged; the existing v7.zip is not repackaged here.

This revision changes only the React branch. The initial implementation was
unit-tested; the subsequent requested model benchmark is recorded below.

## Changes

1. FILE parsing cannot consume a later FILE header or malformed END FILE marker
   as part of the current file. A normally completed response with incomplete
   envelopes is rejected before any writes. Explicitly provider-truncated replies
   retain only individually terminated blocks under the existing path/write guards.
   Executable source containing standalone protocol markers rejects the whole
   staged batch, including EDIT-produced content. Inline marker strings and text
   documentation examples remain supported; standalone FILE envelopes are reserved.
   This is format-level atomic rejection, not an OS-level multi-file transaction.
2. The collection blueprint validates initial as an array before persistence or
   migrations; invalid callers get an actionable error instead of nested data.
   Prompts specify the named collection export and distinguish the initial array
   from a migration's {items: [...]} envelope. No automatic data reset or lossy
   conversion of existing corrupted stores is introduced.
3. Node build/start/load repairs prefer the file protocol with current quoted
   sources rather than automatically entering a tool loop at the normal 1500-char
   repair threshold. Existing bounded retry/fallback/deadline policies still apply.
   Startup evidence budget increases from 600 to 2200 chars to retain file paths.
4. If local repair leaves a build/start/load failure unresolved, sequential feature
   expansion and its checkpoint pause and existing final repair handles the app.
   Deferred node IDs are recorded in metrics, not claimed implemented. Functional
   assertion failures alone do not trigger this stop; a measured run clears it.

## Remaining work

Network failures, lack of a truly protected final-phase time budget, tool repairs
that read without editing, and async test-helper role selection remain separate
issues. These changes do not claim to solve them or establish a higher pass rate.
Official acceptance tests and historical experiment artifacts are unchanged.

Validation: 711 tests, 18 skipped, all remaining passed with Node 22.23.2;
git diff --check passed. New regressions cover malformed/missing FILE endings,
all-or-nothing format rejection, protocol markers in source, startup repair
selection, blocker clearing, and rejecting invalid initial data without persistence.

## Requested React retest

Frozen revision: 2d656e69. Artifact: arc-output/v7-react-fix-bookstack-6OYEP0.
DeepSeek v4 Flash, reasoning low, Bookstack, React blueprint, sequential single
requirements, 3600-second generation limit, unchanged official tests. Independent
single-worker grading took another 158.037 seconds and passed 20/34 (no grader
infrastructure error), versus 9/34 for the previous React revision 28c9b390.

Known tokens fell from 1,890,234 to 985,195 (-47.88%). Repair turns fell 22 to 14;
repair time fell 2016.631 to 929.852 seconds; tool repair turns with no source
change fell 17 to 2. Both runs reached the one-hour generation deadline.
Input cache hit rate fell 65.43% to 55.08%, despite lower absolute token usage.
Missing usage records fell 100 to 10: these are not complete billing totals,
and improved upstream reliability is a material confounder.

No local build/start failures or format rejections occurred in the new run.
The strict parser/startup fail-stop protections were not exercised by this model
run; do not infer causality from their absence. Initial passes were 11/29 measured
nodes versus 7/31; entered nodes were 30/34 versus 32/34. Final-phase repair time
was still not protected, and the last four requirements were not entered.

Remaining final failures: login; save/cancel book edits; save page, save/delete
draft, create chapter, read/edit page navigation; recent views, favorites and
recent-update navigation (14 total). Several downstream checks fail at shared
navigation rather than proving an independent defect in each downstream feature.
Inspect shared React auth state and asynchronous navigation/accessible names,
and enforce a hard feature-generation cutoff before final repair next.
The historical HTML baseline remains higher at 27/34; this run does not show
React outperforming HTML. See the artifact REPORT.md for full comparison.

## Task-neutral follow-up: data ownership, reactive state, diagnostic layers

The pre-change submission archive is v7-thinking-react-d7851961.zip; it is not
overwritten by this follow-up. No generated benchmark application or official
acceptance test is changed.

- Planning and implementation contracts give each collection one canonical
  owner for initialization, migrations and access. Required initial records must
  come from requirements, not arbitrary test examples. Fresh-store prerequisites
  and existing-store upgrades must be checked separately; edits and deletions
  survive restart. Existing collection/store APIs remain unchanged.
- React-only implementation guidance requires a reactive state owner or an
  external-store subscription. Persistence alone is not a UI notification.
  Check cross-component updates without reload, intended restoration after reload,
  and no false success state after failed commands. Do not prescribe a particular
  auth schema or assume browser profile data grants server authorization.
- Generation checks emit bounded advisory source hints for multiple literal
  collection initializers and JSX consumers near browser-storage writes. These
  are heuristics (aliases, custom hooks and state/props can evade or satisfy them),
  not compiler failures, automatic rewrites, test passes or new repair attempts.
  Hints are scoped to changed files/callers, logged and fed into the next codegen
  context; existing wall-clock gating still applies. No server or model call is
  added for the scan. Actual behavioral verification remains acceptance/model
  work; the scanner does not claim to run an application-specific login test.
- Bounded repair evidence separates observed build/load, runtime, HTTP and
  UI/locator signals. Missing data and stale UI remain hypotheses until source,
  responses and snapshots support them. Preserve proper link/button semantics;
  never adapt every role to a test helper's fallback.
- Unknown failures no longer merge merely because ownership is unknown. Concrete
  runtime signatures and explicit source ownership still group repairs. Existing
  round budgets can select multiple independent groups together. Focused repair
  prompts retain prior-pass/flakiness, state-interference and worker evidence.

Design cache version is bumped. Regression coverage includes warning scope and
bounds, non-fatal advisory behavior, evidence budgets, unknown-failure grouping,
React-only prompt scope, and real Node checks that explicit migrations preserve
user edits/deletions and run once. No new paid model benchmark is claimed here.

Validation: 719 tests in 30.172 seconds, 18 skipped, all remaining passed under
Node 22.23.2; git diff --check passed. Read-only replay on the previous generated
application identified duplicate collection owners and the layout/storage update
boundary; diagnostic evidence stayed inside its 8000-character budget. This is
diagnostic coverage, not evidence of an improved benchmark score.

## Follow-up benchmark: regression, not an improved baseline

Frozen 74cf42c9, artifact arc-output/v7-react-contracts-bookstack-qACLTr.
Same DeepSeek v4 Flash / reasoning low / React Bookstack / 3600-second limit.
Independent grade: 3/34, versus 20/34 at 2d656e69. No grader infrastructure error.
Generation exited normally after 2833.339 seconds; independent grading added
327.798 seconds. Known tokens 1,248,940 (+26.77%), cache hit rate 83.33%, 64 requests,
4 missing usage records. Seven repair turns cost 1206.528 seconds; four of six
tool repair turns changed no source. Only four requirements entered sequential
implementation, compared with thirty before. Do not treat early exit as speedup.

An invented loadTable API broke startup at login. The pre-existing startup
fail-stop deferred thirty requirements, but successful startup recovery never
resumed the implementation queue. Four full suites then repeated 3/34 (~1289s),
including repeats after no source changes. Only two early generation checks ran;
both had empty warning lists. The new advisory checks were not exercised here.

Final login UI did show the user and Logout: state synchronization worked in the
observed snapshot. The test still waited for a heading while the nickname was
plain text (async helper fallback). No task-specific role adaptation was made.
Priority next: bounded startup recovery that resumes pending implementation,
verify installed API contracts, reserve tool budget for edits, and reuse complete
measurements only when source/tests/dependencies/environment/data permit it.
Single-run sampling/network confounders remain; these findings do not prove all
regression was caused by the added prompt rules. See the artifact REPORT.md.

## Resumable startup and bounded repair follow-up

- Sequential startup failure now gets at most two focused infrastructure repairs.
  Only a complete current-node measurement clears the blocker; a functional
  assertion failure permits continuing implementation but is not marked passed.
  Remaining requirements resume and checkpoint regression still runs. Failed or
  incomplete recovery retains the existing fail-stop behavior.
- Startup repairs prefer complete files and include implicated helper dependencies.
  Design guidance names installed APIs. Narrow literal named CommonJS imports
  from byte-identical bundled helpers are checked before codegen writes; an invalid
  import rejects the staged batch, with explicit exports as correction evidence.
  Customized helpers, dynamic/ambiguous syntax and quoted examples are not rejected
  by this check. This is not a general JavaScript type checker.
- File repairs and tracked tool repairs feed generation checks too. A mid-budget
  reminder on tool-repair requests reserves attention for edits and validation,
  retains all available tools, and explicitly forbids guessing a repair.
- A final repair with no effective source change stops repeat full-suite passes.
  No test result is cached or invented across changed data/environment, and no
  previously measured failure becomes a pass. Existing independent grading remains.

No benchmark-specific UI role adaptation, fixture seeding or test changes.

Validation before benchmark: 726 tests in 30.558 seconds, 18 skipped, all others
passed (Node 22.23.2); git diff --check passed. Tests cover preserving incomplete
verdicts, resuming after infrastructure recovery without claiming a functional
pass, whole-batch rejection before writes, custom helper exemptions and bounded
mid-turn notices retaining tool access.
