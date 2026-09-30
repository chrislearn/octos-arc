import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

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
