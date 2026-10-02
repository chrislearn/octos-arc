import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-3-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-reviewer"); await h.scenarioPr(page,"Reviewable onboarding PR","acme-docs"); await h.link(page,'Files changed').click(); await h.button(page,'Add comment').first().click(); const body=h.unique('pw-review'); await h.field(page,'Comment').fill(body); await h.button(page,'Add single comment').click(); await h.persisted(page,()=>expect(h.text(page,body).first()).toBeVisible());
});

test("REQ-6-3-3: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-reviewer"); await h.scenarioPr(page,"Pending review onboarding PR","acme-docs"); await h.link(page,'Files changed').click(); await h.button(page,'Add comment').first().click(); const body=h.unique('pw-review'); await h.field(page,'Comment').fill(body); await h.button(page,'Start a review').click(); await h.persisted(page,async()=>{await expect(h.text(page,body).first()).toBeVisible(); await expect(page.getByText(/Pending review/).first()).toBeVisible();});
});

test("REQ-6-3-3: single inline comment persists at changed line", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,"review-comment"); await h.link(page,'Files changed').click(); await h.button(page,'Add comment').first().click(); const body=h.unique('pw-review'); await h.field(page,'Comment').fill(body); await h.button(page,"Add single comment").click(); await h.persisted(page, async () => { await expect(h.text(page,body).first()).toBeVisible();  });
});

test("REQ-6-3-3: pending review draft persists at changed line", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'bob-reviewer'); await h.pr(page,"review-pending"); await h.link(page,'Files changed').click(); await h.button(page,'Add comment').first().click(); const body=h.unique('pw-review'); await h.field(page,'Comment').fill(body); await h.button(page,"Start a review").click(); await h.persisted(page, async () => { await expect(h.text(page,body).first()).toBeVisible();  });
    const address=page.url(); const visitor=await browser.newContext(); const p=await visitor.newPage(); await p.goto(address); await expect(h.text(p,body)).toHaveCount(0); await visitor.close();
});
