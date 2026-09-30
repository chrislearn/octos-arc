"""Foundation-only Sheet gates; richer cross-feature cases remain mandatory."""

def register(s):
    s('REQ-1-3-2', 'export imported plain CSV preserves ordered escaping and active worksheet', r'''
    await page.goto('/'); await h.button(page, 'Import CSV').click();
    const name=h.unique(), dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
    await h.field(dialog,'CSV file').setInputFiles({name:`${name}.csv`,mimeType:'text/csv',buffer:Buffer.from('名称,备注,空\r\n中文,"逗号,文本",\r\nEnglish,"双""引号\n下一行",007','utf8')});
    await h.button(dialog,'Confirm import').click(); await expect(h.text(page,name).first()).toBeVisible();
    expect(h.parseCSV(await h.csv(page))).toEqual([['名称','备注','空'],['中文','逗号,文本',''],['English','双"引号\n下一行','007']]);
    await h.persisted(page,async()=>{ await expect(h.tab(page,'Sheet1')).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:'名称',B2:'逗号,文本',B3:'双"引号\n下一行',C3:'007'}); });
    ''', requires=['REQ-1-3-2','REQ-1-3-1'])
    s('REQ-2-1-1', 'append blank worksheets in order and activate each new A1', r'''
    await h.blank(page);
    for(const name of ['Sheet2','Sheet3']) { await h.button(page,'Add worksheet').click(); await expect(h.tab(page,name)).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:''}); await expect(h.cell(page,'A1')).toHaveAttribute('aria-selected','true'); }
    await h.persisted(page,async()=>{ await h.tabOrder(page,['Sheet1','Sheet2','Sheet3']); await expect(h.tab(page,'Sheet3')).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:''}); });
    ''')
    s('REQ-2-1-3', 'single worksheet rename rejects empty input then trims and persists', r'''
    await h.blank(page); await h.sheetMenu(page,'Sheet1','Rename');
    const dialog=page.getByRole('dialog',{name:'Rename worksheet',exact:true}); await expect(h.field(dialog,'Worksheet name')).toHaveValue('Sheet1');
    await h.field(dialog,'Worksheet name').fill('  '); await h.button(dialog,'Save').click(); await expect(h.text(page,'Worksheet name cannot be empty').first()).toBeVisible();
    await page.reload(); await expect(h.tab(page,'Sheet1')).toBeVisible(); await h.sheetMenu(page,'Sheet1','Rename');
    await h.field(page,'Worksheet name').fill('  Sales  '); await h.button(page.getByRole('dialog',{name:'Rename worksheet',exact:true}),'Save').click();
    await h.persisted(page,async()=>{ await h.tabOrder(page,['Sales']); await expect(h.tab(page,'Sales')).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:''}); });
    ''')
    s('REQ-2-2-1', 'seeded row insertion and deletion move complete records without editing prerequisites', r'''
    await page.goto('/'); await page.getByRole('link',{name:'Row operations seed',exact:true}).click();
    const address=page.url();
    await h.values(page,{A1:'Label',B1:'Value',A2:'first',B2:'10',A3:'second',B3:'20'});
    await h.structure(page,'row','2','Insert 1 row above');
    await h.persisted(page,()=>h.values(page,{A1:'Label',B1:'Value',A2:'',B2:'',A3:'first',B3:'10',A4:'second',B4:'20'}));
    await h.structure(page,'row','3','Delete row');
    await h.persisted(page,()=>h.values(page,{A1:'Label',B1:'Value',A2:'',B2:'',A3:'second',B3:'20',A4:'',B4:''}));
    await test.step('Reopen the same saved workbook from its home entry',async()=>{
      await h.reopen(page,'Row operations seed'); await expect(page).toHaveURL(address);
      await h.values(page,{A1:'Label',B1:'Value',A2:'',B2:'',A3:'second',B3:'20',A4:'',B4:''});
    });
    ''', fixture='row-node', requires=['REQ-2-2-1','REQ-1-1-1'])
    s('REQ-2-2-2', 'seeded column insertion and deletion move complete records without editing prerequisites', r'''
    await page.goto('/'); await page.getByRole('link',{name:'Column operations seed',exact:true}).click();
    const address=page.url();
    await h.values(page,{A1:'first',A2:'alpha',B1:'second',B2:'beta',C1:'third',C2:'gamma'});
    await h.structure(page,'column','B','Insert 1 column left');
    await h.persisted(page,()=>h.values(page,{A1:'first',A2:'alpha',B1:'',B2:'',C1:'second',C2:'beta',D1:'third',D2:'gamma'}));
    await h.structure(page,'column','C','Delete column');
    await h.persisted(page,()=>h.values(page,{A1:'first',A2:'alpha',B1:'',B2:'',C1:'third',C2:'gamma',D1:'',D2:''}));
    await test.step('Reopen the same saved workbook from its home entry',async()=>{
      await h.reopen(page,'Column operations seed'); await expect(page).toHaveURL(address);
      await h.values(page,{A1:'first',A2:'alpha',B1:'',B2:'',C1:'third',C2:'gamma',D1:'',D2:''});
    });
    ''', fixture='column-node', requires=['REQ-2-2-2','REQ-1-1-1'])
    s('REQ-3-1-2', 'plain paste clears middle and trailing empty fields and preserves outside cells', r'''
    await h.blank(page); await h.edit(page,'C2','replace'); await h.edit(page,'D3','tail'); await h.edit(page,'E5','outside');
    await h.paste(page,'B2','East\t\t1200\nNorth\t800\t');
    await h.persisted(page,()=>h.values(page,{B2:'East',C2:'',D2:'1200',B3:'North',C3:'800',D3:'',E5:'outside'}));
    ''')
    s('REQ-3-1-3', 'drag replaces and persists the exact rectangular ARIA selection', r'''
    await h.blank(page); await h.range(page,'B2','C3');
    await h.persisted(page,()=>h.selection(page,['B2','C2','B3','C3'],['A1','A2','B1','D3']));
    await h.cell(page,'A1').click(); await h.persisted(page,()=>h.selection(page,['A1'],['B2','C2','B3','C3']));
    ''')
    s('REQ-3-2-1', 'plain copy preserves source and cut clears source only after target paste', r'''
    await h.blank(page); await h.paste(page,'A1','alpha\t1\nbeta\t2'); await h.edit(page,'J10','outside');
    await h.range(page,'A1','B2'); await page.keyboard.press('Control+c'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+v');
    await h.values(page,{A1:'alpha',B1:'1',A2:'beta',B2:'2',C3:'alpha',D3:'1',C4:'beta',D4:'2',J10:'outside'});
    await h.range(page,'A1','B2'); await page.keyboard.press('Control+x'); await h.values(page,{A1:'alpha',B1:'1',A2:'beta',B2:'2'});
    await h.cell(page,'F6').click(); await page.keyboard.press('Control+v');
    await h.persisted(page,()=>h.values(page,{A1:'',B1:'',A2:'',B2:'',C3:'alpha',D3:'1',C4:'beta',D4:'2',F6:'alpha',G6:'1',F7:'beta',G7:'2',J10:'outside'}));
    ''')
