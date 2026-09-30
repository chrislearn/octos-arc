# Source-reviewed frozen internal tests

These tests are derived from the supplied atomic requirements and inherited interaction contracts. Generic or corrupted scenario templates are interpreted using the more precise atomic prose. They are internal acceptance checks, not official ARC evaluation tests or an official score.

All executable cases have completed source review. Frozen hashes in suite-origin.json and review.json bind that review to the exact helper, fixture and spec bytes. Runtime product behavior has not been certified by this source review.

Read app-design.json, domain-contracts.json, requirement-contracts.json and test-obligations.json as the frozen source-reviewed business context before generating code. app-design describes shared identities, source contracts and atomic commands; its implementation schemas are proposals, while original requirements remain authoritative. The obligation ledger is a verbatim clause inventory, not a claim of exhaustive executable test coverage.

Read fixtures.json before generating code. Provision the public records and role relationships as server seeds. Do not create a private test-only API. Every suite invocation starts with fresh server data; within a suite, mutable GitHub records are separate per case and spreadsheet mutations create separate workbooks through UI. Tests remain enabled if a seed is missing.

Playwright uses E2E_BASE_URL (the harness supplies its isolated smoke server). Both helpers use role/name locators; entry addresses are discovered from the browser and reused across reloads. Source requirements remain authoritative if a conflict is found.
