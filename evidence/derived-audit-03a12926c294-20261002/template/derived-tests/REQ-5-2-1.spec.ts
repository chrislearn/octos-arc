import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

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
  await test.step('Changing limits preserves the entire original rule range',async()=>{
    await h.edit(page,'A2','61'); await expect(h.text(page,'Please enter a number between 40 and 60').first()).toBeVisible();
    await h.values(page,{A1:'60',A2:''}); await h.edit(page,'A2','60');
    await h.persisted(page,()=>h.values(page,{A1:'60',A2:'60'}));
  });
});

test("REQ-5-2-1: dropdown validation rejects grid and whole clipboard/move rectangles without clearing any source", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','Open\nClosed'); await h.validation(page,'A1','A2','Dropdown'); await page.reload(); await h.edit(page,'A1','invalid',true);
  await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{A1:'Open',A2:'Closed'});
  await h.paste(page,'A1','Closed\ninvalid'); await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{A1:'Open',A2:'Closed'});
  await h.paste(page,'C1','Closed\ninvalid'); await h.range(page,'C1','C2'); await page.keyboard.press('Control+x'); await h.cell(page,'A1').click(); await page.keyboard.press('Control+v');
  await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.persisted(page,()=>h.values(page,{A1:'Open',A2:'Closed',C1:'Closed',C2:'invalid'}));
});

test("REQ-5-2-1: context REQ-2-1-3: sheet rename preserves its slot, values, selection, rules and active state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.button(page,'Add worksheet').click(); await h.edit(page,'B2','50'); await h.validation(page,'B2','B3'); await h.cell(page,'B2').click();
  await h.sheetMenu(page,'Sheet2','Rename'); const dialog=page.getByRole('dialog',{name:'Rename worksheet',exact:true}); await h.field(dialog,'Worksheet name').fill('  Analysis  '); await h.button(dialog,'Save').click();
  await h.persisted(page,async()=>{ await h.tabOrder(page,['Sheet1','Analysis']); await expect(h.tab(page,'Analysis')).toHaveAttribute('aria-selected','true'); await expect(h.cell(page,'B2')).toHaveAttribute('aria-selected','true'); await h.values(page,{B2:'50'}); });
  await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'50'});
});

test("REQ-5-2-1: context REQ-2-2-1: structure moves numeric validation with the original cell", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,"row","2","Insert 1 row above");
  await h.edit(page,"B3",'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.persisted(page, () => h.values(page,{"B3":'50'}));
});

test("REQ-5-2-1: context REQ-2-2-1: insertion moves dropdown and numeric rules with original values and leaves inserted cells unconstrained", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.validation(page,'B2','B2'); await h.validation(page,'C2','C2','Dropdown');
  await h.structure(page,"row","2","Insert 1 row above"); await page.reload();
  await h.edit(page,"B3",'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.values(page,{"B3":'10',"C3":'Open'});
  await h.button(page,'Open dropdown for '+"C3").click(); await page.getByRole('option',{name:'Closed',exact:true}).click(); await h.edit(page,"C3",'invalid');
  await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{"C3":'Closed'});
  await h.edit(page,"B2",'101'); await h.edit(page,"C2",'unconstrained'); await h.persisted(page,()=>h.values(page,{"B3":'10',"C3":'Closed',"B2":'101',"C2":'unconstrained'}));
});

test("REQ-5-2-1: context REQ-2-2-1: deleted row validation is removed rather than applied to the next surviving cell", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.edit(page,"B3",'70');
  await h.structure(page,"row","2","Delete row"); await h.values(page,{"B2":'70'}); await h.edit(page,"B2",'101');
  await h.persisted(page,()=>h.values(page,{"B2":'101'}));
});

test("REQ-5-2-1: context REQ-2-2-2: structure moves numeric validation with the original cell", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,"column","B","Insert 1 column left");
  await h.edit(page,"C2",'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.persisted(page, () => h.values(page,{"C2":'50'}));
});

test("REQ-5-2-1: context REQ-2-2-2: insertion moves dropdown and numeric rules with original values and leaves inserted cells unconstrained", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.validation(page,'B2','B2'); await h.validation(page,'C2','C2','Dropdown');
  await h.structure(page,"column","B","Insert 1 column left"); await page.reload();
  await h.edit(page,"C2",'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.values(page,{"C2":'10',"D2":'Open'});
  await h.button(page,'Open dropdown for '+"D2").click(); await page.getByRole('option',{name:'Closed',exact:true}).click(); await h.edit(page,"D2",'invalid');
  await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{"D2":'Closed'});
  await h.edit(page,"B2",'101'); await h.edit(page,"B3",'unconstrained'); await h.persisted(page,()=>h.values(page,{"C2":'10',"D2":'Closed',"B2":'101',"B3":'unconstrained'}));
});

test("REQ-5-2-1: context REQ-2-2-2: deleted column validation is removed rather than applied to the next surviving cell", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.edit(page,"C2",'70');
  await h.structure(page,"column","B","Delete column"); await h.values(page,{"B2":'70'}); await h.edit(page,"B2",'101');
  await h.persisted(page,()=>h.values(page,{"B2":'101'}));
});

test("REQ-5-2-1: context REQ-3-1-1: failed formula-bar commit retains original input and every dependent result", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.edit(page,'D2','=B2*2'); await h.edit(page,'E2','=D2+1'); await h.validation(page,'B2','B3'); await h.cell(page,'B2').click();
  await h.field(page,'Formula bar').fill('101'); await h.field(page,'Formula bar').press('Enter'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
  await expect(h.field(page,'Formula bar')).toHaveValue('50'); await h.persisted(page,async()=>{ await h.values(page,{B2:'50',D2:'100',E2:'101'}); await h.formula(page,'D2','=B2*2','100'); await h.formula(page,'E2','=D2+1','101'); });
});

test("REQ-5-2-1: context REQ-3-1-2: invalid clipboard rectangle is rejected atomically through Ctrl+V", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','10\t20\n30\t40'); await h.validation(page,'A1','B2'); await h.edit(page,'D1','=A1+B1');
  await h.paste(page,'A1','50\t60\n70\t101',false); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
  await h.persisted(page,async()=>{ await h.values(page,{A1:'10',B1:'20',A2:'30',B2:'40'}); await h.formula(page,'D1','=A1+B1','30'); });
});

test("REQ-5-2-1: context REQ-3-1-2: invalid clipboard rectangle is rejected atomically through Paste menu", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','10\t20\n30\t40'); await h.validation(page,'A1','B2'); await h.edit(page,'D1','=A1+B1');
  await h.paste(page,'A1','50\t60\n70\t101',true); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
  await h.persisted(page,async()=>{ await h.values(page,{A1:'10',B1:'20',A2:'30',B2:'40'}); await h.formula(page,'D1','=A1+B1','30'); });
});

test("REQ-5-2-1: context REQ-3-2-1: rejected range cut preserves source and all validated target cells atomically", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','50\n101'); await h.edit(page,'C1','10'); await h.edit(page,'C2','20'); await h.validation(page,'C1','C2'); await h.range(page,'A1','A2'); await page.keyboard.press('Control+x'); await h.cell(page,'C1').click(); await page.keyboard.press('Control+v'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.persisted(page, () => h.values(page,{A1:'50',A2:'101',C1:'10',C2:'20'}));
});

test("REQ-5-2-1: context REQ-3-2-1: rejected copy preserves every source/target formula and outside dependent calculation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','50\n101'); await h.paste(page,'C1','10\n20'); await h.validation(page,'C1','C2'); await h.edit(page,'E1','=C1+C2'); await h.range(page,'A1','A2');
  await page.keyboard.press('Control+c'); await h.cell(page,'C1').click(); await page.keyboard.press('Control+v'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
  await h.persisted(page,async()=>{await h.values(page,{A1:'50',A2:'101',C1:'10',C2:'20'});await h.formula(page,'E1','=C1+C2','30');});
});

test("REQ-5-2-1: context REQ-3-2-2: undo/redo row structure restores numeric rule ranges and last visible values", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,"row","2","Insert 1 row above");
  await h.values(page,{B2:'',"B3":'50'}); await h.button(page,'Undo').click(); await h.values(page,{B2:'50',"B3":''});
  await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'50'});
  await h.button(page,'Redo').click(); await h.persisted(page,()=>h.values(page,{B2:'',"B3":'50'})); await h.edit(page,"B3",'101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{"B3":'50'});
});

test("REQ-5-2-1: context REQ-3-2-2: undo/redo column structure restores numeric rule ranges and last visible values", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,"column","B","Insert 1 column left");
  await h.values(page,{B2:'',"C2":'50'}); await h.button(page,'Undo').click(); await h.values(page,{B2:'50',"C2":''});
  await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'50'});
  await h.button(page,'Redo').click(); await h.persisted(page,()=>h.values(page,{B2:'',"C2":'50'})); await h.edit(page,"C2",'101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{"C2":'50'});
});

test("REQ-5-2-1: context REQ-5-1-2: value filtering is scoped to the selected region and clearing preserves formula and validation behavior", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'B2','Region\tSales\tStatus\nEast\t10\tOpen\nNorth\t20\tClosed\nEast\t30\tClosed'); await h.edit(page,'A1','outside-origin'); await h.edit(page,'B6','outside-next-row'); await h.edit(page,'E4','outside-next-column'); await h.edit(page,'F3','=C3*2'); await h.validation(page,'C3','C5');
  await h.range(page,'B2','D5'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.persisted(page,()=>h.visibleRows(page,['B3','B5','B6'],['B4']));
  expect(h.parseCSV(await h.csv(page))).toEqual([['outside-origin','','','','',''],['','Region','Sales','Status','',''],['','East','10','Open','','20'],['','North','20','Closed','outside-next-column',''],['','East','30','Closed','',''],['','outside-next-row','','','','']]);
  await h.data(page,'Clear filter'); await h.persisted(page,async()=>{await h.values(page,{A1:'outside-origin',B3:'East',C3:'10',B4:'North',C4:'20',B5:'East',C5:'30',B6:'outside-next-row',E4:'outside-next-column'});await h.formula(page,'F3','=C3*2','20');});
  await h.edit(page,'C3','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{C3:'10',F3:'20'});
});
