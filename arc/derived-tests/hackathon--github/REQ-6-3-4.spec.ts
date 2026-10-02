import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-3-4: Approve submission persists current-commit review", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,"review-approve"); await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click();
   await page.getByRole('radio',{name:"Approve",exact:true}).check(); await h.button(page,'Submit review').click();
  await h.persisted(page, async () => { await expect(h.text(page,"Approved").first()).toBeVisible();  });
});

test("REQ-6-3-4: Request changes submission persists current-commit review", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,"review-request-changes"); await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click();
  await (await h.reviewSummary(page)).fill("Please fix the search edge case"); await page.getByRole('radio',{name:"Request changes",exact:true}).check(); await h.button(page,'Submit review').click();
  await h.persisted(page, async () => { await expect(h.text(page,"Changes requested").first()).toBeVisible(); await expect(h.text(page,"Please fix the search edge case").first()).toBeVisible(); });
});

test("REQ-6-3-4: latest Approve replaces Request changes while retaining history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,'review-replace');
  for(const decision of ['Request changes','Approve']) { await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click(); await (await h.reviewSummary(page)).fill(`Decision: ${decision}`); await page.getByRole('radio',{name:decision,exact:true}).check(); await h.button(page,'Submit review').click(); }
  await h.signOut(page); await h.signIn(page,'spec-maintain'); await h.pr(page,'review-replace');
  await expect(h.text(page,'Decision: Request changes').first()).toBeVisible(); await expect(h.text(page,'Decision: Approve').first()).toBeVisible(); await expect(h.button(page,'Merge pull request')).toBeEnabled();
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
      await h.button(page,'Review changes').click(); await (await h.reviewSummary(page)).fill('Publish my current-commit draft');
      await page.getByRole('radio',{name:'Approve',exact:true}).check(); await h.button(page,'Submit review').click();
      await publicView.reload(); await expect(h.text(publicView,published).first()).toBeVisible(); await expect(h.text(publicView,privateDraft)).toHaveCount(0);
      await second.reload(); await expect(h.text(second,privateDraft).first()).toBeVisible();
    });
  } finally { await other.close(); await visitor.close(); }
});

test("REQ-6-3-4: author cannot persist a review decision", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.pr(page,'review-denied-author');
  await h.link(page,'Files changed').click(); await expect(h.text(page,'src/search.ts')).toBeVisible();
  const address=page.url(),summary=h.unique('forbidden-review');
  const open=h.button(page,'Review changes');
  if(await open.count() && await open.isVisible() && await open.isEnabled()) {
    await open.click(); const decision=page.getByRole('radio',{name:'Approve',exact:true});
    await decision.waitFor({state:'visible',timeout:2000}).catch(error=>{ if(error.name!=='TimeoutError') throw error; });
    if(await decision.count() && await decision.isVisible() && await decision.isEnabled()) {
      await decision.check(); if(await (await h.reviewSummary(page)).count()) await (await h.reviewSummary(page)).fill(summary);
      const submit=h.button(page,'Submit review'); if(await submit.count() && await submit.isEnabled()) await h.attemptSubmission(page,submit);
    }
  }
  await page.goto(address); await h.persisted(page,async()=>{
    await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
    await expect(h.text(page,'Open').first()).toBeVisible();
    await expect(h.containsValue(page,summary)).toHaveCount(0); await expect(h.text(page,'Approved')).toHaveCount(0);
  });
});

test("REQ-6-3-4: draft cannot persist a review decision", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,'review-denied-draft');
  await h.link(page,'Files changed').click(); await expect(h.text(page,'README.md')).toBeVisible();
  const address=page.url(),summary=h.unique('forbidden-review');
  const open=h.button(page,'Review changes');
  if(await open.count() && await open.isVisible() && await open.isEnabled()) {
    await open.click(); const decision=page.getByRole('radio',{name:'Approve',exact:true});
    await decision.waitFor({state:'visible',timeout:2000}).catch(error=>{ if(error.name!=='TimeoutError') throw error; });
    if(await decision.count() && await decision.isVisible() && await decision.isEnabled()) {
      await decision.check(); if(await (await h.reviewSummary(page)).count()) await (await h.reviewSummary(page)).fill(summary);
      const submit=h.button(page,'Submit review'); if(await submit.count() && await submit.isEnabled()) await h.attemptSubmission(page,submit);
    }
  }
  await page.goto(address); await h.persisted(page,async()=>{
    await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
    await expect(h.text(page,'Draft').first()).toBeVisible();
    await expect(h.containsValue(page,summary)).toHaveCount(0); await expect(h.text(page,'Approved')).toHaveCount(0);
  });
});

test("REQ-6-3-4: read cannot persist a review decision", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.pr(page,'review-denied-read');
  await h.link(page,'Files changed').click(); await expect(h.text(page,'src/search.ts')).toBeVisible();
  const address=page.url(),summary=h.unique('forbidden-review');
  const open=h.button(page,'Review changes');
  if(await open.count() && await open.isVisible() && await open.isEnabled()) {
    await open.click(); const decision=page.getByRole('radio',{name:'Approve',exact:true});
    await decision.waitFor({state:'visible',timeout:2000}).catch(error=>{ if(error.name!=='TimeoutError') throw error; });
    if(await decision.count() && await decision.isVisible() && await decision.isEnabled()) {
      await decision.check(); if(await (await h.reviewSummary(page)).count()) await (await h.reviewSummary(page)).fill(summary);
      const submit=h.button(page,'Submit review'); if(await submit.count() && await submit.isEnabled()) await h.attemptSubmission(page,submit);
    }
  }
  await page.goto(address); await h.persisted(page,async()=>{
    await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
    await expect(h.text(page,'Open').first()).toBeVisible();
    await expect(h.containsValue(page,summary)).toHaveCount(0); await expect(h.text(page,'Approved')).toHaveCount(0);
  });
});

test("REQ-6-3-4: triage cannot persist a review decision", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-triage'); await h.pr(page,'review-denied-triage');
  await h.link(page,'Files changed').click(); await expect(h.text(page,'src/search.ts')).toBeVisible();
  const address=page.url(),summary=h.unique('forbidden-review');
  const open=h.button(page,'Review changes');
  if(await open.count() && await open.isVisible() && await open.isEnabled()) {
    await open.click(); const decision=page.getByRole('radio',{name:'Approve',exact:true});
    await decision.waitFor({state:'visible',timeout:2000}).catch(error=>{ if(error.name!=='TimeoutError') throw error; });
    if(await decision.count() && await decision.isVisible() && await decision.isEnabled()) {
      await decision.check(); if(await (await h.reviewSummary(page)).count()) await (await h.reviewSummary(page)).fill(summary);
      const submit=h.button(page,'Submit review'); if(await submit.count() && await submit.isEnabled()) await h.attemptSubmission(page,submit);
    }
  }
  await page.goto(address); await h.persisted(page,async()=>{
    await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
    await expect(h.text(page,'Open').first()).toBeVisible();
    await expect(h.containsValue(page,summary)).toHaveCount(0); await expect(h.text(page,'Approved')).toHaveCount(0);
  });
});
