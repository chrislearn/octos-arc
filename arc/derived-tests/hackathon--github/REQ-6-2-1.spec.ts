import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-2-1: visitor Open PR list filter reads same persisted PR after repeated navigation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'Pull requests').click(); const list=page.url(); await h.link(page,'Open').click(); await expect(h.link(page,'Improve onboarding')).toBeVisible(); await page.reload(); await h.link(page,'Improve onboarding').click(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await h.home(page); await page.goto(list); await h.link(page,'Open').click(); await expect(h.link(page,'Improve onboarding')).toBeVisible();
});
