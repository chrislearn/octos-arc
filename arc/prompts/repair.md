The official acceptance tests for requirement node {node_id} just ran against your app: {passed}/{total} passed. Failing tests (Feature / where it failed / what was observed / the last steps before failure):
{failures}
{corrections}{slow}{sources}
Fix frontend/ and/or backend/ so these tests pass without breaking the passing ones. You have about 10 requests: in the FIRST response read at most two files (only the ones you will change), in the SECOND response emit every edit_file/write_file call together, then finish — do not read more files afterwards. No shell commands. The harness rebuilds and re-runs the official tests right after your turn. The spec files are read-only ground truth.
{port_rules}