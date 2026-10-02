Final end-to-end check of the web application in the current directory:
1. `npm run build` in frontend/ — fix any error.
2. Kill leftover servers, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, confirm `curl http://127.0.0.1:{smoke}/` serves the app and every API endpoint answers (success and error cases).
3. Audit required flows and states against the contracts below. Check accessible names, unique IDs and correct label associations. Resolve observed locator ambiguity in its intended scope; repeated text and destinations can be legitimate.
4. For flows affected by async navigation/session changes, hold and release the relevant read in a controlled implementation check. Verify same-owner refresh preserves usable navigation, logout/account change invalidates old responses, and loading settles into usable controls. Exercise stale failures/finally too. Keep these checks separate from protected specs; a zero-wait lookup is a compatibility probe, not a universal requirement.
{tests}
{ui}{performance}
{port_rules}