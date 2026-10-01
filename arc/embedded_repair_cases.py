"""Independent requirement regressions for defects discovered in local execution."""
def register(s):
    s('REQ-3-1-1', 'failed cell save restores formula-bar input and keeps persisted cell; retry succeeds', r'''
  await h.blank(page); await h.edit(page,'A1','original'); await h.values(page,{A1:'original'});
  const alerts=page.locator('[role="alert"]:visible').filter({hasText:/\S/}); await expect(alerts).toHaveCount(0);
    let rejectedAttempts=0, retryAttempts=0; const rejected=h.unique(), retried=h.unique(); const origin=new URL(page.url()).origin;
    // Inject the failed value's actual write, independently of API route or
    // whether the app persists one cell, a worksheet, or the whole workbook.
    await page.route('**/*',async route=>{
      const request=route.request(); const body=request.postData()||'';
      if(new URL(request.url()).origin===origin && ['PATCH','PUT','POST'].includes(request.method())){
        if(body.includes(retried)) retryAttempts++;
        else if(body.includes(rejected)){ rejectedAttempts++; await route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:'Unable to save cell'})}); return; }
      }
      await route.continue();
    });
  await h.edit(page,'A1',rejected); await expect(alerts.first()).toBeVisible();
    await h.values(page,{A1:'original'}); await expect(h.field(page,'Formula bar')).toHaveValue('original'); expect(rejectedAttempts).toBeGreaterThan(0);
    await page.reload(); await h.values(page,{A1:'original'}); await h.edit(page,'A1',retried);
    await h.persisted(page,()=>h.values(page,{A1:retried})); expect(retryAttempts).toBeGreaterThan(0);
    ''')
    s('REQ-3-2-1', 'overlapping cut preserves the complete target and only clears the uncovered source', r'''
    await h.blank(page); await h.paste(page,'A1','first\tsecond\tthird'); await h.values(page,{A1:'first',B1:'second',C1:'third'});
    await h.range(page,'A1','B1'); await page.keyboard.press('Control+x'); await h.cell(page,'B1').click(); await page.keyboard.press('Control+v');
    await h.persisted(page,()=>h.values(page,{A1:'',B1:'first',C1:'second'}));
    ''', requires=['REQ-3-2-1','REQ-3-1-2','REQ-3-1-3','REQ-1-2-1'])
    s('REQ-3-2-1', 'external clipboard replacement after cut pastes new text and preserves the cut source', r'''
    await h.blank(page); await h.paste(page,'A1','original\tneighbor'); await h.values(page,{A1:'original',B1:'neighbor'});
    await h.cell(page,'A1').click(); await page.keyboard.press('Control+x'); await h.paste(page,'C1','external',true);
    await h.persisted(page,()=>h.values(page,{A1:'original',B1:'neighbor',C1:'external'}));
    ''',requires=['REQ-3-2-1','REQ-3-1-2','REQ-1-2-1'])
    s('REQ-4-2-2', 'aggregate formula keeps a stable source error and recalculates after repair', r'''
    await h.blank(page); await h.edit(page,'A1','=1/0'); await h.edit(page,'A2','5'); await h.edit(page,'B1','=SUM(A1:A2)');
    await h.persisted(page,()=>h.formula(page,'B1','=SUM(A1:A2)','#DIV/0!'));
    await h.edit(page,'A1','15'); await h.persisted(page,()=>h.formula(page,'B1','=SUM(A1:A2)','20'));
    ''',requires=['REQ-4-2-2','REQ-4-1-1','REQ-3-1-1','REQ-1-2-1'])
    s('REQ-5-3-1', 'undo and redo restore structural changes together with another sheet pivot source', r'''
    await h.sourceData(page); await h.pivot(page);
    await h.tab(page,'Sheet1').click(); await h.structure(page,'row','1','Insert 1 row above'); await h.values(page,{A1:'',A2:'Region',B3:'10'});
    await h.button(page,'Undo').click(); await h.values(page,{A1:'Region',B2:'10'});
    await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click(); await h.values(page,{B2:'40',B3:'20',B4:'60'});
    await h.tab(page,'Sheet1').click(); await h.button(page,'Redo').click(); await h.values(page,{A1:'',A2:'Region',B3:'10'});
    await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click();
    await h.persisted(page,()=>h.values(page,{B2:'40',B3:'20',B4:'60'}));
    ''',requires=['REQ-5-3-1','REQ-3-2-2','REQ-2-1-2','REQ-2-2-1','REQ-3-1-2','REQ-3-1-3','REQ-2-1-1','REQ-1-2-1'])
