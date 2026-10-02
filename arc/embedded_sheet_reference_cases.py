"""Reference and typed-key boundaries found in the b0c8de00a1c6 review."""


def register(s):
    for order in ('Ascending', 'Descending'):
        s('REQ-5-1-1', f'audit regression: {order} keeps numerically equal spellings in original record order', r'''
        await h.blank(page);await h.paste(page,'A1','Key\tRecord\n2\tfirst\n02\tsecond\n2.0\tthird');
        await h.values(page,{A2:'2',B2:'first',A3:'02',B3:'second',A4:'2.0',B4:'third'});
        await h.range(page,'A1','B4');await h.data(page,'Sort range');const dialog=page.getByRole('dialog',{name:'Sort range',exact:true});
        await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check();
        await h.choose(dialog,'Sort by','Key');await h.choose(dialog,'Order','ORDER');await h.button(dialog,'Sort').click();
        await h.persisted(page,()=>h.values(page,{A1:'Key',B1:'Record',A2:'2',B2:'first',A3:'02',B3:'second',A4:'2.0',B4:'third'}));
        '''.replace('ORDER', order))

    s('REQ-4-1-1', 'audit regression: insert right changes only references at or after the actual insertion', r'''
    await h.blank(page);await h.edit(page,'A1','10');await h.edit(page,'B1','20');await h.edit(page,'D1','=A1+B1');
    await h.formula(page,'D1','=A1+B1','30');await h.structure(page,'column','A','Insert 1 column right');
    await h.persisted(page,async()=>{await h.values(page,{A1:'10',B1:'',C1:'20'});await h.formula(page,'E1','=A1+C1','30');});
    ''')
    s('REQ-4-1-1', 'audit regression: insert below preserves references above the actual insertion and all column axes', r'''
    await h.blank(page);await h.edit(page,'A1','10');await h.edit(page,'A2','20');await h.edit(page,'B4','=A1+A2');
    await h.formula(page,'B4','=A1+A2','30');await h.structure(page,'row','1','Insert 1 row below');
    await h.persisted(page,async()=>{await h.values(page,{A1:'10',A2:'',A3:'20'});await h.formula(page,'B5','=A1+A3','30');});
    ''')

    for source, target, expression, adjusted, value in (
        ('D4', 'E5', '=$A1+A$1+$A$1+A1', '=$A2+B$1+$A$1+B2', '8'),
        ('E5', 'D4', '=$B2+B$2+$B$2+B2', '=$B1+A$2+$B$2+A1', '28'),
    ):
        s('REQ-4-1-2', f'audit regression: mixed absolute axes copy from {source} to {target} independently', f'''
        await h.blank(page);await h.paste(page,'A1','2\\t3\\n5\\t7');await h.edit(page,'{source}','{expression}');
        await h.formula(page,'{source}','{expression}','{value}');await h.cell(page,'{source}').click();await page.keyboard.press('Control+c');
        await h.cell(page,'{target}').click();await page.keyboard.press('Control+v');
        await h.persisted(page,async()=>{{await h.formula(page,'{source}','{expression}','{value}');await h.formula(page,'{target}','{adjusted}','17');await h.values(page,{{A1:'2',B1:'3',A2:'5',B2:'7'}});}});
        ''')

    s('REQ-4-1-2', 'audit regression: formula copy crosses Z to AA without changing absolute columns', r'''
    await page.goto('/');await h.button(page,'Import CSV').click();const name=h.unique();
    const dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
    const row=Array.from({length:28},(_,i)=>i===25?'4':i===26?'9':'').join(',');
    await h.field(dialog,'CSV file').setInputFiles({name:`${name}.csv`,mimeType:'text/csv',buffer:Buffer.from(row)});
    await h.button(dialog,'Confirm import').click();await expect(h.text(page,name).first()).toBeVisible();
    await h.edit(page,'Z2','=Z1+$Z$1');await h.formula(page,'Z2','=Z1+$Z$1','8');
    await h.cell(page,'Z2').click();await page.keyboard.press('Control+c');await h.cell(page,'AA2').click();await page.keyboard.press('Control+v');
    await h.persisted(page,async()=>{await h.formula(page,'Z2','=Z1+$Z$1','8');await h.formula(page,'AA2','=AA1+$Z$1','13');await h.values(page,{Z1:'4',AA1:'9'});});
    ''', requires=['REQ-4-1-2', 'REQ-1-3-1'])

    s('REQ-5-3-1', 'audit regression: COUNT retains blank row groups and all source records in totals', r'''
    await h.blank(page);await h.paste(page,'A1','Region\tSales\tStatus\n\t10\tOpen\nEast\t20\tOpen\n\t30\tClosed');
    await h.values(page,{A2:'',A3:'East',A4:'',B2:'10',B3:'20',B4:'30'});await h.pivot(page,'COUNT');
    await h.persisted(page,()=>h.values(page,{A1:'Region',B1:'COUNT of Sales',A2:'',B2:'2',A3:'East',B3:'1',A4:'Grand Total',B4:'3'}));
    await h.tab(page,'Sheet1').click();await h.values(page,{A2:'',A3:'East',A4:'',B2:'10',B3:'20',B4:'30'});
    ''')
