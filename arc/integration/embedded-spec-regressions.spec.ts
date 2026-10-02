// Stage this file beside a copy of the frozen GitHub helpers.ts and run with
// Playwright. These synthetic layouts are independent of the generated app.
import { test, expect } from '@playwright/test';
import * as h from './helpers';

test('visible branch summaries survive hidden native options in either DOM order', async ({ page }) => {
  const select='<label>Default branch<select aria-label="Default branch"><option selected>main</option><option>feature-search</option></select></label>';
  const rule='<p><span>main</span><span>1 approval</span><span>Require status check test</span></p>';
  for (const html of [select+rule, rule+select]) {
    await page.setContent(html);
    await expect(h.text(page,'main')).toHaveCount(2);
    await expect(h.visibleText(page,'main')).toHaveCount(1);
    await expect(h.visibleText(page,'main')).toBeVisible();
  }
});

test('picker controls coexist with global search and multiple saved grant roles', async ({ page }) => {
  await page.setContent('<header><input type="search" aria-label="Search"></header><table><tr><td><select aria-label="Role"><option>Read</option></select></td></tr><tr><td><select aria-label="Role"><option>Maintain</option></select></td></tr></table><section aria-label="Access picker"><div><label>Search<input aria-label="Search"></label></div><label>Role<select aria-label="Role"><option>Read</option><option>Write</option></select></label><button>Add</button></section>');
  const picker=await h.accessPicker(page);
  await picker.getByRole('textbox',{name:'Search',exact:true}).fill('frontend-team');
  await h.choose(picker,'Role','Write');
  await expect(page.getByRole('searchbox',{name:'Search',exact:true})).toHaveValue('');
  await expect(page.getByRole('combobox',{name:'Role',exact:true}).nth(0).locator('option:checked')).toHaveText('Read');
  await expect(page.getByRole('combobox',{name:'Role',exact:true}).nth(1).locator('option:checked')).toHaveText('Maintain');
  await expect(picker.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Write');
});

test('history snapshot waits for an asynchronously rendered immutable history', async ({ page }) => {
  await page.setContent('<a href="/">GitHub</a><main>Loading history</main>');
  await page.evaluate(()=>setTimeout(()=>{
    document.querySelector('main')!.innerHTML='<a href="/revision/1">Document search flow</a><a href="/revision/0">Initialize empty repository</a>';
  },200));
  await expect.poll(()=>h.historyLinks(page)).toEqual(['GitHub','Document search flow','Initialize empty repository']);
});

test('password validation accepts either or both allowed visible messages', async ({ page }) => {
  for (const messages of [
    ['Current password is incorrect'],
    ['Password confirmation does not match'],
    ['Current password is incorrect', 'Password confirmation does not match'],
  ]) {
    await page.setContent(messages.map(message=>`<div role="alert">${message}</div>`).join(''));
    await expect(h.passwordValidationReason(page).first()).toBeVisible();
  }
  await page.setContent('<p>Current password is incorrect<br>Password confirmation does not match</p>');
  await expect(h.passwordValidationReason(page).first()).toBeVisible();
});

test('password validation rejects missing, unrelated and hidden feedback', async ({ page }) => {
  for (const html of ['<main></main>', '<div role="alert">Password updated</div>',
    '<div hidden>Current password is incorrect</div><div style="display:none">Password confirmation does not match</div>']) {
    await page.setContent(html);
    await expect(h.passwordValidationReason(page)).toHaveCount(0);
  }
});
