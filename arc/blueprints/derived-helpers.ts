// Helpers for tests derived mechanically from requirements.yaml (not official).
// Locators are as tolerant as the official ARC-Bench helpers: any role, label,
// placeholder or text; case-insensitive; first visible match. Navigation is
// more tolerant still: a named control that is not on screen is searched for
// through a bounded crawl of links, tabs and menus, because requirements name
// controls but rarely the path to them.
import { APIRequestContext, expect, Locator, Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

type Match = string | RegExp | Array<string | RegExp>;

// Signing out only affects this test's own browser context, and the sign-out
// confirmation the requirement names sits behind it (v9.2.3 2547a578478f).
const DESTRUCTIVE = /delete|remove|close|merge|archive|trash|leave|reset|cancel|discard|revoke|transfer/i;
const SIGN_IN_ENTRY = [/^\s*sign\s*in\s*$/i, /^\s*log\s*in\s*$/i];
let signedInAs: string | null = null;

async function signInEntryVisible(page: Page): Promise<boolean> {
  for (const pattern of SIGN_IN_ENTRY) {
    for (const locator of [page.getByRole('link', { name: pattern }), page.getByRole('button', { name: pattern })]) {
      if (await locator.first().isVisible({ timeout: 300 }).catch(() => false)) return true;
    }
  }
  return false;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function toPatterns(value: Match): RegExp[] {
  const items = Array.isArray(value) ? value : [value];
  return items.map((item) => item instanceof RegExp ? item
    : new RegExp(escapeRegExp(item.trim()).replace(/\s+/g, '\\s+'), 'i'));
}

function describe(value: Match): string {
  return (Array.isArray(value) ? value : [value]).map(String).join(' | ');
}

function namedLocators(page: Page, pattern: RegExp): Locator[] {
  return [
    page.getByRole('button', { name: pattern }),
    page.getByRole('link', { name: pattern }),
    page.getByRole('menuitem', { name: pattern }),
    page.getByRole('tab', { name: pattern }),
    page.getByRole('checkbox', { name: pattern }),
    page.getByRole('radio', { name: pattern }),
    page.getByRole('option', { name: pattern }),
    page.getByRole('combobox', { name: pattern }),
    page.getByRole('heading', { name: pattern }),
    page.getByLabel(pattern),
    page.getByPlaceholder(pattern),
    page.getByText(pattern),
  ];
}

async function visibleNamed(page: Page, value: Match, timeout = 300): Promise<Locator | null> {
  for (const pattern of toPatterns(value)) {
    for (const locator of namedLocators(page, pattern)) {
      const count = await locator.count().catch(() => 0);
      for (let index = 0; index < Math.min(count, 8); index += 1) {
        const candidate = locator.nth(index);
        if (await candidate.isVisible({ timeout }).catch(() => false)) return candidate;
      }
    }
  }
  return null;
}

type Step = { role: 'link' | 'tab' | 'menuitem' | 'button'; name: string; nth: number };

// Navigation candidates: links, tabs, menu items and EVERY visible non-submit
// button. The account menu of the GitHub task is a plain button showing the
// username (no aria-haspopup); restricting buttons to popup triggers left
// "Sign out" and "Update password" unreachable (local run github-req1-local).
// Unnamed icon buttons are addressed by their position among unnamed buttons.
async function navigationCandidates(page: Page): Promise<Step[]> {
  const raw: Array<{ role: Step['role']; name: string; unnamedIndex?: number }> = await page.evaluate(() => {
    const visible = (el: Element) => {
      const box = (el as HTMLElement).getBoundingClientRect();
      const style = getComputedStyle(el as HTMLElement);
      return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const nameOf = (el: Element) => ((el.getAttribute('aria-label') || el.getAttribute('title')
      || (el as HTMLElement).innerText || el.querySelector('img[alt]')?.getAttribute('alt') || '')
      .replace(/\s+/g, ' ').trim()).slice(0, 80);
    const out: Array<{ role: string; name: string; unnamedIndex?: number }> = [];
    for (const el of Array.from(document.querySelectorAll('a[href]'))) {
      const href = el.getAttribute('href') || '';
      if (!href || href.startsWith('#') || /^(mailto|tel|javascript):/i.test(href) || el.hasAttribute('download')) continue;
      try { if (new URL(href, location.href).origin !== location.origin) continue; } catch { continue; }
      if (visible(el)) out.push({ role: 'link', name: nameOf(el) });
    }
    for (const el of Array.from(document.querySelectorAll('[role="tab"]'))) if (visible(el)) out.push({ role: 'tab', name: nameOf(el) });
    for (const el of Array.from(document.querySelectorAll('[role="menuitem"]'))) if (visible(el)) out.push({ role: 'menuitem', name: nameOf(el) });
    let unnamed = 0;
    for (const el of Array.from(document.querySelectorAll('button, [role="button"]'))) {
      if (!visible(el)) continue;
      const type = (el.getAttribute('type') || '').toLowerCase();
      if (type === 'submit' || (el as HTMLButtonElement).disabled) continue;
      if (el.closest('a[href], [role="menuitem"], [role="tab"], [role="grid"], [role="gridcell"], table')) continue;
      const name = nameOf(el);
      if (name) out.push({ role: 'button', name });
      else out.push({ role: 'button', name: '', unnamedIndex: unnamed++ });
    }
    return out as any;
  });
  const seen = new Map<string, number>();
  const steps: Step[] = [];
  for (const item of raw) {
    if (DESTRUCTIVE.test(item.name)) continue;
    if (!item.name) {
      if (item.unnamedIndex !== undefined) steps.push({ role: 'button', name: '', nth: item.unnamedIndex });
      continue;
    }
    const key = `${item.role}|${item.name}`;
    const nth = seen.get(key) ?? 0;
    seen.set(key, nth + 1);
    if (nth === 0) steps.push({ role: item.role, name: item.name, nth });
  }
  return steps.slice(0, 32);
}

/** Let a client-rendered page finish its first data fetches (session check,
 *  list load) before its controls are read; a header that shows "Sign in" for
 *  200ms and then the account menu must be seen in its settled state. */
async function settle(page: Page): Promise<void> {
  await page.waitForLoadState('domcontentloaded').catch(() => undefined);
  await page.waitForLoadState('networkidle', { timeout: 800 }).catch(() => undefined);
  await page.waitForTimeout(250);
}

async function clickStep(page: Page, step: Step): Promise<void> {
  const locator = step.name
    ? page.getByRole(step.role, { name: step.name, exact: true }).nth(step.nth)
    : page.locator('button:visible, [role="button"]:visible').filter({ hasNotText: /\S/ }).nth(step.nth);
  await locator.click({ timeout: 3000 });
  await settle(page);
}

/** Find a named control or text, crawling at most `depth` navigation clicks. */
/** Words of the target that a candidate's name shares: likely paths are explored first. */
function similarity(value: Match, name: string): number {
  const words = describe(value).toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter((w) => w.length >= 3);
  const low = name.toLowerCase();
  return words.filter((w) => low.includes(w)).length;
}

// A failing crawl used to run until the 120s test timeout (v9.2.1: 6 failing
// checks took 744s at a checkpoint). Bound it in wall time as well as visits.
const REACH_MS = 40_000;

export async function reach(page: Page, value: Match, depth = 3, budget = 60): Promise<Locator> {
  await settle(page);
  const direct = await visibleNamed(page, value, 1500);
  if (direct) return direct;
  const started = Date.now();
  const start = page.url();
  const queue: Step[][] = [[]];
  const explored = new Set<string>();
  const tried: string[] = [];
  let visits = 0;
  while (queue.length && visits < budget && Date.now() - started < REACH_MS) {
    const path = queue.shift()!;
    if (path.length) {
      visits += 1;
      try {
        await page.goto(start);
        await settle(page);
        if (signedInAs && visits === 1 && await signInEntryVisible(page)) {
          // Requirement: the session survives a refresh. Say so instead of
          // reporting every signed-in control as unreachable.
          throw new Error(`After signing in as ${signedInAs} and reloading ${start}, the page shows the sign-in `
            + `entry again: the session is not persisted across a reload, so "${describe(value)}" cannot be reached.`);
        }
        for (const step of path) await clickStep(page, step);
      } catch (error) {
        if (error instanceof Error && error.message.includes('not persisted across a reload')) throw error;
        continue;
      }
      const hit = await visibleNamed(page, value, 400);
      if (hit) return hit;
      tried.push(path.map((s) => s.name).join(' > '));
    }
    if (path.length >= depth) continue;
    // A page state is its URL plus the controls it offers: a toggled menu on
    // the same URL is a new state whose entries must be explored, while a link
    // back to an already expanded page is not.
    const candidates = await navigationCandidates(page);
    const state = `${page.url()}|${candidates.map((s) => `${s.role}:${s.name}:${s.nth}`).join(',')}`;
    if (explored.has(state)) continue;
    explored.add(state);
    const ranked = [...candidates].sort((a, b) => similarity(value, b.name) - similarity(value, a.name));
    for (const step of ranked) {
      if (!path.some((s) => s.role === step.role && s.name === step.name && s.nth === step.nth)) queue.push([...path, step]);
    }
  }
  await page.goto(start).catch(() => undefined);
  const why = Date.now() - started >= REACH_MS ? `after ${Math.round((Date.now() - started) / 1000)}s` : `within ${depth} navigation clicks`;
  throw new Error(`Required control or text "${describe(value)}" is not reachable ${why} from ${start} `
    + `(${visits} page states explored). Explored: ${tried.slice(0, 12).join('; ') || '(no navigation controls)'}`);
}

/** Back to the code seeds before each test (generic entry, ARC_TEST_HOOKS=1).
 *  Any other app answers 404 here; its state then resets per spec file. */
export async function resetState(request: APIRequestContext): Promise<void> {
  await request.post('/__arc/reset', { failOnStatusCode: false, timeout: 10_000 }).catch(() => undefined);
}

export async function openHome(page: Page): Promise<void> {
  signedInAs = null;
  await page.goto('/');
  await settle(page);
}

export async function expectReachable(page: Page, value: Match): Promise<void> {
  const target = await reach(page, value);
  await expect(target).toBeVisible();
}

async function clickLocated(page: Page, target: Locator, value: Match): Promise<void> {
  const beforeUrl = page.url();
  const href = await target.evaluate((el) => (el.closest('a[href]') as HTMLAnchorElement | null)?.href || '').catch(() => '');
  try {
    await target.click({ timeout: 10_000 });
  } catch (error) {
    // Found but not clickable (covered, detached, disabled): say so instead of
    // hanging until the 120s test timeout (v9.2.3 03a2e937517e, REQ-1-2-1).
    throw new Error(`"${describe(value)}" was found on ${page.url()} but could not be clicked within 10s: `
      + `${error instanceof Error ? error.message.split('\n')[0] : String(error)}`);
  }
  if (href && new URL(href).origin === new URL(beforeUrl).origin && href !== beforeUrl) {
    await expect.poll(() => page.url() !== beforeUrl, {
      message: `clicking "${describe(value)}" did not navigate to ${href}`,
      timeout: 5000,
    }).toBe(true);
  }
  await page.waitForLoadState('domcontentloaded').catch(() => undefined);
}

export async function clickNamed(page: Page, value: Match): Promise<void> {
  await clickLocated(page, await reach(page, value), value);
}

export async function hoverNamed(page: Page, value: Match): Promise<void> {
  const target = await reach(page, value);
  await target.hover({ timeout: 10_000 });
}

/** Navigate to where a named page/tab/menu entry is visible; click it when it is a control. */
export async function openNamed(page: Page, value: Match): Promise<void> {
  const target = await reach(page, value);
  const role = await target.evaluate((el) => (el.getAttribute('role') || el.tagName || '').toLowerCase()).catch(() => '');
  if (['a', 'button', 'tab', 'menuitem', 'link', 'option'].includes(role)) {
    await clickLocated(page, target, value);
  }
}

export async function pressKey(page: Page, key: string): Promise<void> {
  await page.keyboard.press(key);
  await page.waitForLoadState('domcontentloaded').catch(() => undefined);
  await page.waitForTimeout(250);
}

/** Prepare an explicit external clipboard fixture for a paste scenario. */
export async function setClipboardText(page: Page, value: string): Promise<void> {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.evaluate(async (text) => navigator.clipboard.writeText(text), value);
}

/** Verify a copied clone value through the browser clipboard, not its toast. */
export async function expectClipboard(page: Page, repository: string, protocol: 'HTTPS' | 'SSH'): Promise<void> {
  await page.context().grantPermissions(['clipboard-read']);
  const copied = await page.evaluate(async () => navigator.clipboard.readText());
  expect(copied, `clipboard value identifies ${repository}`).toContain(repository);
  if (protocol === 'HTTPS') {
    expect(copied, 'HTTPS clone value uses HTTPS').toMatch(/^https:\/\//i);
  } else {
    expect(copied, 'SSH clone value uses SSH and ends in .git').toMatch(/^(?:git@[^:]+:|ssh:\/\/).+\.git$/i);
  }
}

/** The page ended in no error state: no visible alert naming an error, no server error page. */
export async function expectNoErrorState(page: Page): Promise<void> {
  await page.waitForTimeout(300);
  const body = (await page.locator('body').innerText().catch(() => '')).slice(0, 4000);
  const fatal = /Cannot (?:GET|POST|PUT|DELETE) \/|Internal Server Error|Application error|Unexpected token|Not Found$/m;
  expect(body, `page shows a server error state on ${page.url()}`).not.toMatch(fatal);
  const alerts = page.locator('[role="alert"]:visible, .error:visible, [aria-invalid="true"]:visible');
  const count = await alerts.count().catch(() => 0);
  for (let index = 0; index < Math.min(count, 5); index += 1) {
    const text = (await alerts.nth(index).innerText().catch(() => '')).trim();
    expect(text, `an error is shown on ${page.url()}: ${text}`).not.toMatch(/error|invalid|failed|required|cannot|not allowed|denied/i);
  }
}

export async function expectAbsent(page: Page, value: Match): Promise<void> {
  await expect.poll(async () => Boolean(await visibleNamed(page, value, 200)), {
    message: `Expected "${describe(value)}" to be absent from ${page.url()}`,
    timeout: 8000,
  }).toBe(false);
}

function exactName(value: string): RegExp {
  return new RegExp('^\\s*' + escapeRegExp(value.trim()) + '\\s*$', 'i');
}

/** Session identity is visible text/control content, never a typed input value. */
export async function expectIdentity(page: Page, value: string, present = true): Promise<void> {
  const text = page.getByText(exactName(value));
  // getByText matches submit input values too; exclude every editable/input node.
  const identity = text.filter({ hasNot: page.locator('input, textarea, [contenteditable="true"]') });
  await expect.poll(async () => {
    for (const item of await identity.all()) {
      if (await item.isVisible() && await item.evaluate(el => !el.matches('input, textarea, [contenteditable="true"]'))) return true;
    }
    return false;
  }, { message: `Expected session identity ${value} to be ${present ? 'visible' : 'absent'}`, timeout: 8000 }).toBe(present);
}

/** An explicit ARIA promise of the requirement: an element with this role and accessible name. */
export async function expectRole(page: Page, role: string, name: string): Promise<void> {
  await settle(page);
  const locator = page.getByRole(role as any, { name: exactName(name) }).first();
  await expect(locator, `expected an element with role "${role}" named "${name}" on ${page.url()}`)
    .toBeVisible({ timeout: 8000 });
}

function cellLocator(page: Page, ref: string): Locator {
  return page.getByRole('gridcell', { name: exactName(ref) }).first();
}

export async function clickCell(page: Page, ref: string): Promise<void> {
  // "A1:B2" selects a range: click the first cell, shift-click the last.
  const [first, last] = ref.split(':');
  const cell = cellLocator(page, first);
  await expect(cell, `gridcell "${first}" is visible on ${page.url()}`).toBeVisible({ timeout: 8000 });
  await cell.click();
  if (last) {
    const end = cellLocator(page, last);
    await expect(end, `gridcell "${last}" is visible on ${page.url()}`).toBeVisible({ timeout: 8000 });
    await end.click({ modifiers: ['Shift'] });
  }
}

/** Select a cell and type into it; the caller commits with pressKey('Enter'). */
export async function typeInCell(page: Page, ref: string, value: string): Promise<void> {
  await clickCell(page, ref);
  await page.keyboard.type(value);
}

/** Right-click a gridcell: the grid context menu ("Paste"). */
export async function contextClickCell(page: Page, ref: string): Promise<void> {
  const cell = cellLocator(page, ref);
  await expect(cell, `gridcell "${ref}" is visible on ${page.url()}`).toBeVisible({ timeout: 8000 });
  await cell.click({ button: 'right' });
}

/** Right-click row header "2" (rowheader) or column header "B" (columnheader). */
export async function contextClickHeader(page: Page, name: string): Promise<void> {
  const role = /^\d+$/.test(name) ? 'rowheader' : 'columnheader';
  const header = page.getByRole(role, { name, exact: true }).first();
  await expect(header, `${role} "${name}" is visible on ${page.url()}`).toBeVisible({ timeout: 8000 });
  await header.click({ button: 'right' });
}

function cellParts(ref: string): [number, number] {
  const match = /^([A-Z]+)(\d+)$/.exec(ref);
  if (!match) throw new Error(`not a cell reference: ${ref}`);
  let column = 0;
  for (const char of match[1]) column = column * 26 + char.charCodeAt(0) - 64;
  return [column, Number(match[2])];
}

function cellName(column: number, row: number): string {
  let letters = '';
  for (let n = column; n > 0; n = Math.floor((n - 1) / 26)) letters = String.fromCharCode(65 + ((n - 1) % 26)) + letters;
  return `${letters}${row}`;
}

/** Exactly this rectangle is selected: aria-selected="true" inside, "false" on the cells just outside. */
export async function expectSelected(page: Page, range: string): Promise<void> {
  await settle(page);
  const [first, last = first] = range.split(':');
  const [c1, r1] = cellParts(first);
  const [c2, r2] = cellParts(last);
  const [left, right, top, bottom] = [Math.min(c1, c2), Math.max(c1, c2), Math.min(r1, r2), Math.max(r1, r2)];
  for (let row = top; row <= bottom; row += 1) {
    for (let column = left; column <= right; column += 1) {
      const ref = cellName(column, row);
      await expect(cellLocator(page, ref), `gridcell "${ref}" is selected on ${page.url()}`)
        .toHaveAttribute('aria-selected', 'true', { timeout: 8000 });
    }
  }
  const outside = [cellName(right + 1, top), cellName(left, bottom + 1)];
  if (left > 1) outside.push(cellName(left - 1, top));
  if (top > 1) outside.push(cellName(left, top - 1));
  for (const ref of outside) {
    const cell = cellLocator(page, ref);
    if (await cell.count()) {
      await expect(cell, `gridcell "${ref}" outside ${range} is not selected on ${page.url()}`)
        .toHaveAttribute('aria-selected', 'false', { timeout: 8000 });
    }
  }
}

/** Enter a scenario's own starting values (GIVEN "Scenario setup"): click, type, Enter per cell. */
export async function typeCells(page: Page, cells: Array<[string, string]>): Promise<void> {
  for (const [ref, value] of cells) {
    await typeInCell(page, ref, value);
    await page.keyboard.press('Enter');
  }
}

export async function expectCell(page: Page, ref: string, value: string): Promise<void> {
  await settle(page);
  const cell = cellLocator(page, ref);
  if (value === '') {
    await expect(cell, `gridcell "${ref}" is empty on ${page.url()}`).toHaveText(/^\s*$/, { timeout: 8000 });
    return;
  }
  await expect(cell, `gridcell "${ref}" shows "${value}" on ${page.url()}`)
    .toHaveText(new RegExp('^\\s*' + escapeRegExp(value) + '\\s*$'), { timeout: 8000 });
}

/** Choose a file in the file input the requirement names (label, aria-label or nearby button). */
export async function uploadFile(page: Page, value: Match, csv: string,
                                 fileName: 'derived-import.csv' | 'derived-invalid.csv' = 'derived-import.csv'): Promise<void> {
  const file = { name: fileName, mimeType: 'text/csv', buffer: Buffer.from(csv, 'utf8') };
  const named = page.getByLabel(toPatterns(value)[0]).first();
  if (await named.isVisible({ timeout: 1000 }).catch(() => false) && await named.getAttribute('type') === 'file') {
    await named.setInputFiles(file);
    return;
  }
  const input = page.locator('input[type="file"]').first();
  if (await input.count()) {
    await input.setInputFiles(file);
    return;
  }
  // A button that opens the native file chooser.
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser', { timeout: 10_000 }),
    clickNamed(page, value),
  ]);
  await chooser.setFiles(file);
}

/** Click a control and verify the downloaded file name and selected contents. */
export async function expectDownload(page: Page, value: Match, suffix: string, contains: string[] = []): Promise<void> {
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15_000 }),
    clickNamed(page, value),
  ]);
  const name = download.suggestedFilename();
  expect(name, `clicking "${describe(value)}" downloads a file ending with ${suffix}`).toMatch(
    new RegExp(escapeRegExp(suffix) + '$', 'i'));
  if (contains.length) {
    const failure = await download.failure();
    expect(failure, `download of ${name} completed`).toBeNull();
    const content = await readFile(await download.path(), 'utf8');
    for (const value of contains) {
      expect(content, `downloaded ${name} contains ${JSON.stringify(value)}`).toContain(value);
    }
  }
}

export async function checkNamed(page: Page, value: Match): Promise<void> {
  const target = await reach(page, value);
  await target.check().catch(async () => target.click());
}

/** Fill the field the requirement names. The name must be the control's label
 *  or accessible name: a grader locates "labelled controls" by label, so a field
 *  whose requirement text is only its placeholder fails here with the actual
 *  label (v10.0 github: label "Email or username", required "Username or email"). */
export async function fillField(page: Page, label: Match, value: string): Promise<void> {
  const labels = Array.isArray(label) ? label : [label];
  const patterns = labels.map((item) => item instanceof RegExp ? item : exactName(item));
  const candidates = patterns.flatMap((pattern) => [page.getByLabel(pattern),
    page.getByRole('textbox', { name: pattern }), page.getByRole('searchbox', { name: pattern }),
    page.getByRole('combobox', { name: pattern }), page.getByRole('spinbutton', { name: pattern })]);
  const visibleField = async (): Promise<Locator | null> => {
    for (const locator of candidates) {
      const candidate = locator.first();
      if (await candidate.isVisible({ timeout: 100 }).catch(() => false)) return candidate;
    }
    return null;
  };
  await expect.poll(async () => Boolean(await visibleField()), {
    message: `Field "${describe(label)}" was not available by its exact label on ${page.url()}`,
    timeout: 8000,
  }).toBe(true).catch(() => undefined);
  const field = await visibleField();
  if (field) {
    await field.fill(value);
    await expect(field, `Field "${describe(label)}" lost its value after filling on ${page.url()}`)
      .toHaveValue(value, { timeout: 3000 });
    return;
  }
  let placeholderOnly: Locator | null = null;
  for (const pattern of patterns) {
    const byPlaceholder = page.getByPlaceholder(pattern).first();
    if (!placeholderOnly && await byPlaceholder.isVisible({ timeout: 100 }).catch(() => false)) placeholderOnly = byPlaceholder;
  }
  if (placeholderOnly) {
    const actual = await placeholderOnly.evaluate((element) => {
      const input = element as HTMLInputElement;
      const labels = Array.from(input.labels || []).map((node) => (node.textContent || '').trim()).filter(Boolean);
      return input.getAttribute('aria-label') || labels.join(' ') || '(none)';
    }).catch(() => '(unknown)');
    throw new Error(`Field "${describe(label)}" matches only a placeholder on ${page.url()}; its label is "${actual}". `
      + 'Label the control with the exact text the requirement names (a placeholder is not a label).');
  }
  throw new Error(`Field "${describe(label)}" is not a visible exactly-labelled input on ${page.url()}`);
}

export async function expectTextsVisible(page: Page, values: Array<string | RegExp>): Promise<void> {
  for (const value of values) {
    await expect.poll(async () => Boolean(await visibleNamed(page, value, 200)), {
      message: `Expected "${describe(value)}" to be visible on ${page.url()}`,
      timeout: 5000,
    }).toBe(true);
  }
}

async function submitSignIn(page: Page, account: string, password: string): Promise<Locator> {
  const passwordField = page.locator('input[type="password"]:visible').first();
  const currentForm = page.locator('form').filter({ has: passwordField }).first();
  const hasCurrentForm = await currentForm.count() > 0;
  const currentScope = hasCurrentForm ? currentForm : page.locator('body');
  const currentSubmit = currentScope.getByRole('button', { name: /sign\s*in|log\s*in|login|continue/i }).first();
  const loginFormReady = (await passwordField.isVisible({ timeout: 500 }).catch(() => false))
    && ((hasCurrentForm && await currentSubmit.isVisible({ timeout: 100 }).catch(() => false))
      || /(?:sign[/-]?in|log[/-]?in|login)(?:\/|$)/i.test(new URL(page.url()).pathname));
  if (!loginFormReady) {
    await clickNamed(page, [/^\s*sign\s*in\s*$/i, /^\s*log\s*in\s*$/i, /sign\s*in|log\s*in|login/i]);
  }
  await expect(passwordField, 'the sign-in form shows a password field').toBeVisible();
  const form = page.locator('form').filter({ has: page.locator('input[type="password"]') }).first();
  const scope = (await form.count()) ? form : page.locator('body');
  const identity = scope.locator('input:not([type="password"]):not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="submit"])').first();
  await identity.fill(account);
  await scope.locator('input[type="password"]').first().fill(password);
  const submit = scope.getByRole('button', { name: /sign\s*in|log\s*in|login|submit|continue/i }).first();
  if (await submit.isVisible({ timeout: 500 }).catch(() => false)) await submit.click();
  else await scope.locator('input[type="password"]').first().press('Enter');
  return passwordField;
}

/** Sign in through the visible UI; succeeds when the password form is gone. */
export async function signIn(page: Page, account: string, password: string): Promise<void> {
  await submitSignIn(page, account, password);
  await expect(page.locator('input[type="password"]:visible'),
    `signing in as ${account} leaves the sign-in form`).toHaveCount(0, { timeout: 8000 });
  await expect.poll(async () => !(await signInEntryVisible(page)), {
    message: `signing in as ${account} did not establish a session: the sign-in entry is still shown`,
    timeout: 8000,
  }).toBe(true);
  signedInAs = account;
}

/** Invalid credentials must leave the login form and anonymous entry visible. */
export async function expectSignInRejected(page: Page, account: string, password: string): Promise<void> {
  await submitSignIn(page, account, password);
  await expect(page.locator('input[type="password"]:visible'),
    `credentials for ${account} unexpectedly established a session`).toHaveCount(1, { timeout: 8000 });
  await expect.poll(() => signInEntryVisible(page), {
    message: `rejected credentials for ${account} did not leave an anonymous sign-in entry`,
    timeout: 8000,
  }).toBe(true);
}
