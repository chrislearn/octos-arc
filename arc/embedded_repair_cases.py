"""Independent requirement regressions for defects discovered in local execution."""
def register(s):
    # Filled anchors distinguish above/below and left/right. Clipboard setup
    # belongs to a later capability, so the existing partition/witness pipeline
    # places these regressions in the exportable REQ-3-1-2 context gate.
    s('REQ-2-2-1', 'insert below a populated anchor keeps the anchor row', r'''
    await h.blank(page);
    await test.step('Populate the anchor and the following complete record',async()=>{
      await h.paste(page,'A1','anchor\t10\nnext\t20');
      await h.values(page,{A1:'anchor',B1:'10',A2:'next',B2:'20'});
    });
    await h.structure(page,'row','1','Insert 1 row below');
    await test.step('The blank row follows the unchanged anchor, including after reload',async()=>{
      await h.persisted(page,()=>h.values(page,{A1:'anchor',B1:'10',A2:'',B2:'',A3:'next',B3:'20'}));
    });
    ''',requires=['REQ-2-2-1','REQ-1-2-1','REQ-3-1-2'])
    s('REQ-2-2-2', 'insert right of a populated anchor keeps the anchor column', r'''
    await h.blank(page);
    await test.step('Populate the anchor and the following complete column',async()=>{
      await h.paste(page,'A1','anchor\tnext\noutside-anchor\toutside-next');
      await h.values(page,{A1:'anchor',B1:'next',A2:'outside-anchor',B2:'outside-next'});
    });
    await h.structure(page,'column','A','Insert 1 column right');
    await test.step('The blank column follows the unchanged anchor, including after reload',async()=>{
      await h.persisted(page,()=>h.values(page,{A1:'anchor',B1:'',C1:'next',A2:'outside-anchor',B2:'',C2:'outside-next'}));
    });
    ''',requires=['REQ-2-2-2','REQ-1-2-1','REQ-3-1-2'])
    s('REQ-3-1-1', 'failed cell save restores formula-bar input and keeps persisted cell; retry succeeds', r'''

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
    s('REQ-4-2-2', 'a dependent formula preserves a malformed source error and recovers', r'''
    await h.blank(page);
    await h.edit(page,'A1','=1+'); await h.edit(page,'B1','=A1+1');
    await test.step('The source and its dependent preserve the malformed-expression error',async()=>{
      await h.persisted(page,()=>h.values(page,{A1:'#ERROR!',B1:'#ERROR!'}));
    });
    await h.edit(page,'A1','4');
    await test.step('Repairing the source recalculates and persists the dependent',async()=>{
      await h.persisted(page,()=>h.values(page,{A1:'4',B1:'5'}));
    });
    ''',requires=['REQ-4-2-2','REQ-4-1-1','REQ-3-1-1','REQ-1-2-1'])
    s('REQ-5-3-1', 'undo and redo restore structural changes together with another sheet pivot source', r'''
    await h.sourceData(page); await h.pivot(page);
    await h.tab(page,'Sheet1').click(); await h.structure(page,'row','1','Insert 1 row above'); await h.values(page,{A1:'',A2:'Region',B3:'10'});
    await h.button(page,'Undo').click(); await h.values(page,{A1:'Region',B2:'10'});
    // Observe the restored pivot before Redo. A successful Refresh may itself
    // create a history operation and legitimately discard the redo branch.
    await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'40',B3:'20',B4:'60'});
    await h.tab(page,'Sheet1').click(); await h.button(page,'Redo').click(); await h.values(page,{A1:'',A2:'Region',B3:'10'});
    await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click();
    await h.persisted(page,()=>h.values(page,{B2:'40',B3:'20',B4:'60'}));
    ''',requires=['REQ-5-3-1','REQ-3-2-2','REQ-2-1-2','REQ-2-2-1','REQ-3-1-2','REQ-3-1-3','REQ-2-1-1','REQ-1-2-1'])
