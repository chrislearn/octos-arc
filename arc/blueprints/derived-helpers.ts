// Helpers for tests derived mechanically from requirements.yaml (not official).
// Locators are as tolerant as the official ARC-Bench helpers: any role, label,
// placeholder or text; case-insensitive; first visible match. Navigation is
// more tolerant still: a named control that is not on screen is searched for
// through a bounded crawl of links, tabs and menus, because requirements name
// controls but rarely the path to them.
import { expect, Locator, Page } from '@playwright/test';

type Match = string | RegExp | Array<string | RegExp>;

const DESTRUCTIVE = /sign\s*out|log\s*out|delete|remove|close|merge|archive|trash|leave|reset|cancel|discard|revoke|transfer/i;

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

async function navigationCandidates(page: Page): Promise<Step[]> {
  const raw: Array<{ role: Step['role']; name: string }> = await page.evaluate(() => {
    const visible = (el: Element) => {
      const box = (el as HTMLElement).getBoundingClientRect();
      const style = getComputedStyle(el as HTMLElement);
      return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const nameOf = (el: Element) => ((el.getAttribute('aria-label') || (el as HTMLElement).innerText || '')
      .replace(/\s+/g, ' ').trim()).slice(0, 80);
    const out: Array<{ role: string; name: string }> = [];
    for (const el of Array.from(document.querySelectorAll('a[href]'))) {
      const href = el.getAttribute('href') || '';
      if (!href || href.startsWith('#') || /^(mailto|tel|javascript):/i.test(href) || el.hasAttribute('download')) continue;
      try { if (new URL(href, location.href).origin !== location.origin) continue; } catch { continue; }
      if (visible(el)) out.push({ role: 'link', name: nameOf(el) });
    }
    for (const el of Array.from(document.querySelectorAll('[role="tab"]'))) if (visible(el)) out.push({ role: 'tab', name: nameOf(el) });
    for (const el of Array.from(document.querySelectorAll('[role="menuitem"]'))) if (visible(el)) out.push({ role: 'menuitem', name: nameOf(el) });
    for (const el of Array.from(document.querySelectorAll('button[aria-haspopup], [role="button"][aria-haspopup], button[aria-expanded="false"]'))) {
      if (visible(el)) out.push({ role: 'button', name: nameOf(el) });
    }
    return out as any;
  });
  const seen = new Map<string, number>();
  const steps: Step[] = [];
  for (const item of raw) {
    if (!item.name || DESTRUCTIVE.test(item.name)) continue;
    const key = `${item.role}|${item.name}`;
    const nth = seen.get(key) ?? 0;
    seen.set(key, nth + 1);
    if (nth === 0) steps.push({ role: item.role, name: item.name, nth });
  }
  return steps.slice(0, 24);
}

async function clickStep(page: Page, step: Step): Promise<void> {
  const locator = page.getByRole(step.role, { name: step.name, exact: true }).nth(step.nth);
  await locator.click({ timeout: 3000 });
  await page.waitForLoadState('domcontentloaded').catch(() => undefined);
  await page.waitForTimeout(250);
}

/** Find a named control or text, crawling at most `depth` navigation clicks. */
export async function reach(page: Page, value: Match, depth = 4, budget = 80): Promise<Locator> {
  const direct = await visibleNamed(page, value, 1500);
  if (direct) return direct;
  const start = page.url();
  const queue: Step[][] = [[]];
  const explored = new Set<string>();
  const tried: string[] = [];
  let visits = 0;
  while (queue.length && visits < budget) {
    const path = queue.shift()!;
    if (path.length) {
      visits += 1;
      try {
        await page.goto(start);
        for (const step of path) await clickStep(page, step);
      } catch {
        continue;
      }
      const hit = await visibleNamed(page, value, 400);
      if (hit) return hit;
      tried.push(path.map((s) => s.name).join(' > '));
    }
    const state = `${page.url()}|${await page.locator('[role="menu"]:visible').count().catch(() => 0)}`;
    if (explored.has(state) || path.length >= depth) continue;
    explored.add(state);
    for (const step of await navigationCandidates(page)) {
      if (!path.some((s) => s.role === step.role && s.name === step.name)) queue.push([...path, step]);
    }
  }
  await page.goto(start).catch(() => undefined);
  throw new Error(`Required control or text "${describe(value)}" is not reachable within ${depth} navigation `
    + `clicks from ${start}. Explored: ${tried.slice(0, 12).join('; ') || '(no navigation controls)'}`);
}

export async function openHome(page: Page): Promise<void> {
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');
}

export async function expectReachable(page: Page, value: Match): Promise<void> {
  const target = await reach(page, value);
  await expect(target).toBeVisible();
}

export async function clickNamed(page: Page, value: Match): Promise<void> {
  const target = await reach(page, value);
  await target.click();
  await page.waitForLoadState('domcontentloaded').catch(() => undefined);
}

export async function checkNamed(page: Page, value: Match): Promise<void> {
  const target = await reach(page, value);
  await target.check().catch(async () => target.click());
}

export async function fillField(page: Page, label: Match, value: string): Promise<void> {
  for (const pattern of toPatterns(label)) {
    for (const locator of [page.getByLabel(pattern), page.getByPlaceholder(pattern),
      page.getByRole('textbox', { name: pattern }), page.getByRole('searchbox', { name: pattern })]) {
      const candidate = locator.first();
      if (await candidate.isVisible({ timeout: 500 }).catch(() => false)) {
        await candidate.fill(value);
        return;
      }
    }
  }
  const field = await reach(page, label);
  await field.fill(value);
}

export async function expectTextsVisible(page: Page, values: Array<string | RegExp>): Promise<void> {
  for (const value of values) {
    await expect.poll(async () => Boolean(await visibleNamed(page, value, 200)), {
      message: `Expected "${describe(value)}" to be visible on ${page.url()}`,
      timeout: 8000,
    }).toBe(true);
  }
}

/** Sign in through the visible UI; succeeds when the password form is gone. */
export async function signIn(page: Page, account: string, password: string): Promise<void> {
  const passwordField = page.locator('input[type="password"]:visible').first();
  if (!(await passwordField.isVisible({ timeout: 1500 }).catch(() => false))) {
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
  await expect(page.locator('input[type="password"]:visible'),
    `signing in as ${account} leaves the sign-in form`).toHaveCount(0, { timeout: 8000 });
}
