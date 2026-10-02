import { test, expect } from '@playwright/test';
import * as h from '../../derived-tests/hackathon--sheet/helpers';

test('save error locator permits ordinary messages and arbitrary visible alerts',async({page})=>{
  for(const html of ['<p>Unable to save cell</p>','<p>Could not store changes</p>','<p>保存失败，请重试</p>','<div role="alert">Oops</div>']){
    await page.setContent(html);await expect(h.saveFailureReason(page).first()).toBeVisible();
  }
  for(const html of ['<p>Saved</p>','<p hidden>Unable to save cell</p>','<div role="alert" hidden>Error</div>']){
    await page.setContent(html);await expect(h.saveFailureReason(page)).toHaveCount(0);
  }
});

test('selection oracle catches an extra selected coordinate outside its explicit sample',async({page})=>{
  await page.setContent('<div role="grid" aria-label="Worksheet grid" aria-multiselectable="true"><div role="gridcell" aria-label="A1" aria-selected="true"></div><div role="gridcell" aria-label="B1" aria-selected="false"></div><div role="gridcell" aria-label="Z20" aria-selected="true"></div></div>');
  await expect(h.selection(page,['A1'],['B1'])).rejects.toThrow();
  await h.cell(page,'Z20').evaluate(el=>el.setAttribute('aria-selected','false')); await h.selection(page,['A1'],['B1']);
  await h.cell(page,'Z20').evaluate(el=>el.removeAttribute('aria-selected')); await expect(h.selection(page,['A1'],['B1'])).rejects.toThrow();
});
