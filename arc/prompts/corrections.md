## identical_failure
Your last two attempts produced EXACTLY the same failure. The same logic will fail again: read the Expected/Received values in the observation, change the approach (e.g. render the initial state in the served HTML instead of after a fetch), and check the spec's locator against your markup.
## regressions_restored
Your last two repairs made the tests worse; the harness restored frontend/ and backend/ to the best state ({best}/{total}). Start from that code.
## protected_restored
You changed official test/requirement files; the harness restored them: {files}. They are read-only ground truth — fix the app instead.
## layout_incomplete
Your turn ended without both frontend/package.json and backend/package.json (with `build` and `start` scripts) on disk; the harness could not even build the app. Create the missing files.
## implement_timed_out
Your implementation turn ran out of time; work in smaller steps and verify with curl early.
## parallel_suite
The grader runs all spec files IN PARALLEL against one server; tests from different files must not interfere through shared server state (e.g. a counter that every browser session shares). Keep persisted data only where the requirement demands persistence.
## evolution_regression
This node passed before this evolution round; the regression below must be fixed without removing the new behaviour.
## claim_without_verification
Your previous turn claimed completion without running any build, start or request command. Never declare a step done before executing `npm run build`, starting the backend on the smoke port and exercising the endpoint with curl.
## repeated_error
You hit the same error {count} times in a row ({error}). Stop repeating the command; diagnose the root cause (read the file / port / path involved) and change approach.
## protected_writes
You modified protected files that must never change: {files}. Revert nothing yourself; only touch frontend/ and backend/ from now on.
