import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-5: Maintain merge commits actual changes to base branch and persists terminal status", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-success'); await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click(); await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible()); await expect(h.button(page,'Close pull request')).toHaveCount(0); await expect(h.button(page,'Reopen pull request')).toHaveCount(0);
  await h.repo(page,h.fixtureRepo('merge-success')); await h.button(page,'Branch main').click(); await h.option(page,'main'); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await expect(h.text(page,'export const search = "merged search flow";')).toBeVisible();
});

test("REQ-6-5: missing required approval blocks merge before click and retains PR and branch", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-blocked'); await expect(h.button(page,'Merge pull request')).toBeDisabled(); await expect(h.text(page,'Review required by branch protection').first()).toBeVisible(); await h.persisted(page, () => expect(h.button(page,'Merge pull request')).toBeDisabled()); await expect(h.text(page,'Open').first()).toBeVisible(); await h.repo(page,h.fixtureRepo('merge-blocked')); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await expect(h.text(page,'export const search = "search flow";')).toBeVisible();
});

test("REQ-6-5: check-only enforces only its configured merge prerequisites", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,"merge-check-only");
  await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click();
  await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible());
});

test("REQ-6-5: approval-only enforces only its configured merge prerequisites", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,"merge-approval-only");
  await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click();
  await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible());
});

test("REQ-6-5: unprotected enforces only its configured merge prerequisites", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,"merge-unprotected");
  await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click();
  await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible());
});

test("REQ-6-5: current Request changes blocks an otherwise unprotected PR", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-request-changes'); await h.persisted(page, () => expect(h.button(page,'Merge pull request')).toBeDisabled()); await expect(h.text(page,'Open').first()).toBeVisible();
});

test("REQ-6-5: old-commit approval cannot satisfy a protected current-commit PR", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-stale-approval'); await expect(h.button(page,'Merge pull request')).toBeDisabled(); await expect(h.text(page,'Review required by branch protection').first()).toBeVisible(); await page.reload(); await expect(h.button(page,'Merge pull request')).toBeDisabled();
});
