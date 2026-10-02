import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-6: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-author"); await h.scenarioPr(page,"Closable onboarding PR","acme-docs"); await h.button(page,'Close pull request').click(); await expect(h.text(page,'Closed').first()).toBeVisible(); await h.button(page,'Reopen pull request').click(); await h.persisted(page,()=>expect(h.button(page,'Close pull request')).toBeVisible());
});

test("REQ-6-6: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-viewer"); await h.scenarioPr(page,"Protected onboarding PR","acme-docs"); await expect(h.button(page,'Close pull request')).toHaveCount(0); await expect(h.button(page,'Reopen pull request')).toHaveCount(0);
});

test("REQ-6-6: home workspace: named PR entries across repositories open their saved details", async ({ page, browser }) => {
  test.setTimeout(60_000);
  for (const title of ['Draft onboarding update','Overview onboarding PR','Public onboarding PR','Reviewable onboarding PR',
    'Change request onboarding PR','Reviewer request onboarding PR','Closable onboarding PR','Protected onboarding PR',
    'Protection status onboarding PR','Mergeable onboarding PR','Blocked onboarding PR']) {
    await h.home(page); await expect(h.link(page,title)).toHaveCount(1); await h.link(page,title).click();
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
  }
});

test("REQ-6-6: author closes and reopens PR while discussion and branches persist", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.pr(page,'pr-close'); await h.button(page,'Close pull request').click(); await expect(h.button(page,'Reopen pull request')).toBeVisible(); await h.button(page,'Reopen pull request').click(); await h.persisted(page, async () => { await expect(h.button(page,'Close pull request')).toBeVisible(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.link(page,'Files changed')).toBeVisible(); });
});

test("REQ-6-6: Read viewer has no close or reopen action", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'issue-viewer'); await h.pr(page,'pr-close-read'); await expect(h.button(page,'Close pull request')).toHaveCount(0); await expect(h.button(page,'Reopen pull request')).toHaveCount(0);
});
