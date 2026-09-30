import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-2: Owner adds and immediately removes direct team member with persistence", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'team-members'); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Members').click();
  await h.button(page,'Add member').click(); await h.field(page,'Username').fill('bob-reviewer'); await h.button(page,'Add member').click();
  await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toBeVisible()); await h.button(page,'Remove bob-reviewer').click(); await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toHaveCount(0));
});

test("REQ-2-2-2: cycle rejects and preserves original parent value across reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-owner'); await h.organization(page,'team-cycle'); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Settings').click();
  const parent=h.field(page,'Parent team'); const original=await parent.inputValue(); await parent.selectOption({label:'frontend-child'}); await h.button(page,'Save').click(); await expect(h.text(page,'Cyclic team hierarchy is not allowed').first()).toBeVisible(); await expect(parent).toHaveValue(original); await page.reload(); await expect(parent).toHaveValue(original);
});
