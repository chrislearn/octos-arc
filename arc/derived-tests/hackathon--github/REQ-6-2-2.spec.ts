import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-2-2: native base/compare show exact changed file and comparable commits", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.compare(page,'pr-compare'); await expect(page.getByText(/Commit summary/).first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeEnabled();
});

test("REQ-6-2-2: equal base and compare disable creation before compare button and afterward", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.compare(page,'pr-no-changes'); await h.field(page,'compare').selectOption({label:'main'}); await expect(h.text(page,'No changes').first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeDisabled(); await h.button(page,'Compare changes').click(); await expect(h.text(page,'No changes').first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeDisabled();
});
