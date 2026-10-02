import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-1-3: drag replaces and persists the exact rectangular ARIA selection", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.range(page,'B2','C3');
  await h.persisted(page,()=>h.selection(page,['B2','C2','B3','C3'],['A1','A2','B1','D3']));
  await h.cell(page,'A1').click(); await h.persisted(page,()=>h.selection(page,['A1'],['B2','C2','B3','C3']));
});

test("REQ-3-1-3: audit regression: one pointer move commits and persists the entire drag rectangle", async ({ page }) => {
  test.setTimeout(60_000);
  await h.blank(page); const a=await h.cell(page,'A1').boundingBox(),b=await h.cell(page,'C3').boundingBox();
  expect(a).not.toBeNull();expect(b).not.toBeNull();
  await page.mouse.move(a!.x+a!.width/2,a!.y+a!.height/2);await page.mouse.down();
  await page.mouse.move(b!.x+b!.width/2,b!.y+b!.height/2);await page.mouse.up();
  await h.persisted(page,()=>h.selection(page,['A1','B1','C1','A2','B2','C2','A3','B3','C3'],['D1','A4']));
});

test("REQ-3-1-3: audit regression: late selection response cannot replace a subsequent successful cell edit", async ({ page }) => {
  test.setTimeout(60_000);
  await h.blank(page);await page.reload();
  // Learn the request fingerprint from a real selection, without interpreting its payload/schema.
  const write=await h.learnWrite(page,()=>h.cell(page,'B1').click());await h.cell(page,'A1').click();await page.reload();
  let release!:()=>void,arrived!:()=>void,finished!:()=>void;
  const gate=new Promise<void>(resolve=>release=resolve),ready=new Promise<void>(resolve=>arrived=resolve),done=new Promise<void>(resolve=>finished=resolve);
  let held=false;
  const intercept=async(route:any)=>{const req=route.request();
    if(!held&&h.matchesWrite(req,write)&&req.postData()===write.body){held=true;const response=await route.fetch();arrived();await gate;await route.fulfill({response});finished();}
    else await route.continue();};
  await page.route('**/*',intercept);
  try {await h.cell(page,'B1').click();await Promise.race([ready,new Promise((_,reject)=>setTimeout(()=>reject(new Error('HARNESS_UNSUPPORTED: selection write was not intercepted')),10000))]);
    await h.field(page,'Formula bar').fill('saved-after-selection');await h.field(page,'Formula bar').press('Enter');await h.values(page,{B1:'saved-after-selection'});
    release();await done;await h.persisted(page,()=>h.values(page,{B1:'saved-after-selection'}));
  } finally {release();await page.unroute('**/*',intercept);}
});
