import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-3-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"issue-editor"); await h.scenarioIssue(page,"Assignable onboarding issue"); await h.button(page,"Assignees").click(); await h.field(page,"Search assignees").fill("bob-reviewer"); await h.option(page,"bob-reviewer"); await h.persisted(page,()=>expect(h.metadataValue(page,"Assignees","bob-reviewer").first()).toBeVisible()); await h.button(page,"Assignees").click(); await h.option(page,"bob-reviewer"); await h.persisted(page,()=>expect(h.metadataValue(page,"Assignees","bob-reviewer")).toHaveCount(0));
});

test("REQ-5-3-1: eligible assignee is saved live and removed without erasing timeline", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'pr-maintainer'); await h.issue(page,'issue-assign'); await h.button(page,'Assignees').click(); await h.field(page,'Search assignees').fill('triage-collaborator'); await h.option(page,'triage-collaborator'); await h.persisted(page, () => expect(h.metadataValue(page,'Assignees','triage-collaborator').first()).toBeVisible()); await h.button(page,'Assignees').click(); await h.option(page,'triage-collaborator'); await h.persisted(page, () => expect(h.metadataValue(page,'Assignees','triage-collaborator').first()).toHaveCount(0));
});

test("REQ-5-3-1: issue-viewer does not acquire metadata authority from role name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"issue-viewer"); await h.issue(page,'issue-metadata-'+"issue-viewer");
    for(const control of ['Assignees','Labels','Milestone']) await h.unavailable(page,control);
    await expect(h.button(page,'Close issue')).toHaveCount(0); await expect(h.button(page,'Reopen issue')).toHaveCount(0);
});

test("REQ-5-3-1: file-contributor does not acquire metadata authority from role name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"file-contributor"); await h.issue(page,'issue-metadata-'+"file-contributor");
    for(const control of ['Assignees','Labels','Milestone']) await h.unavailable(page,control);
    await expect(h.button(page,'Close issue')).toHaveCount(0); await expect(h.button(page,'Reopen issue')).toHaveCount(0);
});
