Design the application that satisfies this whole requirement tree (do NOT implement anything):

{outline}

Preserve the installed stack. Fresh applications default to local HTML/CSS/JavaScript ES modules, native semantic controls and Express routes, without React or JSX. Existing applications keep their architecture. frontend/src/index.html is the shell; backend/server.js is a small Express entry serving frontend/dist and registering backend/routes/<area>.js modules; shared persistence lives in backend modules. Reuse the provided request/router helpers and cohesive view modules; do not invent another DOM/widget framework. Use one owner per draft/dialog state, stable record IDs, and ignore stale async responses. Render shared navigation consistently; preserve focus and drafts during unrelated updates.
Reply with ONE JSON object (at most 150 lines, no prose) that every requirement will be implemented against:
{"data_model": {"collection": {"field": "type"}},
 "routes": [{"method": "GET|POST|PUT|DELETE", "path": "/api/...", "purpose": "one line", "requirements": ["REQ-..."]}],
 "pages": [{"path": "/...", "purpose": "one line", "requirements": ["REQ-..."]}],
 "contracts": [{"requirements": ["REQ-..."], "invariants": ["ownership/key scope", "command: preconditions -> atomic effects and undo", "draft/save/cancel semantics", "date-only/clock/deadline rules", "control and validation semantics"]}],
 "notes": "session handling, seed data, versioned migrations, validation conventions, naming conventions"}
Name every collection, field, route and page once and consistently; requirements that share data must share the record shape. For each HTTP method, place literal routes before overlapping parameter routes (e.g. /api/items/trash before /api/items/:id). In notes, state the shared interaction lifecycle: when controls become usable, what commits an edit, and when the list reflects the committed record. Do not enumerate test-only cases.
