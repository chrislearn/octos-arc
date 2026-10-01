import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-review-cycle: guide: new compare commit invalidates review/check, preserves comments and merges only after renewal", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const reviewer=await browser.newContext(), maintainer=await browser.newContext(), writer=await browser.newContext();
  try {
    const review=await reviewer.newPage(), merge=await maintainer.newPage(), write=await writer.newPage();
    const comment=h.unique('anchored'), firstSummary=h.unique('approved-old'), nextSummary=h.unique('approved-new');
    let oldRevision='';
    await test.step('Remember an immutable base revision before any mutation',async()=>{
      await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('guide-review-cycle')); await h.link(page,'Commits').click();
      await h.link(page,'Document search flow').click(); oldRevision=page.url();
      await expect(page.locator('body')).toContainText('export const search = "search flow";');
    });
    await test.step('Publish a line comment and approve the current compare commit',async()=>{
      await h.signIn(review,'bob-reviewer'); await h.pr(review,'guide-review-cycle'); await h.link(review,'Files changed').click();
      await h.button(review,'Add comment').first().click(); await h.field(review,'Comment').fill(comment); await h.button(review,'Add single comment').click();
      await h.button(review,'Review changes').click(); await h.field(review,'Summary').fill(firstSummary); await review.getByRole('radio',{name:'Approve',exact:true}).check(); await h.button(review,'Submit review').click();
      await h.persisted(review,()=>expect(h.text(review,comment).first()).toBeVisible());
    });
    await test.step('Approval and successful check together enable Maintain to merge',async()=>{
      await h.pr(page,'guide-review-cycle'); await h.choose(page,'test status','success'); await h.button(page,'Save').click(); await expect(h.text(page,'test: success')).toBeVisible();
      await h.signIn(merge,'spec-maintain'); await h.pr(merge,'guide-review-cycle'); await expect(h.button(merge,'Merge pull request')).toBeEnabled();
    });
    await test.step('The author advances only the compare branch with a real file commit',async()=>{
      await h.signIn(write,'spec-write'); await h.repo(write,h.fixtureRepo('guide-review-cycle')); await h.button(write,'Branch main').click(); await h.option(write,'feature-search');
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
      await expect(h.button(merge,'Reopen pull request')).toHaveCount(0); await h.repo(page,h.fixtureRepo('guide-review-cycle')); await h.link(page,'src').click(); await h.link(page,'search.ts').click();
      await h.persisted(page,()=>expect(h.text(page,'export const search = "reviewed second head";')).toBeVisible());
      await page.goto(oldRevision); await expect(page.locator('body')).toContainText('export const search = "search flow";'); await expect(page.locator('body')).not.toContainText('reviewed second head');
    });
  } finally { await reviewer.close(); await maintainer.close(); await writer.close(); }
});
