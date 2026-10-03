# Sheet browser compatibility probes

These four probes replay the **first failing interaction classes** observed in
the ARC reports for runs `8ff1885a8162` and `8aa637d019a5`: sorting,
filtering, validation, and pivot creation. The scripts use a browser click on a
visible ARIA `option`, matching the interaction pattern in those reports.

This directory is separate from the frozen derived requirement suite. A native
`<select>` can satisfy the requirement's combobox/option semantics while failing
a Playwright click on `<option>`. A compatibility failure therefore does not
by itself prove a requirement violation. Later official assertions are unknown;
passing these probes only proves the tested entry path works.

The pivot probe uses the report's exact `region → getByLabel(/^(rows)$/i)` entry.
The low-run editor renders a `<label>` around the entire `<select>` and option
tree; the high-run editor links a separate label to its trigger. The low-run
region is visible, but the exact label lookup does not find Rows.

Run against an already started app:

```bash
PYTHONPATH=arc python3 arc/check_sheet_compat.py \
  --base-url http://127.0.0.1:3000 \
  --playwright-root /path/containing/node_modules \
  --timeout-ms 10000
```

The command prints JSON with each case's verdict and exits nonzero when a probe
fails. Its temporary Playwright run and screenshots are kept under the selected
Playwright root for inspection.
