import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-4: author requests and removes live eligible reviewer without confirmation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.pr(page,'review-request'); await h.button(page,'Reviewers').click(); await page.getByRole('textbox',{name:'Search',exact:true}).fill('bob-reviewer'); await h.option(page,'bob-reviewer'); await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toBeVisible()); await h.button(page,'Remove bob-reviewer').click(); await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toHaveCount(0));
});
