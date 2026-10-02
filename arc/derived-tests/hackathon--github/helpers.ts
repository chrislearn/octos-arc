import { test as base, expect, type Page, type Locator } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import fixtures from './fixtures.json';

export { expect };
export const test = base.extend({ page: async ({ page, context }, use) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await use(page);
} });
export const PASSWORD = 'Valid-password-123!';
export const unique = (prefix = 'pw') => `${prefix}-${randomUUID().slice(0, 12)}`;
export const button = (p: Page | Locator, name: string) => p.getByRole('button', { name, exact: true });
export const link = (p: Page | Locator, name: string) => p.getByRole('link', { name, exact: true });
export const field = (p: Page | Locator, name: string) => p.getByLabel(name, { exact: true });
// Filled controls are not submission feedback. Wait for the public rendered
// result so a following reload cannot race the request while matching its input.
export const text = (p: Page | Locator, value: string) => p.getByText(value, { exact: true })
  .and(p.locator(':not(input):not(textarea):not([contenteditable="true"])'));
// Native select options contribute text matches even while hidden. Only inspect
// the rendered summary when the contract asks for visible text.
export const visibleText = (p: Page | Locator, value: string) => text(p, value).filter({ visible: true });
export const containsValue = (p: Page | Locator, value: string) => p.getByText(
  new RegExp(`(?<![\\w-])${value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\w-])`)
).and(p.locator(':not(input):not(textarea):not([contenteditable="true"])')).filter({ visible: true });
export const fileValidationReason = (p: Page) => p.getByText(/Invalid file path|Commit message is required/)
  .and(p.locator(':not(input):not(textarea):not([contenteditable="true"])')).filter({ visible: true });
export const passwordValidationReason = (p: Page) => p.getByText(/Current password is incorrect|Password confirmation does not match/)
  .and(p.locator(':not(input):not(textarea):not([contenteditable="true"])')).filter({ visible: true });
export async function accessPicker(p: Page) {
  const search = p.getByRole('textbox', { name: 'Search', exact: true });
  await expect(search).toBeVisible();
  // Find the nearest group containing the picker Search/Role/Add controls.
  // No mandated form tag, CSS class or application route is required.
  let group = search.locator('..');
  for (let depth = 0; depth < 20; depth++, group = group.locator('..')) {
    if (await group.getByRole('combobox', { name: 'Role', exact: true }).count() === 1
        && await button(group, 'Add').count() === 1) return group;
  }
  throw new Error('Access picker must group Search, Role and Add controls');
}
export async function historyLinks(p: Page) {
  // These immutable seed entries prove that the history has rendered; a
  // click/reload alone does not wait for a client-side router to finish.
  await expect(link(p, 'Document search flow')).toBeVisible();
  await expect(link(p, 'Initialize empty repository')).toBeVisible();
  return p.getByRole('link').allTextContents();
}
export async function home(p: Page) { await p.goto('/'); }
export async function signIn(p: Page, username = 'alice-dev', password = PASSWORD, expectedUsername?: string) {
  await home(p); await link(p, 'Sign in').click();
  await field(p, 'Username or email').fill(username); await field(p, 'Password').fill(password);
  await button(p, 'Sign in').click(); await expect(button(p, 'Account menu')).toBeVisible();
  const account = expectedUsername ?? (username.includes('@')
    ? fixtures.accounts.find(a => a.email === username)?.username : username);
  if (!account) throw new Error('Email sign-in needs the known account username');
  await button(p, 'Account menu').click(); await expect(containsValue(p, account).first()).toBeVisible();
  // A persisted session is required; reloading also closes transient menus
  // without assuming an unspecified Escape/toggle implementation.
  await p.reload(); await expect(button(p, 'Account menu')).toBeVisible();
}
export async function signOut(p: Page) {
  await button(p, 'Account menu').click(); await link(p, 'Sign out').click();
  await button(p.getByRole('dialog', { name: 'Sign out', exact: true }), 'Confirm sign out').click();
  await expect(link(p, 'Sign in')).toBeVisible();
}
export async function register(p: Page) {
  const username = unique('pw-user'), email = `${username}@example.test`;
  await home(p); await link(p, 'Sign in').click(); await link(p, 'Create an account').click();
  await field(p, 'Username').fill(username); await field(p, 'Email').fill(email);
  await field(p, 'Password').fill(PASSWORD); await field(p, 'Confirm password').fill(PASSWORD);
  await p.getByRole('checkbox', { name: 'Agree to the terms', exact: true }).check();
  await button(p, 'Create account').click(); await expect(field(p, 'Username or email')).toBeVisible();
  return { username, email };
}
export async function repo(p: Page, name = 'acme-docs') {
  await home(p); const search = p.getByRole('searchbox', { name: 'Search', exact: true });
  await search.fill(name); await search.press('Enter'); const matches = link(p, name); await expect(matches.first()).toBeVisible();
  if (name === 'acme-docs' && await matches.count() > 1) {
    const index = await matches.evaluateAll(els => els.findIndex(el => {
      for (let parent = el.parentElement; parent; parent = parent.parentElement) {
        const same = Array.from(parent.querySelectorAll('a')).filter(a => a.textContent?.trim() === 'acme-docs');
        if (same.length > 1) return false;
        if (parent.textContent?.includes('alice-dev/acme-docs')) return true;
      }
      return false;
    }));
    expect(index, 'repository result must expose its owner/name metadata').toBeGreaterThanOrEqual(0); await matches.nth(index).click();
  } else await matches.click();
  await expect(p.getByRole('heading').filter({ hasText: name })).toBeVisible();
  return p.url();
}
export const orgName = (caseId: string) => `spec-org-${caseId}`;
export async function organization(p: Page, caseId?: string) {
  const name = caseId ? orgName(caseId) : 'Acme Demo';
  await repo(p, caseId ? fixtureRepo(caseId) : 'acme-docs-org'); await link(p, name).click();
  await expect(p.getByRole('heading').filter({ hasText: name })).toBeVisible();
}
export async function settings(p: Page, section: string) { await link(p, 'Settings').click(); await link(p, section).click(); }
// Each mutable scenario has its own seeded repository. This avoids a reset API,
// serial dependencies and reuse of a mutable record by a sibling test.
export const fixtureRepo = (caseId: string) => `spec-${caseId.toLowerCase().replaceAll('_', '-')}`;
export async function issue(p: Page, caseId?: string, title = 'Improve onboarding') {
  await repo(p, caseId ? fixtureRepo(caseId) : 'acme-docs'); await link(p, 'Issues').click();
  await link(p, title).click(); await expect(p.getByRole('heading', { name: title, exact: true })).toBeVisible();
}
export async function pr(p: Page, caseId?: string, title = 'Improve onboarding') {
  await repo(p, caseId ? fixtureRepo(caseId) : 'acme-docs'); await link(p, 'Pull requests').click();
  await link(p, title).click(); await expect(p.getByRole('heading', { name: title, exact: true })).toBeVisible();
}
export async function compare(p: Page, caseId: string) {
  await repo(p, fixtureRepo(caseId)); await link(p, 'Pull requests').click(); await link(p, 'New pull request').click();
  await field(p, 'base').selectOption({ label: 'main' }); await field(p, 'compare').selectOption({ label: 'feature-search' });
  await button(p, 'Compare changes').click(); await expect(text(p, 'src/search.ts')).toBeVisible();
}
export async function persisted(p: Page, assertion: () => Promise<void>) { await assertion(); await p.reload(); await assertion(); }
export async function attemptSubmission(p: Page, submit: Locator) {
  // Observe a UI-triggered write without assuming any endpoint or payload.
  // Wait for the server to finish before navigating; otherwise reload may
  // cancel the write and make an invalid implementation appear to refuse it.
  const response = p.waitForResponse(r => !['GET', 'HEAD', 'OPTIONS'].includes(r.request().method()), { timeout: 2000 })
    .catch(error => { if (error.name === 'TimeoutError') return null; throw error; });
  await submit.click(); const result = await response;
  if (result) await result.finished();
}
export async function option(p: Page, name: string) { await p.getByRole('option', { name, exact: true }).click(); }
export async function choose(p: Page | Locator, name: string, value: string) {
  const control = p.getByRole('combobox', { name, exact: true });
  if (await control.evaluate(el => el.tagName === 'SELECT')) await control.selectOption({ label: value });
  else { await control.click(); await p.getByRole('option', { name: value, exact: true }).click(); }
}
export async function filterStatus(p: Page, status: string) {
  // Open is a source-prescribed link. The other status filters have no
  // prescribed role or field label: discover their displayed enum choices.
  const direct = link(p, status).or(button(p, status)).or(p.getByRole('tab', { name: status, exact: true }));
  if (await direct.count()) { await direct.first().click(); return; }
  for (const select of await p.locator('select').all()) {
    const option = select.getByRole('option', { name: status, exact: true, includeHidden: true });
    if (await option.count()) { await select.selectOption({ label: status }); return; }
  }
  for (const combo of await p.getByRole('combobox').all()) {
    await combo.click(); const option = p.getByRole('option', { name: status, exact: true });
    if (await option.count() && await option.first().isVisible()) { await option.first().click(); return; }
    await p.keyboard.press('Escape');
  }
  throw new Error(`No visible status-filter choice for ${status}; no private route is assumed`);
}
export function metadataValue(p: Page, label: string, value: string) {
  // Fixtures make each target value unique outside the discussion. Historical
  // articles and open selector options must never prove a current association.
  // No aside/section/grid nesting is prescribed by the original requirements.
  const area = button(p, label).locator('xpath=ancestor::*[not(.//article)][last()]');
  return containsValue(area, value)
    .and(area.locator(':not(article):not(article *):not(option):not([role="option"]):not([role="option"] *)'))
    .filter({ hasNot: p.getByRole('article') });
}
export async function discussionSnapshot(p: Page) {
  const entries = p.getByRole('article');
  await expect(entries.first()).toBeVisible();
  return entries.evaluateAll(elements => elements.map(el => {
    const copy = el.cloneNode(true) as Element;
    copy.querySelectorAll('time').forEach(time => time.remove());
    return (copy.textContent ?? '').replace(/\b\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago\b/g, '<relative time>').replace(/\s+/g, ' ').trim();
  }));
}
export async function unavailable(p: Page, name: string) {
  const control=button(p,name); if(await control.count()) await expect(control).toBeDisabled();
  else await expect(control).toHaveCount(0);
}
