import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"team-maintainer"); await h.memberOrganization(page);await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Members').click(); await h.button(page,'Add member').click(); await h.field(page,'Username').fill('bob-reviewer'); await h.button(page,'Add member').click(); await h.persisted(page,()=>expect(h.button(page,'Remove bob-reviewer')).toBeVisible()); await h.button(page,'Remove bob-reviewer').click(); await h.persisted(page,()=>expect(h.button(page,'Remove bob-reviewer')).toHaveCount(0));
});

test("REQ-2-2-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"team-maintainer"); await h.memberOrganization(page);await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Settings').click(); const parent=h.field(page,'Parent team'); await expect(parent).toHaveValue('platform-team'); await parent.selectOption({label:'frontend-child'}); await h.button(page,'Save').click(); await expect(h.text(page,'Cyclic team hierarchy is not allowed')).toBeVisible(); await expect(parent).toHaveValue('platform-team'); await page.reload(); await expect(parent).toHaveValue('platform-team');
});

test("REQ-2-2-2: selftest keyboard organization entry reaches teams without a reload or search helper", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.button(page,'Account menu').press('ArrowDown');
  const organizations=h.link(page,'Your organizations');
  for (let step=0;step<10 && !await organizations.evaluate(element=>element===document.activeElement);step++) await page.keyboard.press('ArrowDown');
  await expect(organizations).toBeFocused(); await page.keyboard.press('Enter');
  await h.link(page,'Acme Demo').click(); await h.link(page,'Teams').click();
  await expect(h.link(page,'New team')).toBeVisible(); await h.link(page,'frontend-team').click();
  await expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toBeVisible();
  await h.link(page,'Settings').click(); await expect(h.field(page,'Parent team')).toBeVisible();
});

test("REQ-2-2-2: 44831560 regression: account menu organization entry exposes the named team without a data gap", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'team-maintainer'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
  await h.link(page,'Acme Demo').click(); await h.link(page,'Teams').click();
  expect(await h.link(page,'frontend-team').isVisible(),'named team must be ready after directory navigation').toBe(true);
  await h.link(page,'frontend-team').click(); await h.link(page,'Settings').click();
  await h.chosen(page,'Parent team','platform-team');
});

test("REQ-2-2-2: 44831560 regression: browser history cannot restore member-only team links after sign-out", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'team-maintainer'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
  await h.link(page,'Acme Demo').click(); await h.link(page,'Teams').click(); await expect(h.link(page,'frontend-team')).toBeVisible();
  await h.signOut(page); await expect(h.button(page,'Account menu')).toHaveCount(0);
  await page.goBack(); await expect(h.text(page,'Access denied')).toBeVisible();
  await expect(h.link(page,'frontend-team')).toHaveCount(0); await expect(h.link(page,'New team')).toHaveCount(0);
  await page.reload(); await expect(h.text(page,'Access denied')).toBeVisible();
});

test("REQ-2-2-2: eb7208fb compatibility: named team navigation keeps the settings entry usable", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'team-maintainer'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
  await h.link(page,'Acme Demo').click(); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click();
  expect(await h.link(page,'Settings').isVisible(),'team detail must retain its settings navigation while data loads').toBe(true);
  await h.link(page,'Settings').click(); await h.chosen(page,'Parent team','platform-team');
});

test("REQ-2-2-2: Owner adds and immediately removes direct team member with persistence", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'team-members'); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Members').click();
    await h.button(page,'Add member').click(); await h.field(page,'Username').fill('bob-reviewer'); await h.button(page,'Add member').click();
    await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toBeVisible()); await h.button(page,'Remove bob-reviewer').click(); await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toHaveCount(0));
});

test("REQ-2-2-2: cycle rejects and preserves original parent value across reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'team-cycle'); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Settings').click();
    await h.chosen(page,'Parent team','platform-team'); await h.choose(page,'Parent team','frontend-child'); await h.button(page,'Save').click(); await expect(h.text(page,'Cyclic team hierarchy is not allowed').first()).toBeVisible(); await h.chosen(page,'Parent team','platform-team'); await page.reload(); await h.chosen(page,'Parent team','platform-team');
});

test("REQ-2-2-2: valid parent change persists independently of the earlier parent relationship", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'team-parent-valid'); await h.link(page,'Teams').click();
    await h.link(page,'frontend-child').click(); await h.link(page,'Settings').click();
    await h.choose(page,'Parent team','platform-team'); await h.button(page,'Save').click();
    await h.persisted(page,()=>h.chosen(page,'Parent team','platform-team'));
    await h.choose(page,'Parent team','frontend-team'); await h.button(page,'Save').click();
    await h.persisted(page,()=>h.chosen(page,'Parent team','frontend-team'));
    await h.organization(page,'team-parent-valid'); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Settings').click();
    await h.persisted(page,()=>h.chosen(page,'Parent team','platform-team'));
});
