import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-2-3: Write comment stores full body and author and survives reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.issue(page,'issue-comment'); const body=h.unique('pw-comment'); await h.field(page,'Comment').fill(body); await h.button(page,'Comment').click(); const entry=page.getByRole('article').filter({hasText:body}); await h.persisted(page, async () => { await expect(entry).toContainText(body); await expect(entry).toContainText('spec-write'); });
});

test("REQ-5-2-3: blank comment adds no article or activity through either allowed UI behavior", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.issue(page,'issue-comment-invalid'); const before=await h.discussionSnapshot(page); await h.field(page,'Comment').fill('   '); const submit=h.button(page,'Comment'); if(await submit.isEnabled()){ await submit.click(); await expect(page.getByText('Comment is required',{exact:false})).toBeVisible(); } else await expect(submit).toBeDisabled();
  await expect.poll(()=>h.discussionSnapshot(page)).toEqual(before); await page.reload(); await expect.poll(()=>h.discussionSnapshot(page)).toEqual(before);
});

test("REQ-5-2-3: spec-read can read discussion but cannot publish a comment", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.issue(page,'issue-comment-denied-spec-read');
  await h.unavailable(page,'Comment'); await h.persisted(page,()=>expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible());
});

test("REQ-5-2-3: spec-triage can read discussion but cannot publish a comment", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-triage'); await h.issue(page,'issue-comment-denied-spec-triage');
  await h.unavailable(page,'Comment'); await h.persisted(page,()=>expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible());
});
