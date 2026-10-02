import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-4: Maintain closes and reopens issue preserving title, body and state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-close'); await h.button(page,'Close issue').click(); await expect(h.text(page,'Closed issue').first()).toBeVisible(); await expect(h.button(page,'Reopen issue')).toBeVisible(); await h.button(page,'Reopen issue').click(); await h.persisted(page, async () => { await expect(h.button(page,'Close issue')).toBeVisible(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.text(page,'Describe the onboarding improvement.').first()).toBeVisible(); });
});

test("REQ-5-4: Read viewer has neither issue status control", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.issue(page,'issue-read'); await expect(h.button(page,'Close issue')).toHaveCount(0); await expect(h.button(page,'Reopen issue')).toHaveCount(0); await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
});

test("REQ-5-4: guide: an Issue created by Write keeps comments and assignee across Maintain status changes", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const maintain=await browser.newContext(), reader=await browser.newContext();
  try {
    const manager=await maintain.newPage(), view=await reader.newPage();
    const title=h.unique('guided-issue'), comment=h.unique('guided-comment'); let address='';
    await test.step('Write creates the actual Issue and persists a discussion entry',async()=>{
      await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('guide-issue-lifecycle')); await h.link(page,'Issues').click(); await h.link(page,'New issue').click();
      await h.field(page,'Title').fill(title); await h.field(page,'Description').fill('Persist all fields through the lifecycle.'); await h.button(page,'Submit new issue').click();
      await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); address=page.url();
      await h.field(page,'Comment').fill(comment); await h.button(page,'Comment').click();
      await h.persisted(page,()=>expect(page.getByRole('article').filter({hasText:comment})).toContainText('spec-write'));
    });
    await test.step('Maintain resolves an eligible account, closes and reopens the same Issue',async()=>{
      await h.signIn(manager,'spec-maintain'); await manager.goto(address); await h.button(manager,'Assignees').click();
      await h.field(manager,'Search assignees').fill('spec-triage'); await h.option(manager,'spec-triage');
      await expect(h.sidebar(manager,'Assignees')).toContainText('spec-triage');
      await h.button(manager,'Close issue').click(); await expect(h.text(manager,'Closed issue').first()).toBeVisible();
      await h.button(manager,'Reopen issue').click(); await h.persisted(manager,()=>expect(h.button(manager,'Close issue')).toBeVisible());
    });
    await test.step('Read sees preserved fields and activity but has no mutation controls',async()=>{
      await h.signIn(view,'spec-read'); await view.goto(address);
      await h.persisted(view,async()=>{
        await expect(view.getByRole('heading',{name:title,exact:true})).toBeVisible();
        await expect(h.text(view,'Persist all fields through the lifecycle.')).toBeVisible();
        await expect(h.text(view,comment)).toBeVisible(); await expect(h.text(view,'spec-triage').first()).toBeVisible();
        await expect(h.text(view,'Closed issue').first()).toBeVisible(); await expect(h.text(view,'Reopened issue').first()).toBeVisible();
        await expect(h.button(view,'Close issue')).toHaveCount(0); await expect(h.button(view,'Reopen issue')).toHaveCount(0);
      });
    });
  } finally { await maintain.close(); await reader.close(); }
});
