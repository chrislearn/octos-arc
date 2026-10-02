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

test('write learning rejects ambiguity and does not confuse create with delete',async({page})=>{
  const requests: string[]=[];
  await page.route('https://sheet.test/**',async route=>{
    const req=route.request();
    if(req.method()==='GET') await route.fulfill({contentType:'text/html',body:`
      <button onclick="fetch('/rules?id=1',{method:'PUT'})">Save</button>
      <button onclick="fetch('/rules?id=1',{method:'DELETE'})">Delete</button>
      <button onclick="Promise.all([fetch('/selection',{method:'PATCH'}),fetch('/rules?id=1',{method:'PUT'})])">Ambiguous</button>
      <button>No write</button>`});
    else {requests.push(req.method());await route.fulfill({status:200,body:'{}'});}
  });
  await page.goto('https://sheet.test/');
  await expect(h.learnWrite(page,()=>page.getByRole('button',{name:'Ambiguous',exact:true}).click())).rejects.toThrow(/HARNESS_UNSUPPORTED:.*observed 2/);
  await expect(h.learnWrite(page,()=>page.getByRole('button',{name:'No write',exact:true}).click())).rejects.toThrow(/HARNESS_UNSUPPORTED:.*observed 0/);
  const create=await h.learnWrite(page,()=>page.getByRole('button',{name:'Save',exact:true}).click());
  const remove=await h.learnWrite(page,()=>page.getByRole('button',{name:'Delete',exact:true}).click());
  expect(create.method).toBe('PUT');expect(remove.method).toBe('DELETE');
  expect(remove.endpoint).toBe('https://sheet.test/rules?id=1');
  const fault=await h.rejectWrites(page,remove);
  try {
    await Promise.all([page.waitForResponse(r=>r.request().method()==='PUT' && r.ok()),
      page.getByRole('button',{name:'Save',exact:true}).click()]);
    expect(fault.attempts()).toBe(0);expect(requests.at(-1)).toBe('PUT');
    await page.getByRole('button',{name:'Delete',exact:true}).click();await fault.assertInjected();
    expect(fault.attempts()).toBe(1);expect(requests.at(-1)).toBe('PUT');
  } finally {await fault.remove();}
});

test('write matching keeps semantic query parameters and escaped paths',async()=>{
  const write={method:'PUT',endpoint:'https://api.test/workbooks/a%2Fb?command=save'};
  expect(h.matchesWrite({method:()=> 'PUT',url:()=>write.endpoint},write)).toBe(true);
  expect(h.matchesWrite({method:()=> 'PUT',url:()=>write.endpoint.replace('save','delete')},write)).toBe(false);
  expect(h.matchesWrite({method:()=> 'DELETE',url:()=>write.endpoint},write)).toBe(false);
});
