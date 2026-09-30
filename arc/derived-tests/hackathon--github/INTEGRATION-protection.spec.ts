import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-protection: Admin changes current compare-commit check pending to success and persists setter", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-admin'); await h.pr(page,'check-success'); await expect(h.text(page,'test: pending').first()).toBeVisible(); await h.choose(page,'test status','success'); await h.button(page,'Save').click(); await h.persisted(page, async () => { await expect(h.text(page,'test: success').first()).toBeVisible(); await expect(h.text(page,'spec-admin').last()).toBeVisible(); });
});
