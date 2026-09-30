import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-2-2: Maintain saves issue title and body with separate commit actions and persists both", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-edit'); await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill('Updated onboarding title'); await h.button(page,'Save issue title').click(); await h.button(page,'Edit issue description').click(); await h.field(page,'Issue description').fill('Updated onboarding body'); await h.button(page,'Save issue description').click();
  await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Updated onboarding title',exact:true})).toBeVisible(); await expect(h.text(page,'Updated onboarding body').first()).toBeVisible(); });
});

test("REQ-5-2-2: blank edited title preserves exact original title after reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-edit-invalid','Original issue title'); await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill('   '); await h.button(page,'Save issue title').click(); await expect(page.getByText('Title is required',{exact:false})).toBeVisible(); await page.reload(); await expect(page.getByRole('heading',{name:'Original issue title',exact:true})).toBeVisible();
});

test("REQ-5-2-2: spec-read cannot edit issue content", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"spec-read"); await h.issue(page,'issue-edit-'+"spec-read");
  await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
  await h.persisted(page, () => expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible());
});

test("REQ-5-2-2: spec-triage cannot edit issue content", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"spec-triage"); await h.issue(page,'issue-edit-'+"spec-triage");
  await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
  await h.persisted(page, () => expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible());
});
