import { test as base, expect, type Page, type Locator } from '@playwright/test';
import { randomUUID } from 'node:crypto';

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
export async function signIn(p: Page, username = 'alice-dev', password = PASSWORD) {
  await home(p); await link(p, 'Sign in').click();
  await field(p, 'Username or email').fill(username); await field(p, 'Password').fill(password);
  await button(p, 'Sign in').click(); await expect(button(p, 'Account menu')).toBeVisible();
  await button(p, 'Account menu').click(); const account = username.includes('@') ? username.split('@')[0].replaceAll('.', '-') : username; await expect(text(p, account).first()).toBeVisible();
  await p.keyboard.press('Escape');
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
export async function option(p: Page, name: string) { await p.getByRole('option', { name, exact: true }).click(); }
export async function choose(p: Page | Locator, name: string, value: string) {
  const control = p.getByRole('combobox', { name, exact: true });
  if (await control.evaluate(el => el.tagName === 'SELECT')) await control.selectOption({ label: value });
  else { await control.click(); await p.getByRole('option', { name: value, exact: true }).click(); }
}
export function sidebar(p: Page, label: string) {
  // Select the complete metadata group below its shared sidebar/timeline owner.
  // This permits nested heading wrappers; a historical article is excluded.
  const other = ['Assignees', 'Labels', 'Milestone', 'Reviewers'].filter(n => n !== label);
  const condition = other.map(n => `@aria-label="${n}" or normalize-space(.)="${n}"`).join(' or ');
  return button(p, label).locator(`xpath=ancestor::*[not(.//article) and not(.//*[self::button or @role="button"][${condition}])][last()]`);
}
export async function unavailable(p: Page, name: string) {
  const control=button(p,name); if(await control.count()) await expect(control).toBeDisabled();
  else await expect(control).toHaveCount(0);
}
