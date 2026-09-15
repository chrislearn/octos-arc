The official acceptance tests for requirement node {node_id} just ran against your app: {passed}/{total} passed. Failing tests (Feature / where it failed / what was observed / the last steps before failure):
{failures}
{test_location}
{corrections}{slow}{sources}
Fix frontend/ and/or backend/ so these tests pass without breaking the passing ones. Work within the configured request budget. Use the supplied evidence to identify the cause, read relevant sources when needed, and make focused edits. Preserve behavior beyond the tested inputs. The harness rebuilds and re-runs the official tests right after your turn. The spec files are read-only ground truth.
{port_rules}