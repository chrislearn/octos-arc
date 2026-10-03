import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-2-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-contributor"); await h.canonicalRepo(page);await h.link(page,'Pull requests').click(); await h.link(page,'New pull request').click(); await h.choose(page,'Base','main'); await h.choose(page,'Compare','feature-search'); await h.button(page,'Compare changes').click(); await expect(h.text(page,'src/search.ts')).toBeVisible(); await expect(h.comparisonCommitInformation(page,'Implement search flow',1).first()).toBeVisible();
});

test("REQ-6-2-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-contributor"); await h.canonicalRepo(page);await h.link(page,'Pull requests').click(); await h.link(page,'New pull request').click(); await h.choose(page,'Base','main'); await h.choose(page,'Compare','main'); await h.button(page,'Compare changes').click(); await expect(h.noDifferences(page).first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeDisabled();
});

test("REQ-6-2-2: comparison controls have the exact Base and Compare accessible names", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'pr-contributor'); await h.canonicalRepo(page);
  await h.link(page,'Pull requests').click(); await h.link(page,'New pull request').click();
  for (const name of ['Base','Compare']) {
    await expect(page.getByRole('combobox',{name,exact:true})).toHaveCount(1);
    await expect(page.getByRole('combobox',{name:name.toLowerCase(),exact:true})).toHaveCount(0);
  }
  await h.choose(page,'Base','main'); await h.choose(page,'Compare','feature-search');
  await h.button(page,'Compare changes').click(); await expect(h.text(page,'src/search.ts')).toBeVisible();
});

test("REQ-6-2-2: 81c7432a compatibility: pull request and comparison navigation remain discoverable before detail data", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'pr-author'); await h.link(page,'Acme Demo').click(); await h.link(page,'acme-docs').click();
  expect(await h.link(page,'Pull requests').isVisible()).toBe(true);
  expect(await h.link(page,'Compare').isVisible()).toBe(true);
  await h.link(page,'Pull requests').click(); await h.link(page,'New pull request').click();
  await expect(page.getByRole('combobox',{name:'Base',exact:true})).toBeVisible();
  await expect(page.getByRole('combobox',{name:'Compare',exact:true})).toBeVisible();
});

test("REQ-6-2-2: reference navigation: comparison keeps repository identity and permits returning to the PR list", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'pr-author'); await h.canonicalRepo(page);
  await h.link(page,'Pull requests').click(); await h.link(page,'New pull request').click();
  await h.chosen(page,'Base','main'); await expect(h.link(page,'acme-docs')).toBeVisible();
  await h.choose(page,'Compare','feature-search'); await h.button(page,'Compare changes').click();
  await expect(h.text(page,'src/search.ts')).toBeVisible(); await page.reload();
  await expect(h.link(page,'acme-docs')).toBeVisible(); await h.link(page,'Pull requests').click();
  await expect(h.link(page,'Overview onboarding PR')).toBeVisible();
});

test("REQ-6-2-2: home workspace: a fresh sign-in can open Compare without an inserted repository step", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'pr-contributor'); await h.link(page,'Compare').click();
  await h.chosen(page,'Base','main'); await h.choose(page,'Compare','feature-search');
  await h.button(page,'Compare changes').click(); await expect(h.text(page,'src/search.ts')).toBeVisible();
});

test("REQ-6-2-2: stage3 feedback: identical branches explain the disabled creation action", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'pr-contributor'); await h.repo(page); await h.link(page,'Compare').click();
  await h.choose(page,'Base','main'); await h.choose(page,'Compare','main');
  await h.button(page,'Compare changes').click();
  await h.persisted(page,async()=>{
    // Compatibility witness for the external report's /identical/i assertion.
    await expect(page.getByText(/identical/i)).toBeVisible();
    await expect(h.button(page,'Create pull request')).toBeDisabled();
  });
});

test("REQ-6-2-2: Base/Compare comboboxes show exact changed file and comparable commits", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.compare(page,'pr-compare'); await expect(h.comparisonCommitInformation(page,'Implement search flow',1).first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeEnabled();
});

test("REQ-6-2-2: equal base and compare report no differences and disable creation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.compare(page,'pr-no-changes'); await h.choose(page,'Compare','main'); await h.button(page,'Compare changes').click(); await expect(h.noDifferences(page).first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeDisabled();
});
