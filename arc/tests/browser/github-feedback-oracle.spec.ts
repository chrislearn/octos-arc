import { test, expect, text, containsValue, metadataValue, discussionSnapshot, signIn, fileValidationReason, passwordValidationReason, filterStatus, attemptSubmission } from '../../derived-tests/hackathon--github/helpers';

test.use({ baseURL: 'http://github-oracle.test' });

test('a refusal attempt waits for the UI write to finish before the caller can reload', async ({ page }) => {
  let saved=false;
  await page.route('http://github-oracle.test/**', async route => {
    if(route.request().method()==='POST') {
      await new Promise(resolve=>setTimeout(resolve,250)); saved=true;
      await route.fulfill({json:{saved:true}});
    } else await route.fulfill({contentType:'text/html',body:'<button onclick="fetch(\'/write\',{method:\'POST\'})">Submit review</button>'});
  });
  await page.goto('/'); await attemptSubmission(page,page.getByRole('button',{name:'Submit review'}));
  expect(saved).toBe(true);
});

test('submission feedback excludes filled controls and waits for the rendered record', async ({ page }) => {
  await page.setContent(`<textarea aria-label="Summary">Saved review</textarea>
    <input aria-label="Title" value="Saved review">
    <div contenteditable="true">Saved review</div>`);
  await expect(text(page, 'Saved review')).toHaveCount(0);
  await page.evaluate(() => {
    const result = document.createElement('p');
    result.textContent = 'Saved review';
    document.body.append(result);
  });
  await expect(text(page, 'Saved review')).toHaveCount(1);
  await expect(text(page, 'Saved review')).toBeVisible();
  await expect(page.getByLabel('Summary')).toHaveValue('Saved review');
});

test('a complete account value can appear in a sentence but cannot match another identity or an input', async ({ page }) => {
  for(const html of ['<p>alice-dev</p>', '<p>Signed in as alice-dev</p>']) {
    await page.setContent(html); await expect(containsValue(page,'alice-dev').first()).toBeVisible();
  }
  for(const html of ['<p>alice-dev-other</p>', '<p>other-alice-dev</p>', '<input value="alice-dev">', '<p hidden>alice-dev</p>']) {
    await page.setContent(html); await expect(containsValue(page,'alice-dev')).toHaveCount(0);
  }
});

test('commit information accepts an inline SHA or the seeded count, but rejects a wrong count and editor-only data', async ({ page }) => {
  const h=await import('../../derived-tests/hackathon--github/helpers');
  for(const html of ['<li><code>abc123f</code>Implement search flow</li>', '<p>1 commit ahead</p>', '<p>1 commits on feature-search relative to main</p>']) {
    await page.setContent(html); await expect(h.comparisonCommitInformation(page,'Implement search flow',1).first()).toBeVisible();
  }
  await page.setContent('<li><code>abc123f</code>Implement search flow</li>');
  await expect(h.renderedSubstring(page,'Implement search flow')).toBeVisible();
  for(const html of ['<p>11 commits ahead</p>', '<p>0 commits ahead</p>', '<p hidden>1 commit ahead</p>', '<textarea>Implement search flow</textarea>']) {
    await page.setContent(html); await expect(h.comparisonCommitInformation(page,'Implement search flow',1)).toHaveCount(0);
  }
});

test('a visible file rejection requires no alert role, but hidden feedback and editor content are insufficient', async ({ page }) => {
  for(const html of ['<p>Invalid file path</p>', '<div role="alert">Commit message is required</div>']) {
    await page.setContent(html); await expect(fileValidationReason(page).first()).toBeVisible();
  }
  for(const html of ['<p>Saved file</p>', '<p hidden>Invalid file path</p>', '<textarea>Invalid file path</textarea>']) {
    await page.setContent(html); await expect(fileValidationReason(page)).toHaveCount(0);
  }
});

test('password rejection accepts either error or both in one block, but rejects hidden feedback and a success message', async ({ page }) => {
  for(const html of ['<p>Current password is incorrect</p>', '<p>Password confirmation does not match</p>', '<p>Current password is incorrect<br>Password confirmation does not match</p>']) {
    await page.setContent(html); await expect(passwordValidationReason(page).first()).toBeVisible();
  }
  for(const html of ['<p>Password updated</p>', '<p hidden>Current password is incorrect</p>', '<textarea>Password confirmation does not match</textarea>']) {
    await page.setContent(html); await expect(passwordValidationReason(page)).toHaveCount(0);
  }
});

test('status choice accepts a tab or an unlabeled native select and changes the displayed state', async ({ page }) => {
  await page.setContent('<button role="tab" onclick="document.querySelector(\'output\').textContent=\'Closed\'">Closed</button><output>Open</output>');
  await filterStatus(page,'Closed'); await expect(page.locator('output')).toHaveText('Closed');
  await page.setContent('<select onchange="document.querySelector(\'output\').textContent=this.value"><option>Open</option><option>Draft</option><option>Closed</option></select><output>Open</output>');
  await filterStatus(page,'Draft'); await expect(page.locator('output')).toHaveText('Draft');
});

test('email login verifies the known username independently of the email local part and menu Escape behavior', async ({ page }) => {
  await page.route('http://github-oracle.test/**', route => route.fulfill({contentType:'text/html',body:`
    <main id="app"></main><script>
    const app=document.querySelector('#app');
    if(localStorage.getItem('account')) {
      app.innerHTML='<button aria-label="Account menu">Account</button><nav id="menu" hidden><p>Signed in as distinct-account</p></nav>';
      document.querySelector('button').onclick=()=>document.querySelector('#menu').hidden=false;
    } else if(location.pathname==='/signin') {
      app.innerHTML='<label>Username or email<input></label><label>Password<input type="password"></label><button>Sign in</button>';
      document.querySelector('button').onclick=()=>{localStorage.setItem('account','distinct-account');location.href='/'};
    }
    else app.innerHTML='<a href="/signin">Sign in</a>';
    </script>`}));
  await signIn(page,'unrelated.email@example.test','Valid-password-123!','distinct-account');
  await expect(page.getByRole('button',{name:'Account menu'})).toBeVisible();
});

test('metadata values work across a flat grid and nested groups while historical entries and selector options cannot satisfy them', async ({ page }) => {
  for(const content of [
    '<div><button>Assignees</button></div><div>spec-triage</div><div><button>Labels</button></div><div>bug</div>',
    '<section><header><button>Assignees</button></header><p>Assigned to spec-triage</p></section><section><button>Labels</button><p>bug</p></section>',
  ]) {
    await page.setContent(`<main><article>Previously assigned spec-triage</article><aside>${content}</aside></main>`);
    await expect(metadataValue(page,'Assignees','spec-triage').first()).toBeVisible();
  }
  for(const extra of ['<article>Previously assigned spec-triage</article>', '<input value="spec-triage">', '<div role="option">spec-triage</div>', '<p hidden>spec-triage</p>']) {
    await page.setContent(`<main><article>Created issue</article><aside><button>Assignees</button><button>Labels</button>${extra}</aside></main>`);
    await expect(metadataValue(page,'Assignees','spec-triage')).toHaveCount(0);
  }
});

test('discussion snapshot waits for reload rendering, ignores relative clock changes and detects an illegally appended article', async ({ page }) => {
  let appended=false,minutes=1;
  await page.route('http://github-oracle.test/**', route => route.fulfill({contentType:'text/html',body:`
    <main><h1>Improve onboarding</h1></main><script>setTimeout(()=>{
      document.querySelector('main').insertAdjacentHTML('beforeend','<article>Created issue <time>${minutes} minutes ago</time></article>${appended?'<article>Illegal blank comment</article>':''}')
    },150)</script>`}));
  await page.goto('/'); const before=await discussionSnapshot(page); minutes=2;
  await page.reload(); await expect.poll(()=>discussionSnapshot(page)).toEqual(before);
  appended=true; await page.reload(); const wrong=await discussionSnapshot(page);
  expect(wrong).not.toEqual(before); expect(wrong).toHaveLength(before.length+1);
});

test('combobox choices work with native controls and portal options outside a row',async({page})=>{
  const h=await import('../../derived-tests/hackathon--github/helpers');
  await page.setContent('<div role="row"><select aria-label="Role"><option>Write</option><option>Read</option></select></div>');
  await h.choose(page.getByRole('row'),'Role','Read'); await h.chosen(page.getByRole('row'),'Role','Read');
  await page.setContent(`<div role="row"><button role="combobox" aria-label="Role" onclick="document.querySelector('#options').hidden=false">Write</button></div><div id="options" hidden><button role="option" onclick="document.querySelector('[role=combobox]').textContent='Read';document.querySelector('#options').hidden=true">Read</button></div>`);
  await h.choose(page.getByRole('row'),'Role','Read'); await h.chosen(page.getByRole('row'),'Role','Read');
  await expect(h.chosen(page.getByRole('row'),'Role','Write')).rejects.toThrow();
  await page.setContent('<select aria-label="test"><option>pending</option><option>success</option></select>');
  await h.choose(page,'test status','success'); await h.chosen(page,'test','success');
});

test('no actionable control accepts absent hidden or disabled controls and refuses enabled controls',async({page})=>{
  const h=await import('../../derived-tests/hackathon--github/helpers');
  for(const html of ['', '<button hidden>Change visibility</button>', '<button disabled>Change visibility</button>']) {
    await page.setContent(html); await h.unavailable(page,'Change visibility');
  }
  await page.setContent('<button>Change visibility</button>'); await expect(h.unavailable(page,'Change visibility')).rejects.toThrow();
});

test('review summary aliases and allowed save labels preserve the actual saved text',async({page})=>{
  const h=await import('../../derived-tests/hackathon--github/helpers');
  for(const label of ['Summary','Comment']) {
    await page.setContent(`<textarea aria-label="${label}"></textarea><input type="radio" aria-label="Comment"><button onclick="document.querySelector('output').textContent=document.querySelector('textarea').value">Update</button><output></output>`);
    await (await h.reviewSummary(page)).fill('Exact summary 中文'); await h.action(page,['Save','Update']).click();
    await expect(text(page,'Exact summary 中文')).toBeVisible();
  }
});

test('password controls must mask values instead of merely excluding input text from body text',async({page})=>{
  const h=await import('../../derived-tests/hackathon--github/helpers');
  await page.setContent('<input aria-label="Password" type="password" value="secret">'); await h.maskedPasswords(page,['Password']);
  await page.setContent('<input aria-label="Password" type="text" value="secret">'); await expect(h.maskedPasswords(page,['Password'])).rejects.toThrow();
});

test('clone copy accepts a descriptive button and checks the displayed value, including no-op rejection',async({page,context})=>{
  const h=await import('../../derived-tests/hackathon--github/helpers');
  await context.grantPermissions(['clipboard-read','clipboard-write']);
  for(const display of ['input','span']) for(const broken of [false,true]) {
    await page.route('https://github-oracle.test/**',route=>route.fulfill({contentType:'text/html',body:`<button>Code</button><button role="tab">HTTPS</button>${display==='input'?'<input readonly value="https://host.test/alice-dev/acme-docs">':'<span>https://host.test/alice-dev/acme-docs</span>'}<button onclick="${broken?'':"navigator.clipboard.writeText((document.querySelector('input')?.value||document.querySelector('span').textContent));"}document.querySelector('output').textContent='Copied'">Copy HTTPS address</button><output></output>`}));
    await page.goto('https://github-oracle.test/');
    if(broken) await expect(h.copyClone(page,'HTTPS')).rejects.toThrow();
    else expect(await h.copyClone(page,'HTTPS')).toBe('https://host.test/alice-dev/acme-docs');
    await page.unroute('https://github-oracle.test/**');
  }
});

test('recovery supports both a displayed one-step form and email-triggered form without a fixed code text-node requirement',async({page})=>{
  const h=await import('../../derived-tests/hackathon--github/helpers');
  for(const oneStep of [false,true]) {
    await page.setContent(`<a href="#" onclick="document.querySelector('main').hidden=false">Forgot password</a><main hidden><input aria-label="Email"><button onclick="document.querySelector('section').hidden=false">${oneStep?'Reset password':'Send reset link'}</button><section ${oneStep?'':'hidden'}><p>Your verification code is 123456</p><input aria-label="Verification code"><input aria-label="New password" type="password"><input aria-label="Confirm password" type="password"></section></main>`);
    await h.recovery(page,'alice.dev@example.test'); await expect(page.getByLabel('Email')).toHaveValue('alice.dev@example.test');
  }
});

test('review Summary wins over a mounted line Comment editor, and Comment fallback stays in the review form',async({page})=>{
  const h=await import('../../derived-tests/hackathon--github/helpers');
  for(const label of ['Summary','Comment']) {
    await page.setContent(`<div><textarea aria-label="Comment">existing line comment</textarea></div><section><textarea aria-label="${label}"></textarea><label><input type="radio">Approve</label><label><input type="radio">Request changes</label><label><input type="radio">Comment</label><button>Submit review</button></section>`);
    await (await h.reviewSummary(page)).fill('precise review summary');
    await expect(page.locator('section textarea')).toHaveValue('precise review summary');
    await expect(page.locator('div textarea')).toHaveValue('existing line comment');
  }
});
