import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-2-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"issue-commenter"); await h.scenarioIssue(page,"Commentable onboarding issue"); const body=h.unique('pw-comment'); await h.field(page,'Comment').fill(body); await h.button(page,'Comment').click(); await h.persisted(page,()=>expect(h.text(page,body).first()).toBeVisible());
});

test("REQ-5-2-3: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"issue-commenter"); await h.scenarioIssue(page,"Comment validation issue"); const before=await page.getByRole('article').allTextContents(); await h.field(page,'Comment').fill('   '); if(await h.button(page,'Comment').isEnabled()) await h.attemptSubmission(page,h.button(page,'Comment')); await page.reload(); await expect.poll(()=>page.getByRole('article').allTextContents()).toEqual(before);
});

test("REQ-5-2-3: Write comment stores full body and author and survives reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.issue(page,'issue-comment'); const body=h.unique('pw-comment'); await h.field(page,'Comment').fill(body); await h.button(page,'Comment').click(); const entry=page.getByRole('article').filter({hasText:body}); await h.persisted(page, async () => { await expect(entry).toContainText(body); await expect(entry).toContainText('file-contributor'); });
});

test("REQ-5-2-3: blank comment adds no article or activity through either allowed UI behavior", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.issue(page,'issue-comment-invalid'); const before=await h.discussionSnapshot(page); await h.field(page,'Comment').fill('   '); const submit=h.button(page,'Comment'); if(await submit.isEnabled()){ await submit.click(); await expect(page.getByText('Comment is required',{exact:false})).toBeVisible(); } else await expect(submit).toBeDisabled();
    await expect.poll(()=>h.discussionSnapshot(page)).toEqual(before); await page.reload(); await expect.poll(()=>h.discussionSnapshot(page)).toEqual(before);
});

test("REQ-5-2-3: issue-viewer can read discussion but cannot publish a comment", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'issue-viewer'); await h.issue(page,'issue-comment-denied-issue-viewer');
    await h.unavailable(page,'Comment'); await h.persisted(page,()=>expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible());
});

test("REQ-5-2-3: triage-collaborator can read discussion but cannot publish a comment", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'triage-collaborator'); await h.issue(page,'issue-comment-denied-triage-collaborator');
    await h.unavailable(page,'Comment'); await h.persisted(page,()=>expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible());
});
