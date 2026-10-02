import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-3-3: milestone selection saves immediately and None removes only association", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-milestone'); await h.button(page,'Milestone').click(); await h.option(page,'v1.0'); await h.persisted(page, () => expect(h.metadataValue(page,'Milestone','v1.0').first()).toBeVisible()); await h.button(page,'Milestone').click(); await h.option(page,'None'); await h.persisted(page, () => expect(h.metadataValue(page,'Milestone','v1.0').first()).toHaveCount(0));
});
