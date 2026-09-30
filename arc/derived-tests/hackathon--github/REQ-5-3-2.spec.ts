import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-3-2: existing label toggle immediately saves and removes association", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-label'); await h.button(page,'Labels').click(); await h.option(page,'bug'); await h.persisted(page, () => expect(h.sidebar(page,'Labels')).toContainText('bug')); await h.button(page,'Labels').click(); await h.option(page,'bug'); await h.persisted(page, () => expect(h.sidebar(page,'Labels')).not.toContainText('bug'));
});
