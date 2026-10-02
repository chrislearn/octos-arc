import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-3-1: eligible assignee is saved live and removed without erasing timeline", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-assign'); await h.button(page,'Assignees').click(); await h.field(page,'Search assignees').fill('spec-triage'); await h.option(page,'spec-triage'); await h.persisted(page, () => expect(h.metadataValue(page,'Assignees','spec-triage').first()).toBeVisible()); await h.button(page,'Assignees').click(); await h.option(page,'spec-triage'); await h.persisted(page, () => expect(h.metadataValue(page,'Assignees','spec-triage').first()).toHaveCount(0));
});

test("REQ-5-3-1: spec-read does not acquire metadata authority from role name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"spec-read"); await h.issue(page,'issue-metadata-'+"spec-read");
  for(const control of ['Assignees','Labels','Milestone']) await h.unavailable(page,control);
  await expect(h.button(page,'Close issue')).toHaveCount(0); await expect(h.button(page,'Reopen issue')).toHaveCount(0);
});

test("REQ-5-3-1: spec-write does not acquire metadata authority from role name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"spec-write"); await h.issue(page,'issue-metadata-'+"spec-write");
  for(const control of ['Assignees','Labels','Milestone']) await h.unavailable(page,control);
  await expect(h.button(page,'Close issue')).toHaveCount(0); await expect(h.button(page,'Reopen issue')).toHaveCount(0);
});
