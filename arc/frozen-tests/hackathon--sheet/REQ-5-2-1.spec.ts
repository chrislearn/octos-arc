import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-5-2-1: dropdown trims options and rejects invalid edits without changing saved value", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','Open'); await h.validation(page,'A1','A2','Dropdown'); await h.button(page,'Open dropdown for A1').click();
  await page.getByRole('option',{name:'Closed',exact:true}).click(); await h.values(page,{A1:'Closed'}); await page.reload(); await h.edit(page,'A1','invalid');
  await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/)).toBeVisible(); await h.persisted(page, () => h.values(page,{A1:'Closed'}));
});

test("REQ-5-2-1: inclusive numeric boundaries and rectangle rejection are atomic across reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','0'); await h.edit(page,'B3','100'); await h.validation(page,'B2','B3'); await page.reload(); await h.edit(page,'B2','100'); await h.edit(page,'B2','0'); await h.edit(page,'B3','0'); await h.edit(page,'B3','100');
  await h.edit(page,'B3','101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.values(page,{B2:'0',B3:'100'});
  await h.paste(page,'B2','50\n101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.persisted(page, () => h.values(page,{B2:'0',B3:'100'}));
});

test("REQ-5-2-1: editing and deleting a validation rule closes dialog and preserves values", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','50'); await h.validation(page,'A1','A1'); await h.cell(page,'A1').click(); await h.data(page,'Data validation');
  const dialog=page.getByRole('dialog',{name:'Data validation',exact:true}); await expect(h.field(dialog,'Minimum')).toHaveValue('0'); await expect(h.field(dialog,'Maximum')).toHaveValue('100');
  await h.field(dialog,'Maximum').fill('200'); await h.button(dialog,'Save').click(); await expect(dialog).toBeHidden(); await h.edit(page,'A1','150'); await h.values(page,{A1:'150'});
  await h.data(page,'Data validation'); await h.button(dialog,'Delete rule').click(); await expect(dialog).toBeHidden(); await h.edit(page,'A1','300'); await h.persisted(page, () => h.values(page,{A1:'300'}));
});

test("REQ-5-2-1: a reopened dropdown rule shows saved trimmed values and Delete rule removes dropdown constraint", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','Open'); await h.validation(page,'A1','A2','Dropdown'); await page.reload(); await h.cell(page,'A1').click(); await h.data(page,'Data validation');
  const dialog=page.getByRole('dialog',{name:'Data validation',exact:true}); await h.chosen(dialog,'Rule type','Dropdown'); const saved=await h.field(dialog,'Allowed values').inputValue(); expect(saved.split(',').map(item=>item.trim())).toEqual(['Open','Closed']); await expect(h.button(dialog,'Delete rule')).toBeVisible();
  await h.button(dialog,'Delete rule').click(); await expect(dialog).toBeHidden(); await h.values(page,{A1:'Open'}); await expect(h.button(page,'Open dropdown for A1')).toHaveCount(0); await h.edit(page,'A1','custom');
  await h.persisted(page,()=>h.values(page,{A1:'custom'})); await h.edit(page,'A2','another-custom'); await h.values(page,{A2:'another-custom'});
});

test("REQ-5-2-1: numeric rule uses inclusive custom bounds and specific rejection text for grid and formula-bar entry", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.numericRule(page,'A1','A2','10','20'); await page.reload(); await h.edit(page,'A1','20'); await h.edit(page,'A1','10'); await h.edit(page,'A2','10'); await h.edit(page,'A2','20');
  await h.edit(page,'A1','9',true); await expect(h.text(page,'Please enter a number between 10 and 20').first()).toBeVisible(); await h.ordinary(page,{A1:'10',A2:'20'});
  await h.edit(page,'A2','21'); await expect(h.text(page,'Please enter a number between 10 and 20').first()).toBeVisible(); await h.persisted(page,()=>h.ordinary(page,{A1:'10',A2:'20'}));
});

test("REQ-5-2-1: modifying a numeric rule immediately changes its persisted limits while preserving existing values", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','50'); await h.numericRule(page,'A1','A2','0','100'); await page.reload(); await h.cell(page,'A1').click(); await h.data(page,'Data validation');
  const dialog=page.getByRole('dialog',{name:'Data validation',exact:true}); await h.chosen(dialog,'Rule type','Number range'); await expect(h.field(dialog,'Minimum')).toHaveValue('0'); await expect(h.field(dialog,'Maximum')).toHaveValue('100'); await expect(h.button(dialog,'Delete rule')).toBeVisible();
  await h.field(dialog,'Minimum').fill('40'); await h.field(dialog,'Maximum').fill('60'); await h.button(dialog,'Save').click(); await expect(dialog).toBeHidden(); await h.values(page,{A1:'50'}); await h.edit(page,'A1','60');
  await page.reload(); await h.edit(page,'A1','61'); await expect(h.text(page,'Please enter a number between 40 and 60').first()).toBeVisible(); await h.values(page,{A1:'60'});
});

test("REQ-5-2-1: dropdown validation rejects grid and whole clipboard/move rectangles without clearing any source", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','Open\nClosed'); await h.validation(page,'A1','A2','Dropdown'); await page.reload(); await h.edit(page,'A1','invalid',true);
  await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{A1:'Open',A2:'Closed'});
  await h.paste(page,'A1','Closed\ninvalid'); await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{A1:'Open',A2:'Closed'});
  await h.paste(page,'C1','Closed\ninvalid'); await h.range(page,'C1','C2'); await page.keyboard.press('Control+x'); await h.cell(page,'A1').click(); await page.keyboard.press('Control+v');
  await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.persisted(page,()=>h.values(page,{A1:'Open',A2:'Closed',C1:'Closed',C2:'invalid'}));
});
