"""Source-reviewed Sheet cases derived from atomic and inherited contracts."""
import json

def register(s):
    s('REQ-1-1-1', 'home entry, saved address and later browser session identify the same workbook', r'''
    await page.goto('/'); const entry = page.getByRole('link', { name: 'Q3 Sales', exact: true });
    await expect(entry).toBeVisible(); await entry.click(); const address = page.url();
    await h.values(page, { A1: 'Region' }); await expect(h.tab(page, 'Sheet1')).toBeVisible();
    await h.persisted(page, () => h.values(page, { A1: 'Region' }));
    const later = await browser.newContext();
    try { const other = await later.newPage(); await other.goto(address); await h.values(other, { A1: 'Region' }); }
    finally { await later.close(); }
    ''')
    s('REQ-1-2-1', 'create opens exactly one blank Sheet1 with A1 selected and persists', r'''
    const address = await h.blank(page); await expect(page.getByRole('tab')).toHaveCount(1);
    await page.reload(); await expect(h.tab(page, 'Sheet1')).toHaveAttribute('aria-selected', 'true');
    await expect(h.cell(page, 'A1')).toHaveAttribute('aria-selected', 'true'); await h.values(page, { A1: '' });
    await expect.poll(async()=> (await h.grid(page).getByRole('gridcell',{includeHidden:true}).allTextContents())
      .filter(value=>value!=='')).toEqual([]);
    await page.goto('/'); await page.goto(address); await expect(page.getByRole('tab')).toHaveCount(1); await h.values(page, { A1: '' });
    ''')
    s('REQ-1-2-2', 'trim and save workbook name updates editor and home entry', r'''
    await h.blank(page); const original=h.unique(); await h.renameWorkbook(page,original);
    await h.button(page, 'Rename workbook').click(); const name = h.unique();
    await expect(h.field(page, 'Workbook name')).toHaveValue(original);
    await h.field(page, 'Workbook name').fill(`  ${name}  `); await h.button(page, 'Save').click();
    await expect(h.text(page, name).first()).toBeVisible(); await page.goto('/');
    await page.getByRole('link', { name, exact: true }).click();
    await h.persisted(page, () => expect(h.text(page, name).first()).toBeVisible());
    ''')
    s('REQ-1-2-2', 'empty workbook name rejects without changing persisted name', r'''
    await h.blank(page); await h.button(page, 'Rename workbook').click(); const original = await h.field(page, 'Workbook name').inputValue();
    await h.field(page, 'Workbook name').fill('   '); await h.button(page, 'Save').click();
    await expect(h.text(page, 'Workbook name cannot be empty').first()).toBeVisible(); await page.reload();
    await h.button(page, 'Rename workbook').click(); await expect(h.field(page, 'Workbook name')).toHaveValue(original);
    ''')
    s('REQ-1-3-1', 'CSV import preserves every ordered field, Unicode, quotes and embedded newline', r'''
    await page.goto('/'); await h.button(page, 'Import CSV').click(); const name = h.unique();
    const dialog = page.getByRole('dialog', { name: 'Import CSV', exact: true });
    await h.field(dialog, 'CSV file').setInputFiles({ name: `${name}.csv`, mimeType: 'text/csv', buffer: Buffer.from('名称,备注,值,空\r\n中文,"逗号,文本",12,\r\nEnglish,"双""引号\n下一行",007,', 'utf8') });
    await h.button(dialog, 'Confirm import').click(); await expect(h.text(page, name).first()).toBeVisible();
    await h.persisted(page, () => h.ordinary(page, { A1: '名称', B1: '备注', C1: '值', D1: '空', A2: '中文', B2: '逗号,文本', C2: '12', D2: '', A3: 'English', B3: '双"引号\n下一行', C3: '007', D3: '' }));
    ''')
    s('REQ-1-3-1', 'unclosed CSV quote leaves no partial workbook', r'''
    await page.goto('/'); await expect(page.getByRole('link',{name:'Q3 Sales',exact:true})).toBeVisible(); const before = (await page.getByRole('link').allTextContents()).sort(); await h.button(page, 'Import CSV').click();
    const name = h.unique(), dialog = page.getByRole('dialog', { name: 'Import CSV', exact: true });
    await h.field(dialog, 'CSV file').setInputFiles({ name: `${name}.csv`, mimeType: 'text/csv', buffer: Buffer.from('A,B\n1,"unclosed') });
    await h.button(dialog, 'Confirm import').click(); await expect(h.text(page, 'Invalid CSV file format. Import failed.').first()).toBeVisible();
    await page.goto('/'); await expect(page.getByRole('link', { name, exact: true })).toHaveCount(0);
    await expect.poll(async()=> (await page.getByRole('link').allTextContents()).sort()).toEqual(before); await page.reload();
    await expect(page.getByRole('link', { name, exact: true })).toHaveCount(0);
    ''')
    s('REQ-1-3-2', 'CSV downloads actual values with escaping and leaves active state intact', r'''
    await page.goto('/'); await h.button(page,'Import CSV').click(); const dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
    await h.field(dialog,'CSV file').setInputFiles({name:`${h.unique()}.csv`,mimeType:'text/csv',buffer:Buffer.from('"中文,comma",,"quote""line\nnext"\n5,,10')}); await h.button(dialog,'Confirm import').click();
    await h.edit(page, 'A2', '5'); await h.edit(page, 'C2', '=A2*2');
    await h.formula(page, 'C2', '=A2*2', '10');
    expect(h.parseCSV(await h.csv(page))).toEqual([['中文,comma', '', 'quote"line\nnext'], ['5', '', '10']]);
    await expect(h.tab(page, 'Sheet1')).toHaveAttribute('aria-selected', 'true'); await expect(h.field(page, 'Formula bar')).toHaveValue('=A2*2');
    await h.persisted(page, () => h.formula(page, 'C2', '=A2*2', '10'));
    ''')
    s('REQ-2-1-1', 'new sheet chooses first unused name and isolates previous data', r'''
    await h.blank(page); await h.edit(page, 'A1', 'source'); await h.button(page, 'Add worksheet').click();
    await expect(h.tab(page, 'Sheet2')).toHaveAttribute('aria-selected', 'true'); await h.values(page, { A1: '' });
    await expect(h.cell(page, 'A1')).toHaveAttribute('aria-selected', 'true'); await h.tab(page, 'Sheet1').click(); await h.values(page, { A1: 'source' });
    await h.persisted(page, () => expect(h.tab(page, 'Sheet2')).toBeVisible());
    ''')
    s('REQ-2-1-2', 'switch restores each sheet formula and selected cell and last active sheet', r'''
    await h.blank(page); await h.edit(page, 'B2', '=2+3'); await h.cell(page, 'B2').click();
    await h.button(page, 'Add worksheet').click(); await h.edit(page, 'C3', 'other'); await h.cell(page, 'C3').click();
    await h.tab(page, 'Sheet1').click(); await expect(h.cell(page, 'B2')).toHaveAttribute('aria-selected', 'true'); await h.formula(page, 'B2', '=2+3', '5');
    await h.tab(page, 'Sheet2').click(); await h.persisted(page, async () => { await expect(h.tab(page, 'Sheet2')).toHaveAttribute('aria-selected', 'true'); await expect(h.cell(page, 'C3')).toHaveAttribute('aria-selected', 'true'); await expect(h.field(page, 'Formula bar')).toHaveValue('other'); });
    await h.tab(page, 'Sheet1').click(); await h.values(page, { B2: '5', C3: '' });
    ''')
    s('REQ-2-1-3', 'rename sheet trims and persists; duplicate and empty names preserve original', r'''
    await h.blank(page); await h.button(page, 'Add worksheet').click(); await h.sheetMenu(page, 'Sheet2', 'Rename');
    const dialog = page.getByRole('dialog', { name: 'Rename worksheet', exact: true }); await expect(h.field(dialog, 'Worksheet name')).toHaveValue('Sheet2');
    await h.field(dialog, 'Worksheet name').fill('Sheet1'); await h.button(dialog, 'Save').click(); await expect(h.text(page, 'Worksheet name already exists').first()).toBeVisible();
    await h.field(dialog, 'Worksheet name').fill('  '); await h.button(dialog, 'Save').click(); await expect(h.text(page, 'Worksheet name cannot be empty').first()).toBeVisible();
    await page.reload(); await expect(h.tab(page, 'Sheet2')).toBeVisible(); await h.sheetMenu(page, 'Sheet2', 'Rename');
    await h.field(page, 'Worksheet name').fill('  Analysis  '); await h.button(page.getByRole('dialog', { name: 'Rename worksheet', exact: true }), 'Save').click();
    await h.persisted(page, () => expect(h.tab(page, 'Analysis')).toBeVisible()); await expect(h.tab(page, 'Sheet2')).toHaveCount(0);
    ''')
    s('REQ-2-1-4', 'delete confirms target and keeps last worksheet safe', r'''
    await h.blank(page); await h.sheetMenu(page, 'Sheet1', 'Delete'); await expect(h.text(page, 'A workbook must contain at least one worksheet').first()).toBeVisible();
    await expect(page.getByRole('dialog', { name: 'Delete worksheet', exact: true })).toHaveCount(0);
    await h.button(page, 'Add worksheet').click(); await h.edit(page, 'A1', 'only-in-deleted-sheet'); await h.sheetMenu(page, 'Sheet2', 'Delete');
    const dialog = page.getByRole('dialog', { name: 'Delete worksheet', exact: true }); await expect(dialog).toContainText('Sheet2'); await h.button(dialog, 'Delete worksheet').click();
    await h.persisted(page, async () => { await expect(h.tab(page, 'Sheet2')).toHaveCount(0); await expect(h.tab(page, 'Sheet1')).toHaveAttribute('aria-selected', 'true'); await h.values(page, { A1: '' }); });
    ''')
    for node, axis, at, insert, delete, shifted, original in [
     ('REQ-2-2-1','row','2','Insert 1 row above','Delete row',{'A2':'','B2':'','C2':'','A3':'East','B3':'10','C3':'Open','A4':'North','B4':'20','C4':'Closed','A5':'East','B5':'30','C5':'Closed'},{'A2':'North','B2':'20','A3':'East','B3':'30'}),
     ('REQ-2-2-2','column','B','Insert 1 column left','Delete column',{'A1':'Region','B1':'','B2':'','C1':'Sales','C2':'10','D1':'Status','D2':'Open','C3':'20','D3':'Closed','C4':'30','D4':'Closed'},{'B1':'Sales','B2':'10','C1':'Status','C2':'Open'})]:
     s(node, f'{axis} insert/delete moves complete records and persists', f'''
     await h.sourceData(page); await h.structure(page, {json.dumps(axis)}, {json.dumps(at)}, {json.dumps(insert)});
     await h.persisted(page, () => h.values(page, {json.dumps(shifted)}));
     await h.structure(page, {json.dumps(axis)}, {json.dumps(at)}, {json.dumps(delete)});
     await h.persisted(page, () => h.values(page, {json.dumps({'A1':'Region','B1':'Sales','C1':'Status','A2':'East','B2':'10','C2':'Open','A3':'North','B3':'20','C3':'Closed','A4':'East','B4':'30','C4':'Closed'})}));
     ''')
    s('REQ-2-2-1', 'insert below then delete referenced row adjusts original formulas', r'''
    await h.blank(page); await h.edit(page, 'A2', '10'); await h.edit(page, 'B4', '=A2*2');
    await h.structure(page, 'row', '1', 'Insert 1 row below'); await h.formula(page, 'B5', '=A3*2', '20');
    await h.structure(page, 'row', '3', 'Delete row'); await h.persisted(page, () => expect(h.cell(page, 'B4')).toHaveText('#REF!'));
    ''')
    s('REQ-2-2-2', 'insert right then delete source column adjusts formulas and invalid references', r'''
    await h.blank(page); await h.edit(page, 'B1', '10'); await h.edit(page, 'D1', '=B1*2');
    await h.structure(page, 'column', 'A', 'Insert 1 column right'); await h.formula(page, 'E1', '=C1*2', '20');
    await h.structure(page, 'column', 'C', 'Delete column'); await h.persisted(page, () => expect(h.cell(page, 'D1')).toHaveText('#REF!'));
    ''')
    s('REQ-3-1-1', 'grid and formula-bar edits commit on Enter or blur and Escape cancels', r'''
    await h.blank(page); await h.edit(page, 'A1', 'text', true); await h.edit(page, 'B1', 'TRUE'); await h.edit(page, 'C1', '2026-09-30'); await h.edit(page, 'E1', '12.5');
    await h.cell(page, 'A1').dblclick(); await h.field(page, 'Edit A1').fill('cancelled'); await h.field(page, 'Edit A1').press('Escape'); await h.values(page, { A1: 'text' });
    await h.cell(page, 'A1').click(); await h.field(page, 'Formula bar').fill('committed-on-blur'); await h.cell(page, 'D1').click();
    await h.persisted(page, () => h.values(page, { A1: 'committed-on-blur', B1: 'TRUE', C1: '2026-09-30', E1: '12.5' }));
    ''')
    for menu in [False,True]:
     s('REQ-3-1-2', 'paste rectangle through '+('menu' if menu else 'Ctrl+V')+' preserves empties and outside cells', f'''
     await h.blank(page); await h.edit(page, 'D4', 'outside'); await h.edit(page, 'C2', '=1+1');
     await h.paste(page, 'B2', 'East\\t\\t1200\\nNorth\\t800\\t', {str(menu).lower()});
     await h.persisted(page, () => h.values(page, {{ B2: 'East', C2: '', D2: '1200', B3: 'North', C3: '800', D3: '', D4: 'outside' }}));
     ''')
    s('REQ-3-1-3', 'complete rectangle replaces and persists exact selected ARIA cells independently per sheet', r'''
    await h.blank(page); await h.range(page, 'B2', 'C3');
    const check = async () => h.selection(page,['B2','C2','B3','C3'],['A1','A2','B1','D3']);
    await check(); await h.button(page, 'Add worksheet').click(); await h.cell(page,'D4').click(); await h.tab(page,'Sheet1').click(); await h.persisted(page, check);
    await h.cell(page,'A1').click(); await expect(h.cell(page,'B2')).toHaveAttribute('aria-selected','false');
    ''')
    s('REQ-3-2-1', 'copy rectangle preserves every value, adjusted formula and outside data', r'''
    await h.blank(page); await h.paste(page, 'A1', '2\t=A1+$A$1\n3\t=A2'); await h.edit(page, 'F6', 'outside');
    await h.range(page, 'A1', 'B2'); await page.keyboard.press('Control+c'); await h.cell(page, 'C3').click(); await page.keyboard.press('Control+v');
    await h.persisted(page, async () => { await h.values(page, { A1:'2',A2:'3',C3:'2',C4:'3',F6:'outside' }); await h.formula(page,'B1','=A1+$A$1','4'); await h.formula(page,'B2','=A2','3'); await h.formula(page,'D3','=C3+$A$1','4'); await h.formula(page,'D4','=C4','3'); });
    ''')
    s('REQ-3-2-1', 'cut rectangle clears every source only after all target values and formulas commit', r'''
    await h.blank(page); await h.paste(page,'A1','2\t=2+3\n3\t=6/2'); await h.edit(page,'F6','outside');
    await h.range(page,'A1','B2'); await page.keyboard.press('Control+x'); await h.values(page,{A1:'2',B1:'5',A2:'3',B2:'3'});
    await h.cell(page,'C3').click(); await page.keyboard.press('Control+v');
    await h.persisted(page,async()=>{ await h.values(page,{A1:'',B1:'',A2:'',B2:'',C3:'2',C4:'3',F6:'outside'}); await h.formula(page,'D3','=2+3','5'); await h.formula(page,'D4','=6/2','3'); });
    ''')
    s('REQ-3-2-2', 'undo/redo restores complete operations and a new edit discards redo branch', r'''
    await h.blank(page); await h.edit(page, 'A1', 'first'); await h.paste(page, 'A1', 'second\tthird');
    await h.button(page, 'Undo').click(); await h.values(page, { A1:'first', B1:'' }); await page.keyboard.press('Control+z'); await h.values(page,{A1:'',B1:''});
    await h.button(page,'Redo').click(); await h.values(page,{A1:'first'}); await page.keyboard.press('Control+y'); await h.values(page,{A1:'second',B1:'third'});
    await h.button(page,'Undo').click(); await h.edit(page,'A1','new branch'); await expect(h.button(page,'Redo')).toBeDisabled(); await page.keyboard.press('Control+y');
    await h.persisted(page, () => h.values(page,{A1:'new branch',B1:''}));
    ''')
    s('REQ-3-2-2', 'undo row structure restores formulas and redo result persists', r'''
    await h.blank(page); await h.edit(page,'A2','10'); await h.edit(page,'B2','=A2*2'); await h.structure(page,'row','2','Insert 1 row above');
    await h.formula(page,'B3','=A3*2','20'); await h.button(page,'Undo').click(); await h.formula(page,'B2','=A2*2','20');
    await h.button(page,'Redo').click(); await h.persisted(page, () => h.formula(page,'B3','=A3*2','20'));
    ''')
    for expression,result in [('=(2+3)*4-6/2','17'),('=sUm(A1:A4)','30'),('=AVERAGE(A1:A4)','15'),('=COUNT(A1:A4)','2'),('=MIN(A1:A4)','10'),('=MAX(A1:A4)','20')]:
     s('REQ-4-1-1', 'formula '+expression+' uses numeric cells and ignores blanks/text', f'''
     await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',{json.dumps(expression)});
     await h.persisted(page, () => h.formula(page,'B1',{json.dumps(expression)},{json.dumps(result)}));
     ''')
    s('REQ-4-1-2', 'copy adjusts relative references, keeps absolute references and rejects out-of-bounds', r'''
    await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'B2','20'); await h.edit(page,'C3','=A1+$A$1');
    await h.cell(page,'C3').click(); await page.keyboard.press('Control+c'); await h.cell(page,'D4').click(); await page.keyboard.press('Control+v');
    await h.formula(page,'D4','=B2+$A$1','30'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+c'); await h.cell(page,'B2').click(); await page.keyboard.press('Control+v');
    await h.persisted(page, () => h.formula(page,'B2','=#REF!','#REF!')); await h.formula(page,'C3','=A1+$A$1','20');
    ''')
    s('REQ-4-2-1', 'direct and transitive dependent formulas update after edit and paste', r'''
    await h.blank(page); await h.edit(page,'A1','2'); await h.edit(page,'B1','=A1*2'); await h.edit(page,'C1','=B1+1');
    await h.edit(page,'A1','5'); await h.values(page,{B1:'10',C1:'11'}); await h.paste(page,'A1','7');
    await h.persisted(page, async () => { await h.formula(page,'B1','=A1*2','14'); await h.formula(page,'C1','=B1+1','15'); });
    ''')
    for expression,error in [('=1/0','#DIV/0!'),('=#REF!','#REF!'),('=UNKNOWN(A1)','#NAME?'),('=1+','#ERROR!'),('=B1','#REF!')]:
     s('REQ-4-2-2', expression+' persists error, isolates other cells, then recovers', f'''
     await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',{json.dumps(expression)});
     await h.persisted(page, () => h.formula(page,'B1',{json.dumps(expression)},{json.dumps(error)})); await h.values(page,{{A1:'6'}});
     await h.edit(page,'B1','=A1+1'); await h.persisted(page, () => h.formula(page,'B1','=A1+1','7'));
     ''')
    s('REQ-4-2-2', 'indirect cycle reports stable reference error and recovers dependencies', r'''
    await h.blank(page); await h.edit(page,'A1','=B1'); await h.edit(page,'B1','=A1'); await h.persisted(page, () => h.values(page,{A1:'#REF!',B1:'#REF!'}));
    await h.edit(page,'B1','4'); await h.persisted(page, () => h.formula(page,'A1','=B1','4'));
    ''')
    for order,expected in [('Ascending',{'A2':'East','B2':'10','C2':'Open','A3':'East','B3':'30','C3':'Closed','A4':'North','B4':'20','C4':'Closed'}),('Descending',{'A2':'North','B2':'20','C2':'Closed','A3':'East','B3':'10','C3':'Open','A4':'East','B4':'30','C4':'Closed'})]:
     s('REQ-5-1-1', order+' sort moves complete records stably and preserves header/outside cells', f'''
     await h.sourceData(page); await h.edit(page,'E5','outside'); await h.range(page,'A1','C4'); await h.data(page,'Sort range');
     const dialog=page.getByRole('dialog',{{name:'Sort range',exact:true}}); await h.choose(dialog,'Sort by','Region'); await h.choose(dialog,'Order',{json.dumps(order)});
     await dialog.getByRole('checkbox',{{name:'Data has header row',exact:true}}).check(); await h.button(dialog,'Sort').click();
     await h.persisted(page, () => h.values(page,{{...{json.dumps(expected)},A1:'Region',B1:'Sales',C1:'Status',E5:'outside'}}));
     ''')
    s('REQ-5-1-2', 'value filter hides rather than deletes, persists and export includes hidden records', r'''
    await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.button(page,'Filter Region').click();
    const dialog=page.getByRole('dialog',{name:'Filter Region',exact:true}); await h.button(dialog,'Clear selection').click(); await dialog.getByRole('checkbox',{name:'East',exact:true}).check(); await h.button(dialog,'Apply').click();
    await h.persisted(page, async () => { await h.filterHeaders(page,{A1:'Region',B1:'Sales',C1:'Status'}); await expect(h.cell(page,'A2')).toBeVisible(); await expect(h.cell(page,'A3')).toBeHidden(); await expect(h.cell(page,'A4')).toBeVisible(); });
    expect(h.parseCSV(await h.csv(page))).toEqual([['Region','Sales','Status'],['East','10','Open'],['North','20','Closed'],['East','30','Closed']]);
    await h.data(page,'Clear filter'); await h.persisted(page, async () => { await expect(h.cell(page,'A3')).toBeVisible(); await h.values(page,{A2:'East',A3:'North',A4:'East'}); });
    ''')
    s('REQ-5-1-2', 'conditions combine with AND and clearing preserves original data', r'''
    await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter');
    for(const [header,condition,value] of [['Region','Text contains','East'],['Sales','Greater than','15']]) { await h.button(page,`Filter ${header}`).click(); const dialog=page.getByRole('dialog',{name:`Filter ${header}`,exact:true}); await h.choose(dialog,'Condition',condition); await h.field(dialog,'Value').fill(value); await h.button(dialog,'Apply').click(); }
    await h.persisted(page, async () => { await h.filterHeaders(page,{A1:'Region',B1:'Sales',C1:'Status'}); await expect(h.cell(page,'A2')).toBeHidden(); await expect(h.cell(page,'A3')).toBeHidden(); await expect(h.cell(page,'A4')).toBeVisible(); });
    ''')
    s('REQ-5-2-1', 'dropdown trims options and rejects invalid edits without changing saved value', r'''
    await h.blank(page); await h.edit(page,'A1','Open'); await h.validation(page,'A1','A2','Dropdown'); await h.button(page,'Open dropdown for A1').click();
    await page.getByRole('option',{name:'Closed',exact:true}).click(); await h.values(page,{A1:'Closed'}); await page.reload(); await h.edit(page,'A1','invalid');
    await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/)).toBeVisible(); await h.persisted(page, () => h.values(page,{A1:'Closed'}));
    ''')
    s('REQ-5-2-1', 'inclusive numeric boundaries and rectangle rejection are atomic across reload', r'''
    await h.blank(page); await h.edit(page,'B2','0'); await h.edit(page,'B3','100'); await h.validation(page,'B2','B3'); await page.reload(); await h.edit(page,'B2','100'); await h.edit(page,'B2','0'); await h.edit(page,'B3','0'); await h.edit(page,'B3','100');
    await h.edit(page,'B3','101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.values(page,{B2:'0',B3:'100'});
    await h.paste(page,'B2','50\n101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.persisted(page, () => h.values(page,{B2:'0',B3:'100'}));
    ''')
    s('REQ-5-2-1', 'editing and deleting a validation rule closes dialog and preserves values', r'''
    await h.blank(page); await h.edit(page,'A1','50'); await h.validation(page,'A1','A1'); await h.cell(page,'A1').click(); await h.data(page,'Data validation');
    const dialog=page.getByRole('dialog',{name:'Data validation',exact:true}); await expect(h.field(dialog,'Minimum')).toHaveValue('0'); await expect(h.field(dialog,'Maximum')).toHaveValue('100');
    await h.field(dialog,'Maximum').fill('200'); await h.button(dialog,'Save').click(); await expect(dialog).toBeHidden(); await h.edit(page,'A1','150'); await h.values(page,{A1:'150'});
    await h.data(page,'Data validation'); await h.button(dialog,'Delete rule').click(); await expect(dialog).toBeHidden(); await h.edit(page,'A1','300'); await h.persisted(page, () => h.values(page,{A1:'300'}));
    ''')
    for node,axis,at,action,target in [('REQ-2-2-1','row','2','Insert 1 row above','B3'),('REQ-2-2-2','column','B','Insert 1 column left','C2')]:
     s(node,'structure moves numeric validation with the original cell',f'''
     await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,{json.dumps(axis)},{json.dumps(at)},{json.dumps(action)});
     await h.edit(page,{json.dumps(target)},'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.persisted(page, () => h.values(page,{{{json.dumps(target)}:'50'}}));
     ''')
    for method,expected in [('SUM',{'A1':'Region','B1':'SUM of Sales','A2':'East','B2':'40','A3':'North','B3':'20','A4':'Grand Total','B4':'60'}),('COUNT',{'A1':'Region','B1':'COUNT of Sales','A2':'East','B2':'2','A3':'North','B3':'1','A4':'Grand Total','B4':'3'}),('AVERAGE',{'A1':'Region','B1':'AVERAGE of Sales','A2':'East','B2':'20','A3':'North','B3':'20','A4':'Grand Total','B4':'20'})]:
     s('REQ-5-3-1',method+' pivot orders groups by appearance and persists exact grand totals',f'''
     await h.sourceData(page); await h.pivot(page,{json.dumps(method)}); await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');
     await h.persisted(page, () => h.values(page,{json.dumps(expected)})); await h.tab(page,'Sheet1').click(); await h.values(page,{{A2:'East',B2:'10',A3:'North',B3:'20',A4:'East',B4:'30'}});
     ''')
    s('REQ-5-3-1','column COUNT pivot displays empty combinations as zero and correct totals',r'''
    await h.sourceData(page); await h.pivot(page,'COUNT','Status'); await h.persisted(page, () => h.values(page,{A1:'Region',B1:'Open',C1:'Closed',D1:'Grand Total',A2:'East',B2:'1',C2:'1',D2:'2',A3:'North',B3:'0',C3:'1',D3:'1',A4:'Grand Total',B4:'1',C4:'2',D4:'3'}));
    ''')
    s('REQ-5-3-1','source edits do not update pivot before refresh; refresh completely replaces result',r'''
    await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.edit(page,'B2','50'); await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'40',B4:'60'});
    await h.button(page,'Refresh pivot table').click(); await h.persisted(page, () => h.values(page,{B2:'80',B4:'100'}));
    ''')
    s('REQ-5-3-1','deleted source field refuses refresh and preserves last successful pivot',r'''
    await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.tab(page,'Pivot1').click();
    await h.button(page,'Refresh pivot table').click(); await expect(h.text(page,'Pivot field is no longer available. Select a new field.').first()).toBeVisible(); await h.persisted(page, () => h.values(page,{A1:'Region',B1:'SUM of Sales',A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}));
    await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'Region',B1:'Status',A2:'East',B2:'Open',A3:'North',B3:'Closed',A4:'East',B4:'Closed'});
    ''')
    s('REQ-5-3-1','SUM without numeric values rejects and preserves source and old result',r'''
    await h.sourceData(page); await h.pivot(page); const editor=page.getByRole('region',{name:'Pivot table editor',exact:true}); await h.choose(editor,'Values','Status'); await h.button(editor,'Apply').click();
    await expect(h.text(page,'Value field requires numeric values').first()).toBeVisible(); await h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'}); await h.tab(page,'Sheet1').click(); await h.values(page,{C2:'Open',C3:'Closed',C4:'Closed'});
    ''')
    s('REQ-2-1-4','pivot source cannot be deleted until its result worksheet is deleted',r'''
    await h.sourceData(page); await h.pivot(page); await h.sheetMenu(page,'Sheet1','Delete'); const dialog=page.getByRole('dialog',{name:'Delete worksheet',exact:true}); await h.button(dialog,'Delete worksheet').click();
    await expect(h.text(page,'Please delete or rebuild dependent pivot tables first').first()).toBeVisible(); await expect(dialog).toBeHidden(); await expect(h.tab(page,'Sheet1')).toBeVisible(); await h.values(page,{B2:'40',B4:'60'}); await page.reload(); await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'Region',B1:'Sales',C1:'Status',A2:'East',B2:'10',C2:'Open',A3:'North',B3:'20',C3:'Closed',A4:'East',B4:'30',C4:'Closed'}); await h.tab(page,'Pivot1').click();
    await h.sheetMenu(page,'Pivot1','Delete'); await h.button(dialog,'Delete worksheet').click(); await h.button(page,'Add worksheet').click(); await h.sheetMenu(page,'Sheet1','Delete'); await h.button(dialog,'Delete worksheet').click();
    await h.persisted(page, async () => { await expect(h.tab(page,'Sheet1')).toHaveCount(0); await expect(h.tab(page,'Pivot1')).toHaveCount(0); await expect(h.tab(page,'Sheet2')).toBeVisible(); });
    ''')
    s('REQ-5-3-1','COUNT includes nonnumeric nonempty records and blanks contribute zero',r'''
    await h.sourceData(page); await h.edit(page,'B2','text'); await h.edit(page,'B3',''); await h.pivot(page,'COUNT'); await h.persisted(page, () => h.values(page,{B2:'2',B3:'0',B4:'2'}));
    ''')
    s('REQ-5-1-1','numeric sort moves whole records rather than lexical or single-column order',r'''
    await h.sourceData(page); await h.edit(page,'B2','100'); await h.edit(page,'B3','2'); await h.edit(page,'B4','30'); await h.range(page,'A1','C4'); await h.data(page,'Sort range'); const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await h.choose(dialog,'Sort by','Sales'); await h.choose(dialog,'Order','Ascending'); await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check(); await h.button(dialog,'Sort').click(); await h.persisted(page, () => h.values(page,{A2:'North',B2:'2',C2:'Closed',A3:'East',B3:'30',C3:'Closed',A4:'East',B4:'100',C4:'Open'}));
    ''')
    s('REQ-3-1-2','bulk paste recalculates outside dependent formulas without overwriting them',r'''
    await h.blank(page); await h.edit(page,'A1','1'); await h.edit(page,'B1','2'); await h.edit(page,'D1','=A1+B1'); await h.paste(page,'A1','3\t4'); await h.persisted(page, () => h.formula(page,'D1','=A1+B1','7'));
    ''')
    s('REQ-3-2-1','rejected range cut preserves source and all validated target cells atomically',r'''
    await h.blank(page); await h.paste(page,'A1','50\n101'); await h.edit(page,'C1','10'); await h.edit(page,'C2','20'); await h.validation(page,'C1','C2'); await h.range(page,'A1','A2'); await page.keyboard.press('Control+x'); await h.cell(page,'C1').click(); await page.keyboard.press('Control+v'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.persisted(page, () => h.values(page,{A1:'50',A2:'101',C1:'10',C2:'20'}));
    ''')
    s('REQ-1-1-1', 'home/editor timestamp agrees with persisted renamed workbook and never loads another workbook', r'''
    await h.blank(page); const name=h.unique(); await h.renameWorkbook(page,name); const address=page.url(); await h.edit(page,'A1','first-workbook-only');
    await page.goto('/'); const updated=await h.recordUpdated(page,name); await page.getByRole('link',{name,exact:true}).click(); await expect(h.text(page,updated).first()).toBeVisible();
    await h.persisted(page,()=>h.values(page,{A1:'first-workbook-only'})); await h.blank(page); const otherName=h.unique(); await h.renameWorkbook(page,otherName); await h.edit(page,'A1','second-workbook-only');
    await page.goto(address); await h.values(page,{A1:'first-workbook-only'}); await expect(h.text(page,name).first()).toBeVisible();
    await h.reopen(page,otherName); await h.values(page,{A1:'second-workbook-only'}); await h.reopen(page,name); await h.values(page,{A1:'first-workbook-only'});
    ''', file='INTEGRATION-workbook-context', requires=['REQ-1-1-1','REQ-1-2-1','REQ-1-2-2','REQ-3-1-1'])
    s('REQ-1-1-1', 'home reopening restores sheet order, formulas, filter, validation and pivot state together', r'''
    await h.sourceData(page); const name=h.unique(); await h.renameWorkbook(page,name); await h.edit(page,'E2','=B2*2'); await h.validation(page,'B2','B4');
    await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.pivot(page);
    await h.button(page,'Add worksheet').click(); await h.edit(page,'A1','independent-sheet'); await h.tab(page,'Pivot1').click(); await h.cell(page,'B2').click();
    await h.reopen(page,name); await h.tabOrder(page,['Sheet1','Pivot1','Sheet2']); await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');
    await h.values(page,{A1:'Region',B1:'SUM of Sales',B2:'40',B4:'60'}); await expect(h.cell(page,'B2')).toHaveAttribute('aria-selected','true'); await expect(h.field(page,'Formula bar')).toHaveValue('40');
    const editor=page.getByRole('region',{name:'Pivot table editor',exact:true}); await h.chosen(editor,'Rows','Region'); await h.chosen(editor,'Values','Sales'); await h.chosen(editor,'Summarize by','SUM');
    await h.tab(page,'Sheet1').click(); await h.visibleRows(page,['A2','A4'],['A3']); await h.formula(page,'E2','=B2*2','20');
    await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'10',E2:'20'});
    await h.tab(page,'Sheet2').click(); await h.persisted(page,()=>h.values(page,{A1:'independent-sheet',E2:''}));
    ''', file='INTEGRATION-workbook-context', requires=['REQ-1-1-1','REQ-1-2-2','REQ-2-1-1','REQ-2-1-2','REQ-3-1-1','REQ-3-1-2','REQ-4-1-1','REQ-5-1-2','REQ-5-2-1','REQ-5-3-1'])
    s('REQ-1-2-1', 'new workbook has no imported values, filter, validation or pivot from another workbook', r'''
    await h.sourceData(page); const original=page.url(); await h.validation(page,'B2','B4'); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.pivot(page);
    await h.blank(page); await expect(page.getByRole('tab')).toHaveCount(1); await expect(h.grid(page)).toHaveAttribute('aria-multiselectable','true'); await h.selection(page,['A1'],['B1','A2','B2']);
    await h.values(page,{A1:'',B2:'',C4:''}); await expect(h.button(page,'Filter Region')).toHaveCount(0); await expect(h.button(page,'Open dropdown for B2')).toHaveCount(0); await expect(h.button(page,'Refresh pivot table')).toHaveCount(0);
    await h.edit(page,'B2','101'); await h.persisted(page,()=>h.values(page,{B2:'101'})); await page.goto(original); await expect(h.tab(page,'Pivot1')).toBeVisible(); await h.tab(page,'Sheet1').click(); await h.values(page,{B2:'10'});
    ''', file='INTEGRATION-workbook-context', requires=['REQ-1-2-1','REQ-3-1-1','REQ-3-1-2','REQ-5-1-2','REQ-5-2-1','REQ-5-3-1'])
    s('REQ-1-2-2', 'renaming is scoped to current workbook and updates refreshed home record', r'''
    await h.blank(page); const first=h.unique(); await h.renameWorkbook(page,first); const address=page.url(); await h.edit(page,'A1','keep-original-data');
    await h.blank(page); const second=h.unique(); await h.renameWorkbook(page,second); await h.edit(page,'A1','keep-second-data');
    await page.goto(address); const renamed=h.unique(); await h.renameWorkbook(page,`  ${renamed}  `); await page.goto('/'); await page.reload();
    await expect(page.getByRole('link',{name:first,exact:true})).toHaveCount(0); await expect(page.getByRole('link',{name:renamed,exact:true})).toBeVisible(); await expect(page.getByRole('link',{name:second,exact:true})).toBeVisible();
    await h.reopen(page,renamed); await h.values(page,{A1:'keep-original-data'}); await h.reopen(page,second); await h.values(page,{A1:'keep-second-data'});
    ''')
    s('REQ-1-3-1', 'import treats first row as data and strips only the final csv extension from the file name', r'''
    await page.goto('/'); const name=`${h.unique()}.part`; await h.button(page,'Import CSV').click(); const dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
    await h.field(dialog,'CSV file').setInputFiles({name:`${name}.csv`,mimeType:'text/csv',buffer:Buffer.from('Region,Sales,Status\nEast,1200,Open\nNorth,800,Closed')}); await h.button(dialog,'Confirm import').click();
    await expect(h.tab(page,'Sheet1')).toHaveAttribute('aria-selected','true'); await expect(page.getByRole('tab')).toHaveCount(1); const address=page.url();
    await h.ordinary(page,{A1:'Region',B1:'Sales',C1:'Status',A2:'East',B2:'1200',C2:'Open',A3:'North',B3:'800',C3:'Closed'}); await h.edit(page,'A1','ordinary-first-row');
    await page.goto('/'); await page.reload(); await expect(page.getByRole('link',{name,exact:true})).toBeVisible(); await page.goto(address); await h.values(page,{A1:'ordinary-first-row',A2:'East',A3:'North'});
    ''')
    s('REQ-1-3-2', 'export reads only active worksheet and preserves selection and original formulas', r'''
    await h.sourceData(page); await h.button(page,'Add worksheet').click(); await h.paste(page,'A1','Label\tValue\nOnly-second\t7'); await h.edit(page,'C2','=B2*3'); await h.cell(page,'C2').click();
    expect(h.parseCSV(await h.csv(page))).toEqual([['Label','Value',''],['Only-second','7','21']]);
    await expect(h.tab(page,'Sheet2')).toHaveAttribute('aria-selected','true'); await h.selection(page,['C2'],['A1','B2']); await expect(h.field(page,'Formula bar')).toHaveValue('=B2*3');
    await h.persisted(page,()=>h.formula(page,'C2','=B2*3','21')); await h.tab(page,'Sheet1').click(); expect(h.parseCSV(await h.csv(page))).toEqual([['Region','Sales','Status'],['East','10','Open'],['North','20','Closed'],['East','30','Closed']]);
    ''')
    s('REQ-2-1-1', 'worksheet addition reuses first unused SheetN and appends in persisted order', r'''
    await h.blank(page); await h.button(page,'Add worksheet').click(); await h.button(page,'Add worksheet').click(); await h.sheetMenu(page,'Sheet2','Delete');
    await h.button(page.getByRole('dialog',{name:'Delete worksheet',exact:true}),'Delete worksheet').click(); await h.button(page,'Add worksheet').click();
    await h.persisted(page,async()=>{ await h.tabOrder(page,['Sheet1','Sheet3','Sheet2']); await expect(h.tab(page,'Sheet2')).toHaveAttribute('aria-selected','true'); await h.selection(page,['A1'],['A2','B1']); });
    ''')
    s('REQ-2-1-1', 'new sheet does not inherit filters or dropdown/numeric validation and preserves source state', r'''
    await h.sourceData(page); await h.validation(page,'B2','B4'); await h.validation(page,'C2','C4','Dropdown'); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']);
    await h.button(page,'Add worksheet').click(); await h.values(page,{A1:'',B2:'',C2:''}); await expect(h.button(page,'Filter Region')).toHaveCount(0); await expect(h.button(page,'Open dropdown for C2')).toHaveCount(0);
    await h.edit(page,'B2','101'); await h.edit(page,'C2','unconstrained'); await h.tab(page,'Sheet1').click(); await h.visibleRows(page,['A2','A4'],['A3']); await expect(h.button(page,'Open dropdown for C2')).toBeVisible();
    await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'10',C2:'Open'});
    await h.tab(page,'Sheet2').click(); await h.persisted(page,()=>h.values(page,{B2:'101',C2:'unconstrained'}));
    ''')
    s('REQ-2-1-3', 'sheet rename preserves its slot, values, selection, rules and active state', r'''
    await h.blank(page); await h.button(page,'Add worksheet').click(); await h.edit(page,'B2','50'); await h.validation(page,'B2','B3'); await h.cell(page,'B2').click();
    await h.sheetMenu(page,'Sheet2','Rename'); const dialog=page.getByRole('dialog',{name:'Rename worksheet',exact:true}); await h.field(dialog,'Worksheet name').fill('  Analysis  '); await h.button(dialog,'Save').click();
    await h.persisted(page,async()=>{ await h.tabOrder(page,['Sheet1','Analysis']); await expect(h.tab(page,'Analysis')).toHaveAttribute('aria-selected','true'); await expect(h.cell(page,'B2')).toHaveAttribute('aria-selected','true'); await h.values(page,{B2:'50'}); });
    await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'50'});
    ''')
    s('REQ-2-1-4', 'deletion removes complete sheet state and activates an adjacent survivor', r'''
    await h.blank(page); await h.edit(page,'A1','first'); await h.button(page,'Add worksheet').click(); await h.paste(page,'A1','Region\tSales\nDeleted\t50'); await h.validation(page,'B2','B2'); await h.range(page,'A1','B2'); await h.data(page,'Create filter'); await h.edit(page,'D2','=B2*2');
    await h.button(page,'Add worksheet').click(); await h.edit(page,'A1','third'); await h.tab(page,'Sheet2').click(); await h.sheetMenu(page,'Sheet2','Delete'); const dialog=page.getByRole('dialog',{name:'Delete worksheet',exact:true}); await expect(dialog).toContainText('Sheet2'); await h.button(dialog,'Delete worksheet').click();
    await expect(h.tab(page,'Sheet2')).toHaveCount(0); const active=page.getByRole('tab').and(page.locator('[aria-selected="true"]')); await expect(active).toHaveCount(1); await expect(active).toHaveAccessibleName(/^Sheet[13]$/);
    await expect(h.button(page,'Filter Region')).toHaveCount(0); await expect(h.button(page,'Open dropdown for B2')).toHaveCount(0); await h.values(page,{B2:'',D2:''});
    await page.reload(); await expect(h.tab(page,'Sheet2')).toHaveCount(0); await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'first'}); await h.tab(page,'Sheet3').click(); await h.values(page,{A1:'third'});
    ''')
    for node,axis,at,action,expected in [
        ('REQ-2-2-1','row','3','Delete row',{'A1':'Region','B1':'Sales','C1':'Status','A2':'East','B2':'10','C2':'Open','A3':'East','B3':'30','C3':'Closed','A4':'','B4':'','C4':''}),
        ('REQ-2-2-2','column','B','Delete column',{'A1':'Region','B1':'Status','C1':'','A2':'East','B2':'Open','C2':'','A3':'North','B3':'Closed','A4':'East','B4':'Closed'})]:
        s(node,'deleting populated '+axis+' removes only the target and shifts all surviving record fields',f'''
        await h.sourceData(page); await h.button(page,'Add worksheet').click(); await h.edit(page,'A1','other-sheet'); await h.tab(page,'Sheet1').click();
        await h.structure(page,{json.dumps(axis)},{json.dumps(at)},{json.dumps(action)}); await h.persisted(page,()=>h.values(page,{json.dumps(expected)}));
        await h.tab(page,'Sheet2').click(); await h.values(page,{{A1:'other-sheet',B2:''}});
        ''')
    for node,axis,at,action,numeric,dropdown,blank_numeric,blank_dropdown in [
        ('REQ-2-2-1','row','2','Insert 1 row above','B3','C3','B2','C2'),
        ('REQ-2-2-2','column','B','Insert 1 column left','C2','D2','B2','B3')]:
        s(node,'insertion moves dropdown and numeric rules with original values and leaves inserted cells unconstrained',f'''
        await h.sourceData(page); await h.validation(page,'B2','B2'); await h.validation(page,'C2','C2','Dropdown');
        await h.structure(page,{json.dumps(axis)},{json.dumps(at)},{json.dumps(action)}); await page.reload();
        await h.edit(page,{json.dumps(numeric)},'101'); await expect(h.text(page,'Please enter a number from 0 to 100').first()).toBeVisible(); await h.values(page,{{{json.dumps(numeric)}:'10',{json.dumps(dropdown)}:'Open'}});
        await h.button(page,'Open dropdown for '+{json.dumps(dropdown)}).click(); await page.getByRole('option',{{name:'Closed',exact:true}}).click(); await h.edit(page,{json.dumps(dropdown)},'invalid');
        await expect(page.getByText(/^Please select one of the following values: Open,\\s*Closed$/).first()).toBeVisible(); await h.values(page,{{{json.dumps(dropdown)}:'Closed'}});
        await h.edit(page,{json.dumps(blank_numeric)},'101'); await h.edit(page,{json.dumps(blank_dropdown)},'unconstrained'); await h.persisted(page,()=>h.values(page,{{{json.dumps(numeric)}:'10',{json.dumps(dropdown)}:'Closed',{json.dumps(blank_numeric)}:'101',{json.dumps(blank_dropdown)}:'unconstrained'}}));
        ''')
    for node,axis,at,action,target in [
        ('REQ-2-2-1','row','2','Delete row','B2'),
        ('REQ-2-2-2','column','B','Delete column','B2')]:
        s(node,'deleted '+axis+' validation is removed rather than applied to the next surviving cell',f'''
        await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.edit(page,{'"B3"' if axis=='row' else '"C2"'},'70');
        await h.structure(page,{json.dumps(axis)},{json.dumps(at)},{json.dumps(action)}); await h.values(page,{{{json.dumps(target)}:'70'}}); await h.edit(page,{json.dumps(target)},'101');
        await h.persisted(page,()=>h.values(page,{{{json.dumps(target)}:'101'}}));
        ''')
    s('REQ-2-2-1','row insert/delete adjusts existing filter region without deleting or reordering hidden records',r'''
    await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.structure(page,'row','2','Insert 1 row above');
    await h.persisted(page,()=>h.visibleRows(page,['A3','A5'],['A4'])); await h.data(page,'Clear filter'); await h.values(page,{A2:'',A3:'East',B3:'10',A4:'North',B4:'20',A5:'East',B5:'30'});
    await h.range(page,'A1','C5'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.structure(page,'row','3','Delete row');
    await h.persisted(page,()=>h.visibleRows(page,['A4'],['A3'])); await h.data(page,'Clear filter'); await h.values(page,{A2:'',A3:'North',B3:'20',A4:'East',B4:'30'});
    ''')
    s('REQ-2-2-2','column insertion/deletion moves filter headers and preserves conditions on original data',r'''
    await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.condition(page,'Sales','Greater than','15'); await h.structure(page,'column','B','Insert 1 column left');
    await h.persisted(page,()=>h.visibleRows(page,['A3','A4'],['A2'])); await expect(h.button(page,'Filter Sales')).toBeVisible(); await h.structure(page,'column','B','Delete column');
    await h.persisted(page,()=>h.visibleRows(page,['A3','A4'],['A2'])); await h.data(page,'Clear filter'); await h.values(page,{B1:'Sales',B2:'10',B3:'20',B4:'30',C1:'Status',C2:'Open'});
    ''')
    s('REQ-2-2-1','overlapping row changes adjust pivot source range and leave old results until explicit refresh',r'''
    await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'row','3','Insert 1 row above'); await h.paste(page,'A3','South\t5\tOpen');
    await h.tab(page,'Pivot1').click(); await h.values(page,{A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}); await h.button(page,'Refresh pivot table').click();
    await h.persisted(page,()=>h.values(page,{A2:'East',B2:'40',A3:'South',B3:'5',A4:'North',B4:'20',A5:'Grand Total',B5:'65'}));
    await h.tab(page,'Sheet1').click(); await h.structure(page,'row','3','Delete row'); await h.tab(page,'Pivot1').click(); await h.values(page,{A3:'South',B5:'65'}); await h.button(page,'Refresh pivot table').click();
    await h.persisted(page,()=>h.values(page,{A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60',A5:'',B5:''}));
    ''')
    s('REQ-2-2-2','pivot refresh tracks moved source headers after column insertion/deletion',r'''
    await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Insert 1 column left'); await h.edit(page,'C2','50');
    await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'40',B4:'60'}); await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'SUM of Sales',B2:'80',B4:'100'}));
    await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.edit(page,'B2','5'); await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'80',B4:'100'});
    await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{B2:'35',B4:'55'}));
    ''')
    s('REQ-3-1-1','formula bar Escape cancels and grid blur commits without changing unrelated cells',r'''
    await h.blank(page); await h.edit(page,'A1','original'); await h.cell(page,'A1').click(); await h.field(page,'Formula bar').fill('cancelled'); await h.field(page,'Formula bar').press('Escape');
    await h.ordinary(page,{A1:'original'}); await h.cell(page,'B2').dblclick(); await h.field(page,'Edit B2').fill('grid-blur'); await h.cell(page,'D4').click();
    await h.persisted(page,()=>h.ordinary(page,{A1:'original',B2:'grid-blur',D4:''}));
    ''')
    s('REQ-3-1-1','failed formula-bar commit retains original input and every dependent result',r'''
    await h.blank(page); await h.edit(page,'B2','50'); await h.edit(page,'D2','=B2*2'); await h.edit(page,'E2','=D2+1'); await h.validation(page,'B2','B3'); await h.cell(page,'B2').click();
    await h.field(page,'Formula bar').fill('101'); await h.field(page,'Formula bar').press('Enter'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
    await expect(h.field(page,'Formula bar')).toHaveValue('50'); await h.persisted(page,async()=>{ await h.values(page,{B2:'50',D2:'100',E2:'101'}); await h.formula(page,'D2','=B2*2','100'); await h.formula(page,'E2','=D2+1','101'); });
    ''')
    for menu in [False,True]:
        s('REQ-3-1-2','invalid clipboard rectangle is rejected atomically through '+('Paste menu' if menu else 'Ctrl+V'),f'''
        await h.blank(page); await h.paste(page,'A1','10\\t20\\n30\\t40'); await h.validation(page,'A1','B2'); await h.edit(page,'D1','=A1+B1');
        await h.paste(page,'A1','50\\t60\\n70\\t101',{str(menu).lower()}); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
        await h.persisted(page,async()=>{{ await h.values(page,{{A1:'10',B1:'20',A2:'30',B2:'40'}}); await h.formula(page,'D1','=A1+B1','30'); }});
        ''')
    s('REQ-3-1-3','reverse-direction drag replaces a saved rectangle and sorting uses only that rectangle',r'''
    await h.blank(page); await h.paste(page,'A1','outside-a\toutside-b\toutside-c\toutside-d\noutside-e\tRegion\tSales\toutside-f\noutside-g\tEast\t20\toutside-h\noutside-i\tNorth\t10\toutside-j');
    await h.range(page,'C4','B2'); await h.selection(page,['B2','C2','B3','C3','B4','C4'],['A1','A2','A3','A4','B1','C1','D2','D3','D4']);
    await h.data(page,'Sort range'); const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check();
    await h.choose(dialog,'Sort by','Sales'); await h.choose(dialog,'Order','Ascending'); await h.button(dialog,'Sort').click();
    await h.persisted(page,()=>h.values(page,{B2:'Region',C2:'Sales',B3:'North',C3:'10',B4:'East',C4:'20',A1:'outside-a',B1:'outside-b',C1:'outside-c',D1:'outside-d',A2:'outside-e',D2:'outside-f',A3:'outside-g',D3:'outside-h',A4:'outside-i',D4:'outside-j'}));
    await h.range(page,'D5','E6'); await h.persisted(page,()=>h.selection(page,['D5','E5','D6','E6'],['B2','C2','B3','C3','C5','F6']));
    ''')
    s('REQ-3-2-1','rejected copy preserves every source/target formula and outside dependent calculation',r'''
    await h.blank(page); await h.paste(page,'A1','50\n101'); await h.paste(page,'C1','10\n20'); await h.validation(page,'C1','C2'); await h.edit(page,'E1','=C1+C2'); await h.range(page,'A1','A2');
    await page.keyboard.press('Control+c'); await h.cell(page,'C1').click(); await page.keyboard.press('Control+v'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
    await h.persisted(page,async()=>{await h.values(page,{A1:'50',A2:'101',C1:'10',C2:'20'});await h.formula(page,'E1','=C1+C2','30');});
    ''')
    s('REQ-3-2-2','undo and redo a range cut restore both rectangles and original formulas as one operation',r'''
    await h.blank(page); await h.paste(page,'A1','2\t=2+3\n3\t=6/2'); await h.paste(page,'C3','old-1\told-2\nold-3\told-4'); await h.edit(page,'F6','outside'); await h.range(page,'A1','B2');
    await page.keyboard.press('Control+x'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+v'); await h.button(page,'Undo').click();
    await h.values(page,{A1:'2',A2:'3',C3:'old-1',D3:'old-2',C4:'old-3',D4:'old-4',F6:'outside'}); await h.formula(page,'B1','=2+3','5'); await h.formula(page,'B2','=6/2','3');
    await h.button(page,'Redo').click(); await h.persisted(page,async()=>{await h.values(page,{A1:'',B1:'',A2:'',B2:'',C3:'2',C4:'3',F6:'outside'}); await h.formula(page,'D3','=2+3','5'); await h.formula(page,'D4','=6/2','3');});
    ''')
    for axis,at,action,shift in [('row','2','Insert 1 row above','B3'),('column','B','Insert 1 column left','C2')]:
        s('REQ-3-2-2','undo/redo '+axis+' structure restores numeric rule ranges and last visible values',f'''
        await h.blank(page); await h.edit(page,'B2','50'); await h.validation(page,'B2','B2'); await h.structure(page,{json.dumps(axis)},{json.dumps(at)},{json.dumps(action)});
        await h.values(page,{{B2:'',{json.dumps(shift)}:'50'}}); await h.button(page,'Undo').click(); await h.values(page,{{B2:'50',{json.dumps(shift)}:''}});
        await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{{B2:'50'}});
        await h.button(page,'Redo').click(); await h.persisted(page,()=>h.values(page,{{B2:'',{json.dumps(shift)}:'50'}})); await h.edit(page,{json.dumps(shift)},'101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{{{json.dumps(shift)}:'50'}});
        ''')
    s('REQ-3-2-2','undo makes deleted pivot source fields valid again and preserves last result',r'''
    await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.button(page,'Undo').click(); await h.values(page,{B1:'Sales',B2:'10',C1:'Status'});
    await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click(); await h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'});
    // Refresh may itself create a new history operation; validate the restored
    // source/result state after refresh without assuming how history counts it.
    await h.persisted(page,()=>h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'})); await h.tab(page,'Sheet1').click(); await h.values(page,{B1:'Sales',B2:'10',B3:'20',B4:'30'});
    ''')
    s('REQ-3-2-2','undo state persists after reload and cannot modify a different saved workbook',r'''
    await h.blank(page); const otherName=h.unique(); await h.renameWorkbook(page,otherName); await h.edit(page,'A1','other-workbook');
    await h.blank(page); const name=h.unique(); await h.renameWorkbook(page,name); await h.edit(page,'A1','initial'); await h.edit(page,'A1','changed'); await h.button(page,'Undo').click();
    await h.persisted(page,()=>h.values(page,{A1:'initial'})); await h.reopen(page,otherName); await h.values(page,{A1:'other-workbook'}); await h.reopen(page,name); await h.values(page,{A1:'initial'});
    ''')
    s('REQ-4-1-1','MAX ignores blank cells rather than using zero when every numeric input is negative',r'''
    await h.blank(page); await h.edit(page,'A1','-20'); await h.edit(page,'A3','-10'); await h.edit(page,'A4','text'); await h.edit(page,'B1','=mAx(A1:A4)');
    await h.persisted(page,()=>h.formula(page,'B1','=mAx(A1:A4)','-10'));
    ''')
    s('REQ-4-2-1','successful range move recalculates formulas depending on target values in dependency order',r'''
    await h.blank(page); await h.paste(page,'A1','3\t4'); await h.edit(page,'C3','1'); await h.edit(page,'D3','2'); await h.edit(page,'F3','=C3+D3'); await h.edit(page,'G3','=F3*2');
    await h.range(page,'A1','B1'); await page.keyboard.press('Control+x'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+v');
    await h.persisted(page,async()=>{await h.values(page,{A1:'',B1:'',C3:'3',D3:'4'});await h.formula(page,'F3','=C3+D3','7');await h.formula(page,'G3','=F3*2','14');});
    ''')
    s('REQ-4-2-1','row and column movement recalculates direct/transitive formulas without changing another sheet',r'''
    await h.blank(page); await h.edit(page,'A2','5'); await h.edit(page,'B2','=A2*2'); await h.edit(page,'C2','=B2+1'); await h.button(page,'Add worksheet').click(); await h.edit(page,'A2','7'); await h.edit(page,'B2','=A2*2'); await h.edit(page,'C2','=B2+1');
    await h.tab(page,'Sheet1').click(); await h.structure(page,'row','2','Insert 1 row above'); await h.formula(page,'B3','=A3*2','10'); await h.formula(page,'C3','=B3+1','11'); await h.structure(page,'column','A','Insert 1 column left');
    await h.formula(page,'C3','=B3*2','10'); await h.formula(page,'D3','=C3+1','11'); await h.edit(page,'B3','9'); await h.persisted(page,async()=>{await h.formula(page,'C3','=B3*2','18');await h.formula(page,'D3','=C3+1','19');});
    await h.tab(page,'Sheet2').click(); await h.formula(page,'B2','=A2*2','14'); await h.formula(page,'C2','=B2+1','15');
    ''')
    s('REQ-4-2-2','a malformed formula does not block unrelated recalculation and fixing it recovers dependents',r'''
    await h.blank(page); await h.edit(page,'A1','2'); await h.edit(page,'B1','=1+'); await h.edit(page,'C1','=A1*3'); await h.edit(page,'D1','=B1+1');
    await h.edit(page,'A1','4'); await h.formula(page,'B1','=1+','#ERROR!'); await h.formula(page,'C1','=A1*3','12'); await h.edit(page,'B1','=A1+2');
    await h.persisted(page,async()=>{await h.formula(page,'B1','=A1+2','6');await h.formula(page,'C1','=A1*3','12');await h.formula(page,'D1','=B1+1','7');});
    ''')
    s('REQ-5-1-1','date keys sort chronologically with stable equal keys and intact full records',r'''
    // Valid ISO date-times with offsets distinguish chronology from text order.
    await h.blank(page); await h.paste(page,'A1','Date\tRecord\tAmount\n2026-01-01T23:30:00Z\tlate\t1\n2026-01-01T23:00:00Z\tfirst-equal\t2\n2026-01-01T23:00:00Z\tsecond-equal\t3\n2026-01-02T00:30:00+02:00\tearly\t4');
    await h.range(page,'A1','C5'); await h.data(page,'Sort range'); const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await h.choose(dialog,'Sort by','Date'); await h.choose(dialog,'Order','Ascending'); await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check(); await h.button(dialog,'Sort').click();
    await h.persisted(page,()=>h.values(page,{A1:'Date',B1:'Record',C1:'Amount',A2:'2026-01-02T00:30:00+02:00',B2:'early',C2:'4',A3:'2026-01-01T23:00:00Z',B3:'first-equal',C3:'2',A4:'2026-01-01T23:00:00Z',B4:'second-equal',C4:'3',A5:'2026-01-01T23:30:00Z',B5:'late',C5:'1'}));
    ''')
    s('REQ-5-1-1','sorting moves formulas with records, adjusts their original references, and preserves validation/filter behavior',r'''
    await h.sourceData(page); await h.edit(page,'D1','Double'); await h.edit(page,'D2','=B2*2'); await h.edit(page,'D3','=B3*2'); await h.edit(page,'D4','=B4*2'); await h.validation(page,'B2','B4');
    await h.range(page,'A1','D4'); await h.data(page,'Create filter'); await h.condition(page,'Sales','Greater than','15'); await h.range(page,'A1','D4'); await h.data(page,'Sort range');
    const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await h.choose(dialog,'Sort by','Sales'); await h.choose(dialog,'Order','Descending'); await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check(); await h.button(dialog,'Sort').click();
    await h.persisted(page,async()=>{await h.values(page,{A2:'East',B2:'30',C2:'Closed',A3:'North',B3:'20',C3:'Closed'});await h.visibleRows(page,['A2','A3'],['A4']);await h.formula(page,'D2','=B2*2','60');await h.formula(page,'D3','=B3*2','40');});
    await h.data(page,'Clear filter'); await h.formula(page,'D4','=B4*2','20'); await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'30',D2:'60'});
    ''')
    for condition,value,visible,hidden in [
        ('Before','2026-01-01T23:00:00Z',['A2'],['A3','A4']),
        ('Is empty',None,['A4'],['A2','A3']),
        ('Is not empty',None,['A2','A3'],['A4'])]:
        s('REQ-5-1-2','condition '+condition+' persists exactly the matching rows and clearing restores originals',f'''
        await h.blank(page); await h.paste(page,'A1','Date\\tRecord\\n2026-01-02T00:30:00+02:00\\tearly\\n2026-01-01T23:30:00Z\\tlate\\n\\tempty'); await h.range(page,'A1','B4'); await h.data(page,'Create filter');
        await h.condition(page,'Date',{json.dumps(condition)},{json.dumps(value) if value is not None else 'undefined'}); await h.persisted(page,async()=>{{await h.filterHeaders(page,{{A1:'Date',B1:'Record'}});await h.visibleRows(page,{json.dumps(visible)},{json.dumps(hidden)});}});
        await h.data(page,'Clear filter'); await h.persisted(page,async()=>{{await h.visibleRows(page,['A2','A3','A4'],[]);await h.values(page,{{A1:'Date',B1:'Record',A2:'2026-01-02T00:30:00+02:00',B2:'early',A3:'2026-01-01T23:30:00Z',B3:'late',A4:'',B4:'empty'}});}});
        ''')
    s('REQ-5-1-2','value filtering is scoped to the selected region and clearing preserves formula and validation behavior',r'''
    await h.blank(page); await h.paste(page,'B2','Region\tSales\tStatus\nEast\t10\tOpen\nNorth\t20\tClosed\nEast\t30\tClosed'); await h.edit(page,'A1','outside-origin'); await h.edit(page,'B6','outside-next-row'); await h.edit(page,'E4','outside-next-column'); await h.edit(page,'F3','=C3*2'); await h.validation(page,'C3','C5');
    await h.range(page,'B2','D5'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.persisted(page,()=>h.visibleRows(page,['B3','B5','B6'],['B4']));
    expect(h.parseCSV(await h.csv(page))).toEqual([['outside-origin','','','','',''],['','Region','Sales','Status','',''],['','East','10','Open','','20'],['','North','20','Closed','outside-next-column',''],['','East','30','Closed','',''],['','outside-next-row','','','','']]);
    await h.data(page,'Clear filter'); await h.persisted(page,async()=>{await h.values(page,{A1:'outside-origin',B3:'East',C3:'10',B4:'North',C4:'20',B5:'East',C5:'30',B6:'outside-next-row',E4:'outside-next-column'});await h.formula(page,'F3','=C3*2','20');});
    await h.edit(page,'C3','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{C3:'10',F3:'20'});
    ''')
    s('REQ-5-1-2','filtered-out source rows still contribute to pivot summary after reopening',r'''
    await h.sourceData(page); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.visibleRows(page,['A2','A4'],['A3']);
    await h.pivot(page); await h.persisted(page,()=>h.values(page,{A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}));
    await h.tab(page,'Sheet1').click(); await h.visibleRows(page,['A2','A4'],['A3']); await h.values(page,{B2:'10',B3:'20',B4:'30'});
    ''')
    s('REQ-5-2-1','a reopened dropdown rule shows saved trimmed values and Delete rule removes dropdown constraint',r'''
    await h.blank(page); await h.edit(page,'A1','Open'); await h.validation(page,'A1','A2','Dropdown'); await page.reload(); await h.cell(page,'A1').click(); await h.data(page,'Data validation');
    const dialog=page.getByRole('dialog',{name:'Data validation',exact:true}); await h.chosen(dialog,'Rule type','Dropdown'); const saved=await h.field(dialog,'Allowed values').inputValue(); expect(saved.split(',').map(item=>item.trim())).toEqual(['Open','Closed']); await expect(h.button(dialog,'Delete rule')).toBeVisible();
    await h.button(dialog,'Delete rule').click(); await expect(dialog).toBeHidden(); await h.values(page,{A1:'Open'}); await expect(h.button(page,'Open dropdown for A1')).toHaveCount(0); await h.edit(page,'A1','custom');
    await h.persisted(page,()=>h.values(page,{A1:'custom'})); await h.edit(page,'A2','another-custom'); await h.values(page,{A2:'another-custom'});
    ''')
    s('REQ-5-2-1','numeric rule uses inclusive custom bounds and specific rejection text for grid and formula-bar entry',r'''
    await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.numericRule(page,'A1','A2','10','20'); await page.reload(); await h.edit(page,'A1','20'); await h.edit(page,'A1','10'); await h.edit(page,'A2','10'); await h.edit(page,'A2','20');
    await h.edit(page,'A1','9',true); await expect(h.text(page,'Please enter a number between 10 and 20').first()).toBeVisible(); await h.ordinary(page,{A1:'10',A2:'20'});
    await h.edit(page,'A2','21'); await expect(h.text(page,'Please enter a number between 10 and 20').first()).toBeVisible(); await h.persisted(page,()=>h.ordinary(page,{A1:'10',A2:'20'}));
    ''')
    s('REQ-5-2-1','modifying a numeric rule immediately changes its persisted limits while preserving existing values',r'''
    await h.blank(page); await h.edit(page,'A1','50'); await h.numericRule(page,'A1','A2','0','100'); await page.reload(); await h.cell(page,'A1').click(); await h.data(page,'Data validation');
    const dialog=page.getByRole('dialog',{name:'Data validation',exact:true}); await h.chosen(dialog,'Rule type','Number range'); await expect(h.field(dialog,'Minimum')).toHaveValue('0'); await expect(h.field(dialog,'Maximum')).toHaveValue('100'); await expect(h.button(dialog,'Delete rule')).toBeVisible();
    await h.field(dialog,'Minimum').fill('40'); await h.field(dialog,'Maximum').fill('60'); await h.button(dialog,'Save').click(); await expect(dialog).toBeHidden(); await h.values(page,{A1:'50'}); await h.edit(page,'A1','60');
    await page.reload(); await h.edit(page,'A1','61'); await expect(h.text(page,'Please enter a number between 40 and 60').first()).toBeVisible(); await h.values(page,{A1:'60'});
    await test.step('Changing limits preserves the entire original rule range',async()=>{
      await h.edit(page,'A2','61'); await expect(h.text(page,'Please enter a number between 40 and 60').first()).toBeVisible();
      await h.values(page,{A1:'60',A2:''}); await h.edit(page,'A2','60');
      await h.persisted(page,()=>h.values(page,{A1:'60',A2:'60'}));
    });
    ''')
    for method,expected in [('SUM',{'A1':'Region','B1':'SUM of Sales','A2':'East','B2':'10','A3':'North','A4':'Grand Total','B4':'10'}),('AVERAGE',{'A1':'Region','B1':'AVERAGE of Sales','A2':'East','B2':'10','A4':'Grand Total','B4':'10'})]:
        # An empty group's AVERAGE display is not specified. Assert its name,
        # numeric groups and grand total, leaving only that display undefined.
        s('REQ-5-3-1',method+' ignores nonnumeric and blank value records without treating blanks as zero',f'''
        await h.sourceData(page); await h.edit(page,'B3','text'); await h.edit(page,'B4',''); await h.pivot(page,{json.dumps(method)}); await h.persisted(page,()=>h.values(page,{{...{json.dumps(expected)},A3:'North'}}));
        await h.tab(page,'Sheet1').click(); await h.values(page,{{B2:'10',B3:'text',B4:''}});
        ''')
    s('REQ-5-3-1','column SUM aggregates numeric records in appearance order with exact row and column grand totals',r'''
    await h.sourceData(page); await h.edit(page,'A2','North'); await h.edit(page,'A3','East'); await h.edit(page,'A4','North'); await h.edit(page,'C2','Closed'); await h.edit(page,'C3','Open'); await h.edit(page,'C4','Open'); await h.pivot(page,'SUM','Status');
    await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'Closed',C1:'Open',D1:'Grand Total',A2:'North',B2:'10',C2:'30',D2:'40',A3:'East',C3:'20',D3:'20',A4:'Grand Total',B4:'10',C4:'50',D4:'60'}));
    ''')
    s('REQ-5-3-1','column AVERAGE computes grand totals from source records rather than averaging group averages',r'''
    await h.sourceData(page); await h.edit(page,'B2','10'); await h.edit(page,'B3','50'); await h.edit(page,'B4','30'); await h.pivot(page,'AVERAGE','Status');
    await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'Open',C1:'Closed',D1:'Grand Total',A2:'East',B2:'10',C2:'30',D2:'20',A3:'North',C3:'50',D3:'50',A4:'Grand Total',B4:'10',C4:'40',D4:'30'}));
    ''')
    s('REQ-5-3-1','pivot naming reuses the first unused PivotN after a result sheet is deleted',r'''
    await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.pivot(page,'COUNT'); await expect(h.tab(page,'Pivot2')).toHaveAttribute('aria-selected','true');
    await h.sheetMenu(page,'Pivot1','Delete'); await h.button(page.getByRole('dialog',{name:'Delete worksheet',exact:true}),'Delete worksheet').click(); await h.tab(page,'Sheet1').click(); await h.pivot(page,'AVERAGE');
    await h.persisted(page,async()=>{await h.tabOrder(page,['Sheet1','Pivot2','Pivot1']);await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');await h.values(page,{B1:'AVERAGE of Sales',B2:'20',B3:'20',B4:'20'});});
    await h.tab(page,'Pivot2').click(); await h.values(page,{B1:'COUNT of Sales',B2:'2',B3:'1',B4:'3'});
    ''')
    for method in ['SUM','AVERAGE']:
        s('REQ-5-3-1',method+' rejects a value field with no numbers and preserves both complete worksheets after reload',f'''
        await h.sourceData(page); await h.pivot(page); const editor=page.getByRole('region',{{name:'Pivot table editor',exact:true}}); await h.choose(editor,'Values','Status'); await h.choose(editor,'Summarize by',{json.dumps(method)}); await h.button(editor,'Apply').click();
        await expect(h.text(page,'Value field requires numeric values').first()).toBeVisible(); await h.persisted(page,()=>h.values(page,{{A1:'Region',B1:'SUM of Sales',A2:'East',B2:'40',A3:'North',B3:'20',A4:'Grand Total',B4:'60'}}));
        await h.tab(page,'Sheet1').click(); await h.values(page,{{A1:'Region',B1:'Sales',C1:'Status',A2:'East',B2:'10',C2:'Open',A3:'North',B3:'20',C3:'Closed',A4:'East',B4:'30',C4:'Closed'}});
        ''')
    s('REQ-5-3-1','refresh replacement removes obsolete groups and totals after source records change',r'''
    await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.edit(page,'A3','East'); await h.edit(page,'B3','5'); await h.tab(page,'Pivot1').click(); await h.values(page,{A3:'North',B4:'60'});
    await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'SUM of Sales',A2:'East',B2:'45',A3:'Grand Total',B3:'45',A4:'',B4:''}));
    await h.tab(page,'Sheet1').click(); await h.values(page,{A2:'East',B2:'10',A3:'East',B3:'5',A4:'East',B4:'30'});
    ''')
    s('REQ-5-2-1','dropdown validation rejects grid and whole clipboard/move rectangles without clearing any source',r'''
    await h.blank(page); await h.paste(page,'A1','Open\nClosed'); await h.validation(page,'A1','A2','Dropdown'); await page.reload(); await h.edit(page,'A1','invalid',true);
    await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{A1:'Open',A2:'Closed'});
    await h.paste(page,'A1','Closed\ninvalid'); await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.values(page,{A1:'Open',A2:'Closed'});
    await h.paste(page,'C1','Closed\ninvalid'); await h.range(page,'C1','C2'); await page.keyboard.press('Control+x'); await h.cell(page,'A1').click(); await page.keyboard.press('Control+v');
    await expect(page.getByText(/^Please select one of the following values: Open,\s*Closed$/).first()).toBeVisible(); await h.persisted(page,()=>h.values(page,{A1:'Open',A2:'Closed',C1:'Closed',C2:'invalid'}));
    ''')
    s('REQ-5-3-1','a deleted pivot field can be reselected and successful apply replaces the saved error-state result',r'''
    await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click();
    await expect(h.text(page,'Pivot field is no longer available. Select a new field.').first()).toBeVisible(); await h.values(page,{B1:'SUM of Sales',B2:'40',B4:'60'}); const editor=page.getByRole('region',{name:'Pivot table editor',exact:true});
    await h.choose(editor,'Rows','Region'); await h.choose(editor,'Values','Status'); await h.choose(editor,'Summarize by','COUNT'); await h.button(editor,'Apply').click();
    await h.persisted(page,async()=>{
      await expect(h.text(page,'Pivot field is no longer available. Select a new field.')).toHaveCount(0);
      await h.values(page,{A1:'Region',B1:'COUNT of Status',A2:'East',B2:'2',A3:'North',B3:'1',A4:'Grand Total',B4:'3'});
    }); await h.tab(page,'Sheet1').click(); await h.values(page,{A1:'Region',B1:'Status',A2:'East',B2:'Open',A3:'North',B3:'Closed',A4:'East',B4:'Closed'});
    ''')
