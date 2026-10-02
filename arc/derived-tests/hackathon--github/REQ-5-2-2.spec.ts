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

test("REQ-5-2-2: home workspace: a newly created private issue can be renamed, rediscovered, and remains private after sign-out", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const account=await h.register(page); await h.signIn(page,account.username); await h.link(page,'New repository').click();
  const repository=h.unique('workspace-private'), title=h.unique('Workspace issue'), renamed=title+' renamed';
  await h.field(page,'Repository name').fill(repository); await page.getByRole('radio',{name:'Private',exact:true}).check();
  await h.button(page,'Create repository').click(); await h.link(page,'Issues').click(); await h.link(page,'New issue').click();
  await h.field(page,'Title').fill(title); await h.field(page,'Description').fill('Created through the visible interface.');
  await h.button(page,'Submit new issue').click(); await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
  await h.home(page); await h.link(page,title).click(); await h.button(page,'Edit issue title').click();
  await h.field(page,'Issue title').fill(renamed); await h.button(page,'Save issue title').click();
  await h.home(page); await expect(h.link(page,renamed)).toBeVisible(); await expect(h.link(page,title)).toHaveCount(0);
  await h.signOut(page); await expect(h.link(page,renamed)).toHaveCount(0); await page.reload();
  await expect(h.link(page,renamed)).toHaveCount(0); await expect(h.link(page,repository)).toHaveCount(0);
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
