# v7 branch split and React reliability fixes

Branches:
- v7-thinking-html starts at 0e9a7420: the measured no-React v7 baseline (27/34).
- v7-thinking-react starts at e967760a: the React control (9/34) and subsequent fixes.
- v7-thinking remains unchanged; the existing v7.zip is not repackaged here.

This revision changes only the React branch. No new paid model benchmark was
started; the previous 9/34 result measures the pre-fix revision, not these fixes.

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
