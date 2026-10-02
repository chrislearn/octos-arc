import { test as base, expect, type Page, type Locator, type Request, type Response } from '@playwright/test';
import { randomUUID } from 'node:crypto';
export { expect };
export const test = base.extend({ page: async ({ page, context }, use) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']); await use(page);
} });
export const unique = () => `sheet-${randomUUID().slice(0, 12)}`;
export const button = (p: Page | Locator, name: string) => p.getByRole('button', { name, exact: true });
export const field = (p: Page | Locator, name: string) => p.getByLabel(name, { exact: true });
export const text = (p: Page | Locator, value: string) => p.getByText(value, { exact: true });
export const grid = (p: Page) => p.getByRole('grid', { name: 'Worksheet grid', exact: true });
export const cell = (p: Page, at: string) => grid(p).getByRole('gridcell', { name: at, exact: true, includeHidden: true });
export const tab = (p: Page, name: string) => p.getByRole('tab', { name, exact: true });
export async function blank(p: Page) {
  await p.goto('/'); await button(p, 'New blank workbook').click(); await button(p, 'Create').click();
  await expect(tab(p, 'Sheet1')).toHaveAttribute('aria-selected', 'true');
  await expect(cell(p, 'A1')).toHaveAttribute('aria-selected', 'true');
  await values(p, { A1: '' });
  return p.url();
}
export async function edit(p: Page, at: string, value: string, viaGrid = false) {
  await cell(p, at).click();
  if (viaGrid) { await cell(p, at).dblclick(); await field(p, `Edit ${at}`).fill(value); await field(p, `Edit ${at}`).press('Enter'); }
  else { await field(p, 'Formula bar').fill(value); await field(p, 'Formula bar').press('Enter'); }
}
export async function values(p: Page, expected: Record<string, string>) {
  for (const [at, value] of Object.entries(expected)) {
    // Exclude only the named controls in the requirement, not arbitrary buttons
    // containing data. Preserve spaces and embedded newlines in ordinary text.
    await expect.poll(() => cell(p, at).evaluate((el, { at, value }) => {
      const content = el.cloneNode(true) as HTMLElement;
      // cloneNode copies markup defaults, not live input/textarea values.
      const inputs = [...el.querySelectorAll('input, textarea')];
      const inputCopies = [...content.querySelectorAll('input, textarea')];
      inputs.forEach((control, i) => {
        const style = getComputedStyle(control);
        const hidden = control.closest('[hidden], [aria-hidden="true"]') || style.display === 'none' || style.visibility === 'hidden'
          || (control instanceof HTMLInputElement && control.type === 'hidden');
        inputCopies[i].replaceWith(document.createTextNode(hidden ? '' : (control as HTMLInputElement | HTMLTextAreaElement).value));
      });
      const originals = [...el.querySelectorAll('button, [role="button"]')];
      const copies = [...content.querySelectorAll('button, [role="button"]')];
      originals.forEach((control, i) => {
        const labelledBy = control.getAttribute('aria-labelledby');
        const name = control.getAttribute('aria-label') ?? (labelledBy
          ? labelledBy.split(/\s+/).map(id => document.getElementById(id)?.textContent ?? '').join(' ')
          : control.textContent ?? '');
        if ([`Open dropdown for ${at}`, `Filter ${value}`].includes(name.trim())) copies[i].remove();
      });
      content.querySelectorAll('[aria-hidden="true"]').forEach(control => control.remove());
      return content.textContent || '';
    }, { at, value })).toBe(value);
  }
}
export async function formula(p: Page, at: string, expression: string, result: string) {
  await values(p, { [at]: result }); await cell(p, at).click();
  await expect(field(p, 'Formula bar')).toHaveValue(expression);
}
export async function persisted(p: Page, assertion: () => Promise<void>) { await assertion(); await p.reload(); await assertion(); }
export async function range(p: Page, from: string, to: string) {
  const a = await cell(p, from).boundingBox(), b = await cell(p, to).boundingBox();
  expect(a).not.toBeNull(); expect(b).not.toBeNull();
  await p.mouse.move(a!.x + a!.width / 2, a!.y + a!.height / 2); await p.mouse.down();
  await p.mouse.move(b!.x + b!.width / 2, b!.y + b!.height / 2, { steps: 8 }); await p.mouse.up();
}
export async function data(p: Page, action: string) { await button(p, 'Data').click(); await p.getByRole('menuitem', { name: action, exact: true }).click(); }
export async function sheetMenu(p: Page, name: string, action: string) {
  await button(p, `Worksheet options for ${name}`).click(); await p.getByRole('menuitem', { name: action, exact: true }).click();
}
export async function structure(p: Page, axis: 'row' | 'column', at: string, action: string) {
  await grid(p).getByRole(axis === 'row' ? 'rowheader' : 'columnheader', { name: at, exact: true }).click({ button: 'right' });
  await p.getByRole('menuitem', { name: action, exact: true }).click();
}
export async function clipboard(p: Page, value: string) { await p.evaluate(value => navigator.clipboard.writeText(value), value); }
export async function paste(p: Page, at: string, value: string, menu = false) {
  await clipboard(p, value); await cell(p, at).click();
  if (menu) { await cell(p, at).click({ button: 'right' }); await p.getByRole('menuitem', { name: 'Paste', exact: true }).click(); }
  else await p.keyboard.press('Control+v');
}
export async function choose(p: Page | Locator, name: string, value: string) {
  const control = p.getByRole('combobox', { name, exact: true });
  if (await control.evaluate(el => el.tagName === 'SELECT')) await control.selectOption({ label: value });
  else { await control.click(); const root = 'keyboard' in p ? p : p.page(); await root.getByRole('option', { name: value, exact: true }).click(); }
}
export async function prepareValidation(p: Page, from: string, to: string, kind = 'Number range') {
  await range(p, from, to); await data(p, 'Data validation');
  const dialog = p.getByRole('dialog', { name: 'Data validation', exact: true });
  await choose(dialog, 'Rule type', kind);
  if (kind === 'Number range') { await field(dialog, 'Minimum').fill('0'); await field(dialog, 'Maximum').fill('100'); }
  else await field(dialog, 'Allowed values').fill(' Open , Closed ');
  return dialog;
}
export async function validation(p: Page, from: string, to: string, kind = 'Number range') {
  const dialog = await prepareValidation(p, from, to, kind);
  await button(dialog, 'Save').click(); await expect(dialog).toBeHidden();
}
export async function csv(p: Page) {
  const pending = p.waitForEvent('download'); await button(p, 'Export CSV').click(); const download = await pending;
  expect(download.suggestedFilename()).toMatch(/\.csv$/i); const stream = await download.createReadStream();
  expect(stream).not.toBeNull(); const chunks: Buffer[] = []; for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString('utf8').replace(/^\uFEFF/, '');
}
// Independent RFC 4180 parser used only as an export oracle; accepting CRLF or LF
// does not relax field order, trailing empties, quote escaping or Unicode checks.
export function parseCSV(source: string): string[][] {
  const rows: string[][] = []; let row: string[] = [], field = '', quoted = false, closed = false;
  for (let i = 0; i < source.length; i++) {
    const c = source[i];
    if (quoted) { if (c === '"') { if (source[i + 1] === '"') { field += '"'; i++; } else { quoted = false; closed = true; } } else field += c; }
    else if (c === '"' && field === '' && !closed) quoted = true;
    else if (c === ',') { row.push(field); field = ''; closed = false; }
    else if (c === '\n' || c === '\r') { if (c === '\r' && source[i + 1] === '\n') i++; row.push(field); rows.push(row); row = []; field = ''; closed = false; }
    else { if (closed || c === '"') throw new Error('Malformed CSV quoting'); field += c; }
  }
  if (quoted) throw new Error('Unclosed CSV quote');
  if (field !== '' || row.length || closed) { row.push(field); rows.push(row); }
  return rows;
}
export async function pivot(p: Page, method = 'SUM', column?: string, value = 'Sales') {
  await range(p, 'A1', 'C4'); await data(p, 'Create pivot table');
  const dialog = p.getByRole('dialog', { name: 'Create pivot table', exact: true });
  await expect(text(dialog, 'Source range: A1:C4')).toBeVisible(); await dialog.getByRole('radio', { name: 'New worksheet', exact: true }).check();
  await button(dialog, 'Create').click(); const editor = p.getByRole('region', { name: 'Pivot table editor', exact: true });
  await choose(editor, 'Rows', 'Region'); if (column) await choose(editor, 'Columns', column);
  await choose(editor, 'Values', value); await choose(editor, 'Summarize by', method); await button(editor, 'Apply').click();
}
export async function sourceData(p: Page) {
  await blank(p); await paste(p, 'A1', 'Region\tSales\tStatus\nEast\t10\tOpen\nNorth\t20\tClosed\nEast\t30\tClosed');
  await values(p, { A1: 'Region', B1: 'Sales', C1: 'Status', A2: 'East', B2: '10', C2: 'Open', A3: 'North', B3: '20', C3: 'Closed', A4: 'East', B4: '30', C4: 'Closed' });
}
// Read selected labels without assuming application option values/IDs.
export async function chosen(p: Page | Locator, name: string, value: string) {
  const control = p.getByRole('combobox', { name, exact: true });
  if (await control.evaluate(el => el.tagName === 'SELECT')) await expect(control.locator('option:checked')).toHaveText(value);
  else if (await control.evaluate(el => ['INPUT', 'TEXTAREA'].includes(el.tagName))) await expect(control).toHaveValue(value);
  else await expect(control).toContainText(value);
}
export async function ordinary(p: Page, expected: Record<string, string>) {
  await values(p, expected);
  for (const [at, value] of Object.entries(expected)) {
    await cell(p, at).click(); await expect(field(p, 'Formula bar')).toHaveValue(value);
  }
}
export async function numericRule(p: Page, from: string, to: string, minimum: string, maximum: string) {
  await range(p, from, to); await data(p, 'Data validation');
  const dialog = p.getByRole('dialog', { name: 'Data validation', exact: true });
  await choose(dialog, 'Rule type', 'Number range'); await field(dialog, 'Minimum').fill(minimum); await field(dialog, 'Maximum').fill(maximum);
  await button(dialog, 'Save').click(); await expect(dialog).toBeHidden();
}
export async function condition(p: Page, header: string, conditionName: string, value?: string) {
  await button(p, `Filter ${header}`).click(); const dialog = p.getByRole('dialog', { name: `Filter ${header}`, exact: true });
  await choose(dialog, 'Condition', conditionName); if (value !== undefined) await field(dialog, 'Value').fill(value);
  await button(dialog, 'Apply').click();
}
export async function filterValues(p: Page, header: string, names: string[]) {
  await button(p, `Filter ${header}`).click(); const dialog = p.getByRole('dialog', { name: `Filter ${header}`, exact: true });
  await button(dialog, 'Clear selection').click(); for (const name of names) await dialog.getByRole('checkbox', { name, exact: true }).check();
  await button(dialog, 'Apply').click();
}
export async function visibleRows(p: Page, visible: string[], hidden: string[]) {
  for (const at of visible) await expect(cell(p, at)).toBeVisible();
  for (const at of hidden) await expect(cell(p, at)).toBeHidden();
}
export async function filterHeaders(p: Page, expected: Record<string, string>) {
  for (const [at, value] of Object.entries(expected)) {
    await expect(cell(p, at)).toBeVisible();
    await expect(button(p, `Filter ${value}`)).toBeVisible();
  }
  await values(p, expected);
}
export async function selection(p: Page, inside: string[], outside: string[]) {
  await expect(grid(p)).toHaveAttribute('aria-multiselectable', 'true');
  for (const at of inside) await expect(cell(p, at)).toHaveAttribute('aria-selected', 'true');
  for (const at of outside) await expect(cell(p, at)).toHaveAttribute('aria-selected', 'false');
  // Count every exposed selected cell, including cells omitted by an outside
  // sample. All remaining cells must explicitly expose aria-selected=false.
  await expect(grid(p).getByRole('gridcell', { selected: true, includeHidden: true })).toHaveCount(inside.length);
  await expect(grid(p).getByRole('gridcell', { includeHidden: true }).and(
    p.locator(':not([aria-selected="true"]):not([aria-selected="false"])'))).toHaveCount(0);
}

// The source requires visible errors but no particular ARIA role. Accept a
// visible alert or ordinary error text; unsupported feedback needs an adapter.
export const saveFailureReason = (p: Page | Locator) => p.getByRole('alert').filter({ hasText: /\S/ }).or(
  p.getByText(/unable to|could not|cannot save|failed|failure|error|错误|失败|无法|重试/i)
).filter({ visible: true });
export async function renameWorkbook(p: Page, name: string) {
  await button(p, 'Rename workbook').click(); await field(p, 'Workbook name').fill(name); await button(p, 'Save').click();
  await expect(text(p, name).first()).toBeVisible();
}
export async function reopen(p: Page, name: string) {
  await p.goto('/'); await p.getByRole('link', { name, exact: true }).click();
}
// A home "record" has no mandated ARIA role. Find its visible timestamp from
// the link's nearest ancestor containing one; no class, route, or storage ID.
export async function recordUpdated(p: Page, name: string) {
  const link = p.getByRole('link', { name, exact: true }); await expect(link).toBeVisible();
  const label = await link.evaluate(el => {
    for (let node: HTMLElement | null = el as HTMLElement; node; node = node.parentElement) {
      const labels = [...new Set([node, ...node.querySelectorAll<HTMLElement>('*')]
        .flatMap(candidate => candidate.innerText?.split(/\r?\n/) ?? [])
        .map(line => line.trim()).filter(line => /^Last updated:\s*\S/.test(line)))];
      if (labels.length === 1) return labels[0];
    }
    return null;
  });
  expect(label, `Home record ${name} must display Last updated`).not.toBeNull(); return label!;
}
export async function tabOrder(p: Page, names: string[]) {
  const tabs = p.getByRole('tab'); await expect(tabs).toHaveCount(names.length);
  for (let i = 0; i < names.length; i++) await expect(tabs.nth(i)).toHaveAccessibleName(names[i]);
}

// Prepare the dialog/selection BEFORE learning; action performs only the exact
// successful command later faulted. Never guess among unrelated background
// writes or learn a create request to fault delete. Ambiguity needs an adapter.
export async function learnWrite(p: Page, action: () => Promise<unknown>) {
  await p.waitForLoadState('networkidle');
  const started = new Set<Request>();
  const writes = new Map<string, {method:string, endpoint:string, body:string|null}>();
  let observed!:()=>void;
  const firstResponse = new Promise<void>(resolve=>observed=resolve);
  const onRequest = (request: Request) => {
    if (['POST','PUT','PATCH','DELETE'].includes(request.method())) started.add(request);
  };
  const onResponse = (response: Response) => {
    const request = response.request();
    if (!started.has(request) || !response.ok()) return;
    const url = new URL(request.url());
    const write = {method:request.method(), endpoint:url.origin+url.pathname+url.search, body:request.postData()};
    writes.set(JSON.stringify(write), write);
    observed();
  };
  p.on('request', onRequest); p.on('response', onResponse);
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await action();
    // networkidle can still reflect the prior document state immediately after
    // a click. First observe an actual response from this command.
    await Promise.race([firstResponse, new Promise<never>((_,reject)=>{
      timer=setTimeout(()=>reject(new Error('HARNESS_UNSUPPORTED: observed 0 successful command writes; provide a transport adapter')),10_000);
    })]);
    await Promise.all([...started].map(request=>request.response()));
    await p.waitForLoadState('networkidle', {timeout:10_000});
  } finally {
    clearTimeout(timer);
    p.off('request', onRequest); p.off('response', onResponse);
  }
  if (writes.size !== 1) throw new Error(
    `HARNESS_UNSUPPORTED: expected one successful command write, observed ${writes.size}; prepare selection first or provide a transport adapter`);
  return [...writes.values()][0];
}
export function matchesWrite(request: any, write: {method:string, endpoint:string}) {
  const url = new URL(request.url());
  return request.method() === write.method && url.origin+url.pathname+url.search === write.endpoint;
}
export async function rejectWrites(p: Page, write: {method:string, endpoint:string}) {
  let attempts = 0;
  const evidence: {method:string, url:string, status:number}[] = [];
  const intercept = async (route: any) => {
    if (matchesWrite(route.request(),write)) {
      attempts++;
      await route.fulfill({status:500, contentType:'application/json',body:JSON.stringify({error:'Unable to save changes'})});
      evidence.push({method:route.request().method(), url:route.request().url(), status:500});
    } else await route.fallback();
  };
  await p.route('**/*',intercept);
  return {attempts:()=>attempts, remove:()=>p.unroute('**/*',intercept),
    assertInjected:async()=>{
      await expect.poll(()=>evidence.length, {message:'HARNESS_UNSUPPORTED: target command did not use the learned HTTP write; no injected failure was observed'}).toBeGreaterThan(0);
      await test.info().attach('http-fault-injection', {body:JSON.stringify(evidence), contentType:'application/json'});
    }};
}
