import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-3-4: Approve submission persists current-commit review", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,"review-approve"); await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click();
   await page.getByRole('radio',{name:"Approve",exact:true}).check(); await h.button(page,'Submit review').click();
  await h.persisted(page, () => expect(h.text(page,"Approved").first()).toBeVisible());
});

test("REQ-6-3-4: Request changes submission persists current-commit review", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,"review-request-changes"); await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click();
  await h.field(page,"Summary").fill("Please fix the search edge case"); await page.getByRole('radio',{name:"Request changes",exact:true}).check(); await h.button(page,'Submit review').click();
  await h.persisted(page, () => expect(h.text(page,"Changes requested").first()).toBeVisible());
});

test("REQ-6-3-4: Comment submission persists current-commit review", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,"review-decision-comment"); await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click();
  await h.field(page,"Summary").fill("Please fix the search edge case"); await page.getByRole('radio',{name:"Comment",exact:true}).check(); await h.button(page,'Submit review').click();
  await h.persisted(page, () => expect(h.text(page,"Please fix the search edge case").first()).toBeVisible());
});

test("REQ-6-3-4: latest Comment replaces Request changes while retaining history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,'review-replace');
  for(const decision of ['Request changes','Comment']) { await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click(); await h.field(page,'Summary').fill(`Decision: ${decision}`); await page.getByRole('radio',{name:decision,exact:true}).check(); await h.button(page,'Submit review').click(); }
  await h.signOut(page); await h.signIn(page,'spec-maintain'); await h.pr(page,'review-replace');
  await expect(h.text(page,'Decision: Request changes').first()).toBeVisible(); await expect(h.text(page,'Decision: Comment').first()).toBeVisible(); await expect(h.button(page,'Merge pull request')).toBeEnabled();
});

test("REQ-6-3-4: guide: submitting one review publishes only that reviewers drafts", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const other=await browser.newContext(), visitor=await browser.newContext();
  try {
    const second=await other.newPage(), publicView=await visitor.newPage();
    const published=h.unique('published-draft'), privateDraft=h.unique('private-draft'); let address='';
    await test.step('Two non-author reviewers independently retain private draft comments',async()=>{
      await h.signIn(page,'bob-reviewer'); await h.pr(page,'guide-review-publication'); await h.link(page,'Files changed').click(); address=page.url();
      await h.button(page,'Add comment').first().click(); await h.field(page,'Comment').fill(published); await h.button(page,'Start a review').click();
      await h.persisted(page,()=>expect(h.text(page,published).first()).toBeVisible());
      await h.signIn(second,'spec-maintain'); await second.goto(address);
      await expect(h.text(second,published)).toHaveCount(0);
      await h.button(second,'Add comment').first().click(); await h.field(second,'Comment').fill(privateDraft); await h.button(second,'Start a review').click();
      await h.persisted(second,()=>expect(h.text(second,privateDraft).first()).toBeVisible());
      await publicView.goto(address); await expect(h.text(publicView,published)).toHaveCount(0); await expect(h.text(publicView,privateDraft)).toHaveCount(0);
    });
    await test.step('Submitting Bob’s review publicly releases his comment and retains the other draft',async()=>{
      await h.button(page,'Review changes').click(); await h.field(page,'Summary').fill('Publish my current-commit draft');
      await page.getByRole('radio',{name:'Comment',exact:true}).check(); await h.button(page,'Submit review').click();
      await publicView.reload(); await expect(h.text(publicView,published).first()).toBeVisible(); await expect(h.text(publicView,privateDraft)).toHaveCount(0);
      await second.reload(); await expect(h.text(second,privateDraft).first()).toBeVisible(); await expect(h.text(second,'Pending review').first()).toBeVisible();
    });
  } finally { await other.close(); await visitor.close(); }
});
