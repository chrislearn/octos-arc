import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-pr-filters: Open Draft Closed and actual Merged status filters isolate records and retain other PRs", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); const address=await h.repo(page,h.fixtureRepo('pr-filter-lifecycle'));
  await h.link(page,'Pull requests').click(); const list=page.url();
  for(const [status,title] of [['Open','Improve onboarding'],['Draft','Draft onboarding update'],['Closed','Fix search']]) {
    await h.filterStatus(page,status); await h.persisted(page,async()=>{
      await expect(h.link(page,title)).toBeVisible();
      for(const other of ['Improve onboarding','Draft onboarding update','Fix search'].filter(name=>name!==title)) await expect(h.link(page,other)).toHaveCount(0);
    });
  }
  await h.filterStatus(page,'Open'); await h.link(page,'Improve onboarding').click();
  await h.button(page,'Merge pull request').click(); await h.button(page,'Confirm merge').click(); await expect(h.text(page,'Merged').first()).toBeVisible();
  await page.goto(list); await h.filterStatus(page,'Merged');
  await h.persisted(page,async()=>{ await expect(h.link(page,'Improve onboarding')).toBeVisible(); await expect(h.link(page,'Fix search')).toHaveCount(0); await expect(h.link(page,'Draft onboarding update')).toHaveCount(0); });
  await h.filterStatus(page,'Draft'); await expect(h.link(page,'Draft onboarding update')).toBeVisible();
  await h.filterStatus(page,'Closed'); await expect(h.link(page,'Fix search')).toBeVisible();
});
