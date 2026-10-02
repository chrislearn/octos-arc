import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-pr-planning: PR milestone toggles without cross-repository choices or deleting history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.repo(page,'foreign-milestone-repo'); await h.pr(page,'pr-milestone');
  await h.button(page,'Milestone').click(); await expect(page.getByRole('option',{name:'foreign-milestone',exact:true})).toHaveCount(0);
  await h.option(page,'v1.0'); await h.persisted(page,()=>expect(h.metadataValue(page,'Milestone','v1.0').first()).toBeVisible());
  await h.button(page,'Milestone').click(); await h.option(page,'None');
  await h.persisted(page,()=>expect(h.metadataValue(page,'Milestone','v1.0')).toHaveCount(0));
  await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
  await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible();
  const discussion=page.getByRole('article').filter({hasText:'Please review this update.'});
  await expect(discussion).toHaveCount(1); await expect(discussion).toContainText('Please review this update.');
  await expect(discussion).toContainText('spec-write');
});

test("INTEGRATION-pr-planning: spec-read cannot change a PR milestone", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.pr(page,'pr-milestone-denied-spec-read');
  await h.unavailable(page,'Milestone'); await h.persisted(page,()=>expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible());
});

test("INTEGRATION-pr-planning: spec-write cannot change a PR milestone", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.pr(page,'pr-milestone-denied-spec-write');
  await h.unavailable(page,'Milestone'); await h.persisted(page,()=>expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible());
});
