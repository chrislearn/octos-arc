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
