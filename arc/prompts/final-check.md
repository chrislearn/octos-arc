Final end-to-end check of the web application in the current directory:
1. `npm run build` in frontend/ — fix any error.
2. Kill leftover servers, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, confirm `curl http://127.0.0.1:{smoke}/` serves the app and every API endpoint answers (success and error cases).
3. Audit every page against the contracts below and fix violations; run a mechanical strict-mode check: for each value the pages echo, count the elements containing it (`curl -s <page> | grep -o '<value>' | wc -l` for server-rendered pages, or read the render code) — the count must be 1.
{tests}
{ui}{performance}
{port_rules}