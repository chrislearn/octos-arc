import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"team-maintainer"); await h.memberOrganization(page);await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Members').click(); await h.button(page,'Add member').click(); await h.field(page,'Username').fill('bob-reviewer'); await h.button(page,'Add member').click(); await h.persisted(page,()=>expect(h.button(page,'Remove bob-reviewer')).toBeVisible()); await h.button(page,'Remove bob-reviewer').click(); await h.persisted(page,()=>expect(h.button(page,'Remove bob-reviewer')).toHaveCount(0));
});

test("REQ-2-2-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"team-maintainer"); await h.memberOrganization(page);await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Settings').click(); const parent=h.field(page,'Parent team'),original=await parent.inputValue(); await parent.selectOption({label:'frontend-child'}); await h.button(page,'Save').click(); await expect(h.text(page,'Cyclic team hierarchy is not allowed')).toBeVisible(); await expect(parent).toHaveValue(original); await page.reload(); await expect(parent).toHaveValue(original);
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
