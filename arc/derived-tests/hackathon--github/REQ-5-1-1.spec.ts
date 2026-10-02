import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-1-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.link(page,'Issues').click(); await h.filterStatus(page,"Open"); await page.getByRole('searchbox',{name:'Search issues',exact:true}).fill("Improve onboarding"); await expect(h.link(page,"Improve onboarding")).toBeVisible();
});

test("REQ-5-1-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.link(page,'Issues').click(); await h.filterStatus(page,"Closed"); await page.getByRole('searchbox',{name:'Search issues',exact:true}).fill("Legacy welcome text"); await expect(h.link(page,"Legacy welcome text")).toBeVisible();
});

test("REQ-5-1-1: Open/Closed live issue filters combine with keyword and survive refresh", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'Issues').click(); await h.link(page,'Open').click(); await page.getByRole('searchbox',{name:'Search issues',exact:true}).fill('Improve onboarding'); await h.persisted(page, () => expect(h.link(page,'Improve onboarding')).toBeVisible());
    await h.link(page,'Closed').click(); await page.getByRole('searchbox',{name:'Search issues',exact:true}).fill('Legacy welcome text'); await expect(h.link(page,'Legacy welcome text')).toBeVisible(); await expect(h.link(page,'Improve onboarding')).toHaveCount(0);
});
