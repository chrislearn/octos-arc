import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-1-2: visitor issue detail shows complete title, description and readable timeline", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.issue(page); const address=page.url(); await page.goto(address); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.text(page,'Describe the onboarding improvement.').first()).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(page.getByText(/Comment|Activity/).first()).toBeVisible(); });
});
