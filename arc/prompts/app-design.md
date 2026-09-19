Design the application that satisfies this whole requirement tree (do NOT implement anything):

{outline}

Architecture is fixed: frontend/src/index.html plus one html per route; backend/server.js as a small Express entry that serves frontend/dist and registers backend/routes/<area>.js modules; shared persistence in backend modules.
Reply with ONE JSON object (at most 150 lines, no prose) that every requirement will be implemented against:
{"data_model": {"collection": {"field": "type"}},
 "routes": [{"method": "GET|POST|PUT|DELETE", "path": "/api/...", "purpose": "one line", "requirements": ["REQ-..."]}],
 "pages": [{"path": "/...", "purpose": "one line", "requirements": ["REQ-..."]}],
 "notes": "session handling, seed data, validation conventions, naming conventions"}
Name every collection, field, route and page once and consistently; requirements that share data must share the record shape.
