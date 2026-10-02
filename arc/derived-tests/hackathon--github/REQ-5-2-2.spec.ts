import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-2-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"issue-editor"); await h.scenarioIssue(page,"Editable onboarding issue"); const title=h.unique('updated-title'),body=h.unique('updated-body'); await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill(title); await h.button(page,'Save issue title').click(); await h.button(page,'Edit issue description').click(); await h.field(page,'Issue description').fill(body); await h.button(page,'Save issue description').click(); await h.persisted(page,async()=>{await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,body).first()).toBeVisible();});
});

test("REQ-5-2-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"issue-editor"); await h.scenarioIssue(page,"Original issue title"); await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill('   '); await h.button(page,'Save issue title').click(); await expect(h.titleRequiredReason(page).first()).toBeVisible(); await page.reload(); await expect(page.getByRole('heading',{name:'Original issue title',exact:true})).toBeVisible();
});

test("REQ-5-2-2: Maintain saves issue title and body with separate commit actions and persists both", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'pr-maintainer'); await h.issue(page,'issue-edit'); await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill('Updated onboarding title'); await h.button(page,'Save issue title').click(); await h.button(page,'Edit issue description').click(); await h.field(page,'Issue description').fill('Updated onboarding body'); await h.button(page,'Save issue description').click();
    await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Updated onboarding title',exact:true})).toBeVisible(); await expect(h.text(page,'Updated onboarding body').first()).toBeVisible(); });
});

test("REQ-5-2-2: blank edited title preserves exact original title after reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'pr-maintainer'); await h.issue(page,'issue-edit-invalid','Original issue title'); await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill('   '); await h.button(page,'Save issue title').click(); await expect(h.titleRequiredReason(page).first()).toBeVisible(); await page.reload(); await expect(page.getByRole('heading',{name:'Original issue title',exact:true})).toBeVisible();
});

test("REQ-5-2-2: issue-viewer cannot edit issue content", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"issue-viewer"); await h.issue(page,'issue-edit-'+"issue-viewer");
    await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
    await h.persisted(page, () => expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible());
});

test("REQ-5-2-2: triage-collaborator cannot edit issue content", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"triage-collaborator"); await h.issue(page,'issue-edit-'+"triage-collaborator");
    await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
    await h.persisted(page, () => expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible());
});

test("REQ-5-2-2: Write saves title and description independently without Triage metadata authority", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.issue(page,'issue-write-edit'); const title=h.unique('write-title'), body=h.unique('write-body');
    await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill(title); await h.button(page,'Save issue title').click();
    await h.persisted(page,async()=>{await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible();});
    await h.button(page,'Edit issue description').click(); await h.field(page,'Issue description').fill(body); await h.button(page,'Save issue description').click();
    await h.persisted(page,async()=>{await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();await expect(h.text(page,body)).toBeVisible();});
    for(const control of ['Assignees','Labels','Milestone']) await h.unavailable(page,control);
});
