import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-pr-filters: Open filter excludes Draft Closed and a PR after its actual merge", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.repo(page,h.fixtureRepo('pr-filter-lifecycle'));
  await h.link(page,'Pull requests').click(); const list=page.url(); await h.link(page,'Open').click();
  await h.persisted(page,async()=>{
    await expect(h.link(page,'Improve onboarding')).toBeVisible();
    await expect(h.link(page,'Fix search')).toHaveCount(0); await expect(h.link(page,'Draft onboarding update')).toHaveCount(0);
  });
  await h.link(page,'Improve onboarding').click(); const detail=page.url();
  await h.button(page,'Merge pull request').click(); await h.button(page,'Confirm merge').click();
  await h.persisted(page,()=>expect(h.text(page,'Merged').first()).toBeVisible());
  await page.goto(list); await h.link(page,'Open').click();
  await h.persisted(page,async()=>{
    for(const title of ['Improve onboarding','Fix search','Draft onboarding update']) await expect(h.link(page,title)).toHaveCount(0);
  });
  await page.goto(detail); await h.persisted(page,()=>expect(h.text(page,'Merged').first()).toBeVisible());
});
