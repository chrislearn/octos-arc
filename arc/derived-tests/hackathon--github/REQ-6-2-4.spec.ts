import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-2-4: Draft creation is persistent and has present disabled merge action", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.compare(page,'pr-draft-create'); await h.button(page,'Create draft pull request').click(); const title=h.unique('pw-draft'); await h.field(page,'Title').fill(title); await h.button(page,'Create draft pull request').click(); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Draft').first()).toBeVisible(); await expect(h.button(page,'Merge pull request')).toBeDisabled(); });
});

test("REQ-6-2-4: author marks Draft ready without changing title or branches", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.pr(page,'pr-ready','Draft onboarding update'); await h.button(page,'Ready for review').click(); const confirm=h.button(page,'Confirm'); if(await confirm.isVisible()) await confirm.click(); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Draft onboarding update',exact:true})).toBeVisible(); await expect(h.text(page,'Draft')).toHaveCount(0); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'draft-feature').first()).toBeVisible(); await expect(h.text(page,'main').first()).toBeVisible(); await expect(h.text(page,'Ready for review').first()).toBeVisible(); });
});
