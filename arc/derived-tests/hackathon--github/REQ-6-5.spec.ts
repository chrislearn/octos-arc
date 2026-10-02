import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-5: Maintain merge commits actual changes to base branch and persists terminal status", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-success'); await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click(); await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible()); await expect(h.button(page,'Close pull request')).toHaveCount(0); await expect(h.button(page,'Reopen pull request')).toHaveCount(0);
  await h.repo(page,h.fixtureRepo('merge-success')); await h.button(page,'Branch main').click(); await h.option(page,'main'); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await expect(h.text(page,'export const search = "merged search flow";')).toBeVisible();
});

test("REQ-6-5: missing required approval blocks merge before click and retains PR and branch", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-blocked'); await expect(h.button(page,'Merge pull request')).toBeDisabled(); await expect(h.text(page,'Review required by branch protection').first()).toBeVisible(); await h.persisted(page, () => expect(h.button(page,'Merge pull request')).toBeDisabled()); await expect(h.text(page,'Open').first()).toBeVisible(); await h.repo(page,h.fixtureRepo('merge-blocked')); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await expect(h.text(page,'export const search = "search flow";')).toBeVisible();
});

test("REQ-6-5: check-only enforces only its configured merge prerequisites", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,"merge-check-only");
  await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click();
  await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible());
});

test("REQ-6-5: approval-only enforces only its configured merge prerequisites", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,"merge-approval-only");
  await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click();
  await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible());
});

test("REQ-6-5: unprotected enforces only its configured merge prerequisites", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,"merge-unprotected");
  await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click();
  await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible());
});

test("REQ-6-5: current Request changes blocks an otherwise unprotected PR", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-request-changes'); await h.persisted(page, () => expect(h.button(page,'Merge pull request')).toBeDisabled()); await expect(h.text(page,'Open').first()).toBeVisible();
});

test("REQ-6-5: old-commit approval cannot satisfy a protected current-commit PR", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-stale-approval'); await expect(h.button(page,'Merge pull request')).toBeDisabled(); await expect(h.text(page,'Review required by branch protection').first()).toBeVisible(); await page.reload(); await expect(h.button(page,'Merge pull request')).toBeDisabled();
});

test("REQ-6-5: write cannot merge or change the base branch", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.pr(page,'merge-denied-write'); const address=page.url();
  await expect(h.text(page,'Open').first()).toBeVisible();
  const merge=h.button(page,'Merge pull request');
  if(await merge.count() && await merge.isVisible() && await merge.isEnabled()) {
    await merge.click(); const confirm=h.button(page,'Confirm merge');
    await confirm.waitFor({state:'visible',timeout:2000}).catch(error=>{ if(error.name!=='TimeoutError') throw error; });
    if(await confirm.count() && await confirm.isVisible() && await confirm.isEnabled()) await h.attemptSubmission(page,confirm);
  }
  await page.goto(address); await h.persisted(page,async()=>{ await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'Merged')).toHaveCount(0); });
  await h.repo(page,h.fixtureRepo('merge-denied-write')); await h.link(page,'src').click(); await h.link(page,'search.ts').click();
  await h.persisted(page,()=>expect(h.text(page,'export const search = "search flow";')).toBeVisible());
});

test("REQ-6-5: read cannot merge or change the base branch", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.pr(page,'merge-denied-read'); const address=page.url();
  await expect(h.text(page,'Open').first()).toBeVisible();
  const merge=h.button(page,'Merge pull request');
  if(await merge.count() && await merge.isVisible() && await merge.isEnabled()) {
    await merge.click(); const confirm=h.button(page,'Confirm merge');
    await confirm.waitFor({state:'visible',timeout:2000}).catch(error=>{ if(error.name!=='TimeoutError') throw error; });
    if(await confirm.count() && await confirm.isVisible() && await confirm.isEnabled()) await h.attemptSubmission(page,confirm);
  }
  await page.goto(address); await h.persisted(page,async()=>{ await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'Merged')).toHaveCount(0); });
  await h.repo(page,h.fixtureRepo('merge-denied-read')); await h.link(page,'src').click(); await h.link(page,'search.ts').click();
  await h.persisted(page,()=>expect(h.text(page,'export const search = "search flow";')).toBeVisible());
});

test("REQ-6-5: triage cannot merge or change the base branch", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-triage'); await h.pr(page,'merge-denied-triage'); const address=page.url();
  await expect(h.text(page,'Open').first()).toBeVisible();
  const merge=h.button(page,'Merge pull request');
  if(await merge.count() && await merge.isVisible() && await merge.isEnabled()) {
    await merge.click(); const confirm=h.button(page,'Confirm merge');
    await confirm.waitFor({state:'visible',timeout:2000}).catch(error=>{ if(error.name!=='TimeoutError') throw error; });
    if(await confirm.count() && await confirm.isVisible() && await confirm.isEnabled()) await h.attemptSubmission(page,confirm);
  }
  await page.goto(address); await h.persisted(page,async()=>{ await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'Merged')).toHaveCount(0); });
  await h.repo(page,h.fixtureRepo('merge-denied-triage')); await h.link(page,'src').click(); await h.link(page,'search.ts').click();
  await h.persisted(page,()=>expect(h.text(page,'export const search = "search flow";')).toBeVisible());
});

test("REQ-6-5: a failed required check blocks an otherwise approved PR", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-check-failure');
  await h.persisted(page,async()=>{ await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.button(page,'Merge pull request')).toBeDisabled(); });
  await h.repo(page,h.fixtureRepo('merge-check-failure')); await h.link(page,'src').click(); await h.link(page,'search.ts').click();
  await h.persisted(page,()=>expect(h.text(page,'export const search = "search flow";')).toBeVisible());
});

test("REQ-6-5: context REQ-6-2-1: Open Draft Closed and actual Merged status filters isolate records and retain other PRs", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); const address=await h.repo(page,h.fixtureRepo('pr-filter-lifecycle-node'));
  await h.link(page,'Pull requests').click(); const list=page.url();
  for(const [status,title] of [['Open','Improve onboarding'],['Draft','Draft onboarding update'],['Closed','Fix search']]) {
    await h.filterStatus(page,status); await h.persisted(page,async()=>{
      await expect(h.link(page,title)).toBeVisible();
      for(const other of ['Improve onboarding','Draft onboarding update','Fix search'].filter(name=>name!==title)) await expect(h.link(page,other)).toHaveCount(0);
    });
  }
  await h.filterStatus(page,'Open'); await h.link(page,'Improve onboarding').click();
  await h.button(page,'Merge pull request').click(); await h.button(page,'Confirm merge').click(); await expect(h.text(page,'Merged').first()).toBeVisible();
  await page.goto(list); await h.filterStatus(page,'Merged');
  await h.persisted(page,async()=>{ await expect(h.link(page,'Improve onboarding')).toBeVisible(); await expect(h.link(page,'Fix search')).toHaveCount(0); await expect(h.link(page,'Draft onboarding update')).toHaveCount(0); });
  await h.filterStatus(page,'Draft'); await expect(h.link(page,'Draft onboarding update')).toBeVisible();
  await h.filterStatus(page,'Closed'); await expect(h.link(page,'Fix search')).toBeVisible();
});

test("REQ-6-5: context REQ-6-5: guide: new compare commit invalidates review/check, preserves comments and merges only after renewal", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const reviewer=await browser.newContext(), maintainer=await browser.newContext(), writer=await browser.newContext();
  try {
    const review=await reviewer.newPage(), merge=await maintainer.newPage(), write=await writer.newPage();
    const comment=h.unique('anchored'), firstSummary=h.unique('approved-old'), nextSummary=h.unique('approved-new');
    let oldRevision='';
    await test.step('Remember an immutable base revision before any mutation',async()=>{
      await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('guide-review-cycle-node')); await h.link(page,'Commits').click();
      await h.link(page,'Document search flow').click(); oldRevision=page.url();
      await expect(page.locator('body')).toContainText('export const search = "search flow";');
    });
    await test.step('Publish a line comment and approve the current compare commit',async()=>{
      await h.signIn(review,'bob-reviewer'); await h.pr(review,'guide-review-cycle-node'); await h.link(review,'Files changed').click();
      await h.button(review,'Add comment').first().click(); await h.field(review,'Comment').fill(comment); await h.button(review,'Add single comment').click();
      await h.button(review,'Review changes').click(); await h.field(review,'Summary').fill(firstSummary); await review.getByRole('radio',{name:'Approve',exact:true}).check(); await h.button(review,'Submit review').click();
      await h.persisted(review,()=>expect(h.text(review,comment).first()).toBeVisible());
    });
    await test.step('Approval and successful check together enable Maintain to merge',async()=>{
      await h.pr(page,'guide-review-cycle-node'); await h.choose(page,'test status','success'); await h.button(page,'Save').click(); await expect(h.text(page,'test: success')).toBeVisible();
      await h.signIn(merge,'spec-maintain'); await h.pr(merge,'guide-review-cycle-node'); await expect(h.button(merge,'Merge pull request')).toBeEnabled();
    });
    await test.step('The author advances only the compare branch with a real file commit',async()=>{
      await h.signIn(write,'spec-write'); await h.repo(write,h.fixtureRepo('guide-review-cycle-node')); await h.button(write,'Branch main').click(); await h.option(write,'feature-search');
      await h.link(write,'src').click(); await h.link(write,'search.ts').click(); await h.button(write,'Edit').click();
      await h.field(write,'File contents').fill('export const search = "reviewed second head";'); await h.field(write,'Commit message').fill('Advance compare for renewed review'); await h.button(write,'Commit changes').click();
      await h.persisted(write,()=>expect(h.text(write,'export const search = "reviewed second head";')).toBeVisible());
    });
    await test.step('Old decisions/check no longer satisfy protection; old line comment remains Outdated',async()=>{
      await merge.reload(); await expect(h.button(merge,'Merge pull request')).toBeDisabled(); await expect(h.text(merge,'Review required by branch protection')).toBeVisible();
      await page.reload(); await expect(h.text(page,'test: pending')).toBeVisible(); await review.reload();
      await expect(h.text(review,firstSummary)).toBeVisible(); await expect(h.text(review,comment).first()).toBeVisible();
      // Outdated is required for the anchored comment. Stale review decisions
      // are proved by the merge gate; their history needs no extra UI badge.
      // Exclude the neighbouring review so its badge cannot satisfy this check.
      const marked=h.text(review,comment).first().locator(`xpath=ancestor::*[.//*[normalize-space(.)="Outdated"] and not(.//*[normalize-space(.)="${firstSummary}"])][1]`);
      await expect(h.text(marked,'Outdated').first()).toBeVisible();
    });
    await test.step('A renewed approval alone is insufficient until Admin sets the current check',async()=>{
      await h.button(review,'Review changes').click(); await h.field(review,'Summary').fill(nextSummary); await review.getByRole('radio',{name:'Approve',exact:true}).check(); await h.button(review,'Submit review').click();
      await expect(h.text(review,nextSummary)).toBeVisible(); await merge.reload(); await expect(h.button(merge,'Merge pull request')).toBeDisabled();
      await h.choose(page,'test status','success'); await h.button(page,'Save').click(); await expect(h.text(page,'test: success')).toBeVisible();
      await merge.reload(); await expect(h.button(merge,'Merge pull request')).toBeEnabled(); await h.button(merge,'Merge pull request').click(); await h.button(merge,'Confirm merge').click(); await h.persisted(merge,()=>expect(h.text(merge,'Merged').first()).toBeVisible());
    });
    await test.step('Merged base has the new bytes, terminal status and unchanged historical revision',async()=>{
      await expect(h.button(merge,'Reopen pull request')).toHaveCount(0); await h.repo(page,h.fixtureRepo('guide-review-cycle-node')); await h.link(page,'src').click(); await h.link(page,'search.ts').click();
      await h.persisted(page,()=>expect(h.text(page,'export const search = "reviewed second head";')).toBeVisible());
      await page.goto(oldRevision); await expect(page.locator('body')).toContainText('export const search = "search flow";'); await expect(page.locator('body')).not.toContainText('reviewed second head');
    });
  } finally { await reviewer.close(); await maintainer.close(); await writer.close(); }
});
