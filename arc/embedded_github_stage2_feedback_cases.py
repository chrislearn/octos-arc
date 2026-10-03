"""04e112d2 regressions: visible entry, real clipboard effects and source context.

Feedback/highlight checks supplement the contract as UI compatibility witnesses.
Record authors and simultaneous field errors are checked in their proper scope;
legitimate repeated data must not be removed to satisfy a page-wide locator.
"""


def register(g):
    for protocol in ['HTTPS', 'SSH']:
        g('REQ-3-2-3', f'stage2 feedback: {protocol} copy has one persistent confirmation and an unchanged action name', r'''
        await h.repo(page); await page.clock.install();
        const copied=await h.copyClone(page,'PROTOCOL');
        await expect(page.getByText(/copied/i)).toHaveCount(1);
        await expect(page.getByText(/copied/i)).toBeVisible();
        await expect(h.button(page,'Copy clone value')).toBeEnabled();
        await page.clock.fastForward(6000); await expect(page.getByText(/copied/i)).toBeVisible();
        expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(copied);
        await page.keyboard.press('Escape'); await h.button(page,'Code').click();
        await expect(page.getByText(/copied/i)).toHaveCount(0);
        '''.replace('PROTOCOL', protocol))
    g('REQ-3-2-3', 'stage2 feedback: changing protocol clears prior success and copies the newly displayed value', r'''
    await h.repo(page); const https=await h.copyClone(page,'HTTPS');
    await page.getByRole('tab',{name:'SSH',exact:true}).click(); await expect(h.text(page,'Copied')).toHaveCount(0);
    await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied')).toBeVisible();
    const ssh=await page.evaluate(()=>navigator.clipboard.readText()); expect(ssh).not.toBe(https);
    const displayed=await page.locator('input:visible').evaluateAll(els=>els.map(el=>(el as HTMLInputElement).value));
    expect(displayed).toContain(ssh);
    await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied')).toHaveCount(1);
    expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(ssh);
    ''')
    g('REQ-3-2-3', 'stage2 feedback: an unavailable asynchronous clipboard still performs a real user-initiated copy', r'''
    await h.repo(page); await h.button(page,'Code').click();
    await page.evaluate(()=>{
      (window as any).readActualClipboard=navigator.clipboard.readText.bind(navigator.clipboard);
      Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});
    });
    const displayed=await page.locator('input:visible').evaluateAll(els=>els.map(el=>(el as HTMLInputElement).value));
    await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied')).toBeVisible();
    const copied=await page.evaluate(()=>(window as any).readActualClipboard()); expect(displayed).toContain(copied);
    ''')
    g('REQ-3-2-3', 'stage2 feedback: refused clipboard writes report failure without false success and allow retry', r'''
    await h.repo(page); await h.button(page,'Code').click();
    const sentinel=h.unique('uncopied'); await page.evaluate(async value=>{
      await navigator.clipboard.writeText(value);
      (window as any).writeActualClipboard=navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText=async()=>{throw new DOMException('Denied','NotAllowedError');};
    },sentinel);
    await h.button(page,'Copy clone value').click(); await expect(page.getByRole('alert')).toContainText(/unable to copy/i);
    await expect(h.text(page,'Copied')).toHaveCount(0); expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(sentinel);
    await page.evaluate(()=>{navigator.clipboard.writeText=(window as any).writeActualClipboard;});
    await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied')).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    ''')
    g('REQ-3-2-3', 'stage2 feedback: a late copy completion cannot confirm a different protocol or reopened menu', r'''
    await h.repo(page); await h.button(page,'Code').click();
    await page.evaluate(()=>{
      const write=navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText=value=>new Promise<void>((resolve,reject)=>{
        (window as any).finishCopy=()=>write(value).then(resolve,reject);
      });
    });
    await h.button(page,'Copy clone value').click(); await expect(h.button(page,'Copy clone value')).toBeDisabled();
    await page.getByRole('tab',{name:'SSH',exact:true}).click();
    await page.evaluate(()=>(window as any).finishCopy()); await expect(h.text(page,'Copied')).toHaveCount(0);
    await h.button(page,'Copy clone value').click(); await page.keyboard.press('Escape');
    await h.button(page,'Code').click(); await page.evaluate(()=>(window as any).finishCopy());
    await expect(h.text(page,'Copied')).toHaveCount(0); await expect(h.button(page,'Copy clone value')).toBeEnabled();
    ''')
    g('REQ-4-2-2', 'stage2 feedback: a fresh homepage directly exposes the saved commit and its read-only diff', r'''
    await h.home(page); await h.link(page,'Document search flow').click();
    const address=page.url(); await h.persisted(page,async()=>{
      await expect(h.text(page,'src/search.ts')).toBeVisible(); await expect(page.getByRole('heading',{name:/^Changed files/})).toBeVisible();
      await expect(page.getByText(/\d+ additions/)).toBeVisible(); await expect(page.getByText(/\d+ deletions/)).toBeVisible();
    });
    await page.goto(address); await expect(h.text(page,'src/search.ts')).toBeVisible();
    ''')
    g('REQ-4-2-1', 'stage2 feedback: homepage Commits follows the selected repository and retains each row author', r'''
    await h.home(page); await h.choose(page,'Workspace repository','Acme Demo/acme-docs'); await h.link(page,'Commits').click();
    for(const title of ['Document search flow','Initialize empty repository']) {
      const row=page.getByRole('listitem').filter({has:h.link(page,title)});
      await expect(row.getByText('alice-dev',{exact:true})).toBeVisible(); await expect(row).toContainText(/ago/);
    }
    await page.reload();
    for(const title of ['Document search flow','Initialize empty repository']) {
      const row=page.getByRole('listitem').filter({has:h.link(page,title)});
      await expect(row.getByText('alice-dev',{exact:true})).toBeVisible();
    }
    ''')
    create_repo=r'''
    const account=await h.register(page); await h.signIn(page,account.username); await h.link(page,'New repository').click();
    const repository=h.unique('stage2-private'); await h.field(page,'Repository name').fill(repository);
    await page.getByRole('radio',{name:'Private',exact:true}).check(); await h.button(page,'Create repository').click();
    await expect(h.button(page,'Add file')).toBeVisible(); const repoAddress=page.url();
    '''
    add_file=r'''
    await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await h.field(page,'File name').fill(path); await h.field(page,'File contents').fill(content);
    await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click();
    await expect(page.locator('pre')).toHaveText(content);
    '''
    g('REQ-4-4', 'stage2 feedback: new private commits are discoverable and colliding messages remain distinct until sign-out', create_repo+r'''
    const message=h.unique('Private commit');
    for(const path of ['first.md','second.md']) { const content='Saved '+path;
    '''+add_file+r'''
      await page.goto(repoAddress); await expect(h.button(page,'Add file')).toBeVisible();
    }
    await h.home(page); const links=page.getByRole('link').filter({hasText:message}); await expect(links).toHaveCount(2);
    const names=await links.allTextContents(); expect(new Set(names).size).toBe(2);
    const addresses=[];
    for(const label of names) {
      await h.link(page,label).click(); addresses.push(page.url()); await expect(page.getByRole('heading',{name:/^Changed files/})).toBeVisible(); await h.home(page);
    }
    expect(new Set(addresses).size).toBe(2);
    await h.signOut(page); await expect(page.getByRole('link').filter({hasText:message})).toHaveCount(0); await page.reload();
    await expect(page.getByRole('link').filter({hasText:message})).toHaveCount(0);
    await page.goto(addresses[0]); await expect(h.text(page,'Access denied')).toBeVisible();
    ''', requires=['REQ-4-2-2','REQ-1-1-1','REQ-1-1-2','REQ-1-2','REQ-3-2-1','REQ-4-4'])
    g('REQ-4-2-3', 'stage2 feedback: a search match remains visible with its full file after reload and filename navigation', r'''
    await h.repo(page); await h.link(page,'README.md').click(); const content=await page.locator('pre').textContent();
    await h.repo(page); const search=page.getByRole('searchbox',{name:'Search',exact:true});
    await search.fill('search flow'); await search.press('Enter'); await h.link(page,'Code').click(); await h.link(page,'README.md').click();
    const address=page.url();
    for(let i=0;i<3;i++) {
      await expect(h.text(page,'search flow')).toBeVisible(); expect(await page.locator('pre').textContent()).toBe(content);
      if(i===0) await page.reload(); else if(i===1) await h.link(page,'README.md').click();
    }
    await page.goto(address); await expect(h.text(page,'search flow')).toBeVisible();
    ''')
    g('REQ-4-4', 'stage2 feedback: literal case-insensitive repeated matches preserve source bytes and markup as text', create_repo+r'''
    const path='literal.md', message=h.unique('Literal source'), query='[a+b]? & <tag>';
    const content='Case [a+b]? & <tag>\nRepeated [A+B]? & <tag>\n  Unchanged spacing.\n';
    '''+add_file+r'''
    await page.goto(repoAddress); const search=page.getByRole('searchbox',{name:'Search',exact:true});
    await search.fill(query); await search.press('Enter'); await h.link(page,'Code').click(); await h.link(page,path).click();
    await h.persisted(page,async()=>{
      expect(await page.locator('pre').textContent()).toBe(content);
      await expect(h.text(page,query)).toBeVisible(); await expect(h.text(page,'[A+B]? & <tag>')).toBeVisible();
      await expect(page.locator('pre tag')).toHaveCount(0);
    });
    ''', requires=['REQ-4-2-3','REQ-1-1-1','REQ-1-1-2','REQ-3-2-1','REQ-4-4'])
    g('REQ-4-4', 'stage2 feedback: simultaneous invalid inputs preserve files and history without requiring a unique global error', r'''
    await h.signIn(page,'file-contributor'); const address=await h.repo(page,'file-management-demo');
    const files=await page.getByRole('list').last().getByRole('link').allTextContents();
    await h.link(page,'Commits').click(); const before=await h.historyLinks(page); await page.goto(address);
    await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await h.field(page,'File name').fill('../invalid.md'); await h.field(page,'File contents').fill('must not be saved');
    await h.field(page,'Commit message').fill(''); await h.button(page,'Commit changes').click();
    await expect(h.fileValidationReason(page).first()).toBeVisible();
    await page.goto(address); await expect(h.button(page,'Add file')).toBeVisible();
    expect(await page.getByRole('list').last().getByRole('link').allTextContents()).toEqual(files);
    await h.link(page,'Commits').click(); await expect.poll(()=>h.historyLinks(page)).toEqual(before);
    await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(before);
    ''')
