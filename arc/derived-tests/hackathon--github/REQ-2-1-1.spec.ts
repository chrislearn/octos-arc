import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-1-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();await h.link(page,'Acme Demo').click(); await h.link(page,'Repositories').click(); await expect(h.link(page,'acme-docs')).toBeVisible();
});

test("REQ-2-1-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalOrganization(page);await h.link(page,'Repositories').click(); await h.field(page,'Find a repository').fill('secret-research'); await expect(h.link(page,'secret-research')).toHaveCount(0);
});

test("REQ-2-1-1: public organization retains navigation while exposing only public repository data", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalOrganization(page);
  await h.persisted(page,async()=>{
    await expect(page.getByRole('heading').filter({hasText:/Acme Demo|acme-demo/}).first()).toBeVisible();
    await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(h.link(page,'secret-research')).toHaveCount(0);
    for (const name of ['Repositories','People','Teams']) await expect(h.link(page,name)).toBeVisible();
    await expect(h.text(page,'bob-reviewer')).toHaveCount(0);
  });
  await h.link(page,'acme-docs').click(); await h.link(page,'Acme Demo').click();
  await expect(page.getByRole('heading').filter({hasText:/Acme Demo|acme-demo/}).first()).toBeVisible();
});

test("REQ-2-1-1: navigation readiness retains organization navigation while repository data loads", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Acme Demo').click();
  expect(await h.link(page,'Repositories').isVisible(),'organization navigation must not wait for repository data').toBe(true);
  for (const label of ['People','Teams']) await expect(h.link(page,label)).toBeVisible();
  await h.link(page,'Repositories').click(); await h.link(page,'acme-docs').click();
  await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-2-1-1: 44831560 regression: public directory entry exposes the public repository without a data gap", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Acme Demo').click();
  expect(await h.link(page,'acme-docs').isVisible(),'public repository must be ready after directory navigation').toBe(true);
  await h.link(page,'acme-docs').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-2-1-1: eb7208fb compatibility: cold public home exposes the organization and its public repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page);
  expect(await h.link(page,'Acme Demo').isVisible(),'public discovery must not depend on a session round trip').toBe(true);
  await h.link(page,'Acme Demo').click(); await h.link(page,'Repositories').click();
  expect(await h.link(page,'acme-docs').isVisible()).toBe(true);
  await expect(h.link(page,'secret-research')).toHaveCount(0);
  await h.link(page,'acme-docs').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-2-1-1: eb7208fb compatibility: sign-out retains public discovery without restoring private repository entries", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.link(page,'Acme Demo').click();
  await expect(h.link(page,'secret-research')).toBeVisible();
  await h.signOut(page); await expect(h.button(page,'Account menu')).toHaveCount(0);
  expect(await h.link(page,'Acme Demo').isVisible()).toBe(true);
  await h.link(page,'Acme Demo').click(); await h.link(page,'Repositories').click();
  await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(h.link(page,'secret-research')).toHaveCount(0);
  await page.reload(); await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(h.link(page,'secret-research')).toHaveCount(0);
});

test("REQ-2-1-1: organization live repository filter exposes public result and hides private result", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.organization(page); await h.link(page,'Repositories').click(); await h.field(page,'Find a repository').fill('acme-docs'); await expect(h.link(page,'acme-docs')).toBeVisible();
    await h.link(page,'acme-docs').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible(); await page.goBack(); await expect(h.link(page,'acme-docs')).toBeVisible();
    await h.field(page,'Find a repository').fill('secret-research'); await expect(h.link(page,'secret-research')).toHaveCount(0);
});
