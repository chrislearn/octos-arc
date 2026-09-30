import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-5-2-3: Write comment stores full body and author and survives reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.issue(page,'issue-comment'); const body=h.unique('pw-comment'); await h.field(page,'Comment').fill(body); await h.button(page,'Comment').click(); const entry=page.getByRole('article').filter({hasText:body}); await h.persisted(page, async () => { await expect(entry).toContainText(body); await expect(entry).toContainText('spec-write'); });
});

test("REQ-5-2-3: blank comment adds no article or activity through either allowed UI behavior", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.issue(page,'issue-comment-invalid'); const before=await page.getByRole('article').allTextContents(); await h.field(page,'Comment').fill('   '); const submit=h.button(page,'Comment'); if(await submit.isEnabled()){ await submit.click(); await expect(page.getByText('Comment is required',{exact:false})).toBeVisible(); } else await expect(submit).toBeDisabled();
  expect(await page.getByRole('article').allTextContents()).toEqual(before); await page.reload(); expect(await page.getByRole('article').allTextContents()).toEqual(before);
});
