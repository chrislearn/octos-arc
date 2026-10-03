import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-4: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-author"); await h.scenarioPr(page,"Reviewer request onboarding PR","acme-docs"); await h.button(page,'Reviewers').click(); await h.field(page,'Search').fill('bob-reviewer'); await h.option(page,'bob-reviewer'); await h.persisted(page,async()=>{await expect(h.text(page,'bob-reviewer')).toBeVisible(); await expect(h.button(page,'Remove bob-reviewer')).toBeVisible();}); await h.button(page,'Remove bob-reviewer').click(); await h.persisted(page,async()=>{await expect(h.text(page,'bob-reviewer')).toHaveCount(0); await expect(h.button(page,'Remove bob-reviewer')).toHaveCount(0);});
});

test("REQ-6-4: author requests and removes live eligible reviewer without confirmation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.pr(page,'review-request'); await h.button(page,'Reviewers').click(); await page.getByRole('textbox',{name:'Search',exact:true}).fill('bob-reviewer'); await h.option(page,'bob-reviewer'); await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toBeVisible()); await h.button(page,'Remove bob-reviewer').click(); await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toHaveCount(0));
});
