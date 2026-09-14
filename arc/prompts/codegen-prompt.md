Requirement {node_id}: {description}

Acceptance test (ground truth):
{spec}
{files_intro} frontend/src/index.html (+ one html per further route); backend/server.js = CommonJS (require) Node http server on process.env.PORT||{port} serving ../frontend/dist files (index.html for /, <name>.html for /<name>) plus any API routes the requirement needs (in-memory state), 404 for anything else, wrapped in try/catch and process.on('uncaughtException').{ports} Both package.json files already exist (build copies src/* to dist; start runs server.js): do not output them.
Rules: texts, button names, labels and test ids exactly as in the test; the initial state is literally in the HTML; state lives in the page script unless the requirement says it is persisted; no external resources, no CSS, no comments, no notes; Playwright strict mode: every locator in the test must match exactly one element on the served page (no duplicate links, labels, texts or ids; each label's for= resolves to its own control). {size_rule}
