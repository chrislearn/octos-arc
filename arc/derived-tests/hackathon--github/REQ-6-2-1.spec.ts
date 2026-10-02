import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-2-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.link(page,'Pull requests').click(); await h.filterStatus(page,'Open'); await h.link(page,'Improve onboarding').click(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
});

test("REQ-6-2-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.link(page,'Pull requests').click(); await h.filterStatus(page,'Open'); await h.persisted(page,()=>expect(h.link(page,'Improve onboarding')).toBeVisible());
});

test("REQ-6-2-1: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.link(page,'Pull requests').click(); await h.filterStatus(page,'Open'); await h.canonicalRepo(page);await h.link(page,'Pull requests').click(); await h.filterStatus(page,'Open'); await expect(h.link(page,'Improve onboarding')).toBeVisible();
});

test("REQ-6-2-1: reference navigation: repository lists can switch Issues to Pull requests and back to Code", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page); await h.link(page,'Issues').click();
  await expect(h.link(page,'Improve onboarding')).toBeVisible(); await expect(h.link(page,'acme-docs')).toBeVisible();
  await h.link(page,'Pull requests').click(); await expect(h.link(page,'Overview onboarding PR')).toBeVisible();
  await expect(h.link(page,'acme-docs')).toBeVisible(); await h.link(page,'Issues').click();
  await expect(h.link(page,'Improve onboarding')).toBeVisible(); await h.link(page,'Code').click();
  await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-6-2-1: home workspace: a fresh visitor opens Pull requests directly", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Pull requests').click();
  await expect(h.link(page,'Overview onboarding PR')).toBeVisible(); await h.link(page,'Open').click();
  await page.reload(); await expect(h.link(page,'Overview onboarding PR')).toBeVisible();
});

test("REQ-6-2-1: home workspace: changing the repository changes the collaboration destination", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.choose(page,'Workspace repository','Acme Demo/branch-protection-demo');
  await h.link(page,'Pull requests').click(); await expect(h.link(page,'Protection status onboarding PR')).toBeVisible();
  await expect(h.link(page,'Overview onboarding PR')).toHaveCount(0);
});

test("REQ-6-2-1: visitor Open PR list filter reads same persisted PR after repeated navigation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'Pull requests').click(); const list=page.url(); await h.link(page,'Open').click(); await expect(h.link(page,'Improve onboarding')).toBeVisible(); await page.reload(); await h.link(page,'Improve onboarding').click(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await h.home(page); await page.goto(list); await h.link(page,'Open').click(); await expect(h.link(page,'Improve onboarding')).toBeVisible();
});
