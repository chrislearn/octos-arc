"""Behavior witnesses added after the Sheet requirement/spec audit.

Original requirements remain authoritative. UI-based witnesses are partitioned
by their actual prerequisites and retained in exported node gates.
"""

def register(s):
    for menu in (False, True):
        s('REQ-3-1-2', 'plain text paste preserves significant whitespace and leading zeros through '+('menu' if menu else 'Ctrl+V'), r'''
        await h.blank(page); await h.edit(page,'E5','outside');
        await h.paste(page,'B2','  alpha  beta  \t中文  值 \n007\t tail ',MENU);
        await h.persisted(page,()=>h.ordinary(page,{B2:'  alpha  beta  ',C2:'中文  值 ',B3:'007',C3:' tail ',E5:'outside'}));
        '''.replace('MENU',str(menu).lower()))
    s('REQ-3-2-1', 'copy preserves exact ordinary text in both rectangles after reload', r'''
    await h.blank(page); await h.paste(page,'A1','  alpha  beta  \t007\n中文  值 \t tail '); await h.edit(page,'F6','outside');
    await h.range(page,'A1','B2'); await page.keyboard.press('Control+c'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+v');
    await h.persisted(page,()=>h.ordinary(page,{A1:'  alpha  beta  ',B1:'007',A2:'中文  值 ',B2:' tail ',C3:'  alpha  beta  ',D3:'007',C4:'中文  值 ',D4:' tail ',F6:'outside'}));
    ''')
    s('REQ-4-1-1', 'inline grid formulas commit on Enter and blur and Escape retains the original formula', r'''
    await h.blank(page); await h.edit(page,'A1','2',true); await h.edit(page,'B1','=A1*2',true);
    await h.cell(page,'C1').dblclick(); await h.field(page,'Edit C1').fill('=B1+1'); await h.cell(page,'D1').click();
    await h.cell(page,'B1').dblclick(); await h.field(page,'Edit B1').fill('=A1*99'); await h.field(page,'Edit B1').press('Escape');
    await h.persisted(page,async()=>{await h.formula(page,'B1','=A1*2','4');await h.formula(page,'C1','=B1+1','5');await h.values(page,{A1:'2',D1:''});});
    ''')
    s('REQ-4-1-1', 'two-dimensional aggregate input through grid ignores blanks and nonnumeric text', r'''
    await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'B1','text'); await h.edit(page,'B2','20');
    await h.edit(page,'D1','=sUm(A1:B2)',true); await h.edit(page,'D2','=AVERAGE(A1:B2)',true); await h.edit(page,'D3','=COUNT(A1:B2)',true);
    await h.persisted(page,async()=>{await h.formula(page,'D1','=sUm(A1:B2)','30');await h.formula(page,'D2','=AVERAGE(A1:B2)','15');await h.formula(page,'D3','=COUNT(A1:B2)','2');});
    ''')
    for direction, target, expression, result in [('horizontal','E4','=B1+$A$1','12'),('vertical','D5','=A2+$A$1','16')]:
        s('REQ-4-1-2', direction+' formula copy changes only the relative axis and preserves absolute references', r'''
        await h.blank(page); await h.edit(page,'A1','5'); await h.edit(page,'B1','7'); await h.edit(page,'A2','11'); await h.edit(page,'B2','13'); await h.edit(page,'D4','=A1+$A$1');
        await h.cell(page,'D4').click(); await page.keyboard.press('Control+c'); await h.cell(page,'TARGET').click(); await page.keyboard.press('Control+v');
        await h.persisted(page,async()=>{await h.formula(page,'D4','=A1+$A$1','10');await h.formula(page,'TARGET','EXPRESSION','RESULT');await h.values(page,{A1:'5',B1:'7',A2:'11',B2:'13'});});
        '''.replace('TARGET',target).replace('EXPRESSION',expression).replace('RESULT',result))
    actions={
        'grid': "await h.edit(page,'A1','not-a-number',true);",
        'formula bar': "await h.edit(page,'A1','not-a-number');",
        'paste': "await h.paste(page,'A1','15\\nnot-a-number');",
        'cut': "await h.range(page,'F1','F2'); await page.keyboard.press('Control+x'); await h.cell(page,'A1').click(); await page.keyboard.press('Control+v');",
    }
    for path, action in actions.items():
        s('REQ-5-2-1', 'numeric validation rejects nonnumeric '+path+' without changing targets sources or dependents', r'''
        await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'D1','=SUM(A1:A2)');
        await h.paste(page,'F1','15\nnot-a-number'); await h.numericRule(page,'A1','A2','10','20'); await page.reload();
        ACTION
        await expect(h.text(page,'Please enter a number between 10 and 20').filter({visible:true}).first()).toBeVisible();
        await h.persisted(page,async()=>{await h.ordinary(page,{A1:'10',A2:'20',F1:'15',F2:'not-a-number'});await h.formula(page,'D1','=SUM(A1:A2)','30');});
        '''.replace('ACTION',action))
    s('REQ-5-3-1', 'column pivot reopens all saved field selections and exact results in a later browser session', r'''
    await h.sourceData(page); const name=h.unique(); await h.renameWorkbook(page,name); await h.pivot(page,'COUNT','Status'); const address=page.url();
    const check=async(p:typeof page)=>{
      await h.tabOrder(p,['Sheet1','Pivot1']); await expect(h.tab(p,'Pivot1')).toHaveAttribute('aria-selected','true');
      const editor=p.getByRole('region',{name:'Pivot table editor',exact:true});
      await h.chosen(editor,'Rows','Region'); await h.chosen(editor,'Columns','Status'); await h.chosen(editor,'Values','Sales'); await h.chosen(editor,'Summarize by','COUNT');
      await h.values(p,{A1:'Region',B1:'Open',C1:'Closed',D1:'Grand Total',A2:'East',B2:'1',C2:'1',D2:'2',A3:'North',B3:'0',C3:'1',D3:'1',A4:'Grand Total',B4:'1',C4:'2',D4:'3'});
    };
    await h.persisted(page,()=>check(page)); await h.reopen(page,name); await check(page);
    const later=await browser.newContext(); try{const p=await later.newPage();await p.goto(address);await check(p);}finally{await later.close();}
    ''')
