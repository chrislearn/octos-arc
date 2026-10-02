import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-1-1: grid and formula-bar edits commit on Enter or blur and Escape cancels", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'A1', 'text', true); await h.edit(page, 'B1', 'TRUE'); await h.edit(page, 'C1', '2026-09-30'); await h.edit(page, 'E1', '12.5');
  await h.cell(page, 'A1').dblclick(); await h.field(page, 'Edit A1').fill('cancelled'); await h.field(page, 'Edit A1').press('Escape'); await h.values(page, { A1: 'text' });
  await h.cell(page, 'A1').click(); await h.field(page, 'Formula bar').fill('committed-on-blur'); await h.cell(page, 'D1').click();
  await h.persisted(page, () => h.values(page, { A1: 'committed-on-blur', B1: 'TRUE', C1: '2026-09-30', E1: '12.5' }));
});

test("REQ-3-1-1: formula bar Escape cancels and grid blur commits without changing unrelated cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','original'); await h.cell(page,'A1').click(); await h.field(page,'Formula bar').fill('cancelled'); await h.field(page,'Formula bar').press('Escape');
  await h.ordinary(page,{A1:'original'}); await h.cell(page,'B2').dblclick(); await h.field(page,'Edit B2').fill('grid-blur'); await h.cell(page,'D4').click();
  await h.persisted(page,()=>h.ordinary(page,{A1:'original',B2:'grid-blur',D4:''}));
});

test("REQ-3-1-1: failed cell save restores formula-bar input and keeps persisted cell; retry succeeds", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page);
  const endpoints=new Set<string>();
  const endpoint=(request:any)=>{const url=new URL(request.url()); return `${request.method()} ${url.origin}${url.pathname}`;};
  const discover=(response:any)=>{ if(['PATCH','PUT','POST'].includes(response.request().method()) && response.ok()) endpoints.add(endpoint(response.request())); };
  page.on('response',discover);
  try {
    // Learn transport from an actual successful cell write. No assumed route,
    // JSON schema, origin, body encoding, or payload substring is necessary.
    await h.edit(page,'A1','original'); await h.values(page,{A1:'original'});
    await expect.poll(()=>endpoints.size,{message:'HARNESS_UNSUPPORTED: cell rollback requires an observable successful HTTP write endpoint; provide an adapter for WebSocket/local storage'}).toBeGreaterThan(0);
  } finally { page.off('response',discover); }
  await h.persisted(page,()=>h.values(page,{A1:'original'}));
  const feedback=h.saveFailureReason(page); await expect(feedback).toHaveCount(0);
  let rejectedAttempts=0, retryAttempts=0, rejecting=true; const rejected=h.unique(), retried=h.unique();
  const intercept=async(route:any)=>{
    if(endpoints.has(endpoint(route.request()))) {
      if(rejecting) { rejectedAttempts++; await route.fulfill({status:500,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({error:'Unable to save cell'})}); return; }
      retryAttempts++;
    }
    await route.continue();
  };
  await page.route('**/*',intercept);
  try {
    await h.edit(page,'A1',rejected);
    await expect.poll(()=>rejectedAttempts,{message:'HARNESS_UNSUPPORTED: failed edit did not use the learned HTTP write endpoint'}).toBeGreaterThan(0);
    await expect(feedback.first()).toBeVisible();
    await h.values(page,{A1:'original'}); await expect(h.field(page,'Formula bar')).toHaveValue('original');
    await page.reload(); await h.values(page,{A1:'original'}); rejecting=false; await h.edit(page,'A1',retried);
    await h.persisted(page,()=>h.values(page,{A1:retried})); expect(retryAttempts).toBeGreaterThan(0);
  } finally { await page.unroute('**/*',intercept); }
});

test("REQ-3-1-1: context REQ-1-2-2: renaming is scoped to current workbook and updates refreshed home record", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); const first=h.unique(); await h.renameWorkbook(page,first); const address=page.url(); await h.edit(page,'A1','keep-original-data');
  await h.blank(page); const second=h.unique(); await h.renameWorkbook(page,second); await h.edit(page,'A1','keep-second-data');
  await page.goto(address); const renamed=h.unique(); await h.renameWorkbook(page,`  ${renamed}  `); await page.goto('/'); await page.reload();
  await expect(page.getByRole('link',{name:first,exact:true})).toHaveCount(0); await expect(page.getByRole('link',{name:renamed,exact:true})).toBeVisible(); await expect(page.getByRole('link',{name:second,exact:true})).toBeVisible();
  await h.reopen(page,renamed); await h.values(page,{A1:'keep-original-data'}); await h.reopen(page,second); await h.values(page,{A1:'keep-second-data'});
});

test("REQ-3-1-1: context REQ-1-3-1: import treats first row as data and strips only the final csv extension from the file name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); const name=`${h.unique()}.part`; await h.button(page,'Import CSV').click(); const dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
  await h.field(dialog,'CSV file').setInputFiles({name:`${name}.csv`,mimeType:'text/csv',buffer:Buffer.from('Region,Sales,Status\nEast,1200,Open\nNorth,800,Closed')}); await h.button(dialog,'Confirm import').click();
  await expect(h.tab(page,'Sheet1')).toHaveAttribute('aria-selected','true'); await expect(page.getByRole('tab')).toHaveCount(1); const address=page.url();
  await h.ordinary(page,{A1:'Region',B1:'Sales',C1:'Status',A2:'East',B2:'1200',C2:'Open',A3:'North',B3:'800',C3:'Closed'}); await h.edit(page,'A1','ordinary-first-row');
  await page.goto('/'); await page.reload(); await expect(page.getByRole('link',{name,exact:true})).toBeVisible(); await page.goto(address); await h.values(page,{A1:'ordinary-first-row',A2:'East',A3:'North'});
});

test("REQ-3-1-1: context REQ-1-1-1: home/editor timestamp agrees with persisted renamed workbook and never loads another workbook", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); const name=h.unique(); await h.renameWorkbook(page,name); const address=page.url(); await h.edit(page,'A1','first-workbook-only');
  await page.goto('/'); const updated=await h.recordUpdated(page,name); await page.getByRole('link',{name,exact:true}).click(); await expect(h.text(page,updated).first()).toBeVisible();
  await h.persisted(page,()=>h.values(page,{A1:'first-workbook-only'})); await h.blank(page); const otherName=h.unique(); await h.renameWorkbook(page,otherName); await h.edit(page,'A1','second-workbook-only');
  await page.goto(address); await h.values(page,{A1:'first-workbook-only'}); await expect(h.text(page,name).first()).toBeVisible();
  await h.reopen(page,otherName); await h.values(page,{A1:'second-workbook-only'}); await h.reopen(page,name); await h.values(page,{A1:'first-workbook-only'});
});

test("REQ-3-1-1: context REQ-1-1-1: edited workbook state is shared by saved address across independent browser sessions", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); const address=page.url(); await h.edit(page,'F8','unique-workbook-state'); await h.persisted(page,()=>h.values(page,{F8:'unique-workbook-state'}));
  const later=await browser.newContext();
  try { const p=await later.newPage(); await p.goto(address); await h.values(p,{F8:'unique-workbook-state'}); await h.edit(p,'F8','later-session-edit'); await h.values(p,{F8:'later-session-edit'}); await page.reload(); await h.values(page,{F8:'later-session-edit'}); }
  finally { await later.close(); }
});
