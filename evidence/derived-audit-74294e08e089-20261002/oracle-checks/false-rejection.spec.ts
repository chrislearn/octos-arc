import { test, expect } from './helpers';
import * as h from './helpers';

test('actual helper falsely rejects a visible username inside a sentence', async ({page})=>{
 await page.route('**/*',route=>route.fulfill({contentType:'text/html',body:`<main id="app"></main><script>
 const app=document.querySelector('#app');
 if(sessionStorage.getItem('signed')) {app.innerHTML='<button aria-label="Account menu">Account</button><p hidden id="identity">Signed in as alice-dev</p>';document.querySelector('button').onclick=()=>document.querySelector('#identity').hidden=false}
 else if(location.pathname==='/signin') {app.innerHTML='<label>Username or email<input></label><label>Password<input type="password"></label><button>Sign in</button>';document.querySelector('button').onclick=()=>{sessionStorage.setItem('signed','yes');location.href='/'}}
 else app.innerHTML='<a href="/signin">Sign in</a>';
 </script>`}));
 await expect(h.signIn(page,'alice-dev')).rejects.toThrow();
 await expect(page.getByText('Signed in as alice-dev',{exact:true})).toBeVisible();
 await expect(h.button(page,'Account menu')).toBeVisible();
});

test('actual sidebar helper falsely rejects allowed flat metadata groups',async({page})=>{
 await page.setContent('<main><article>Created issue</article><aside><div><button>Assignees</button></div><div>spec-triage</div><div><button>Labels</button></div><div>bug</div><div><button>Milestone</button></div><div>v1.0</div></aside></main>');
 await expect(page.getByText('spec-triage',{exact:true})).toBeVisible();
 await expect(expect(h.sidebar(page,'Assignees')).toContainText('spec-triage')).rejects.toThrow();
});

test('REQ-4-4 alert assertion falsely rejects ordinary visible validation feedback',async({page})=>{
 await page.setContent('<label>File name<input value="../invalid.md"></label><p>Invalid file path</p><button>Commit changes</button>');
 await expect(page.getByText('Invalid file path',{exact:true})).toBeVisible();
 // The downloaded REQ-4-4 case uses this exact assertion; source has no alert-role contract.
 await expect(expect(page.getByRole('alert').filter({hasText:/Invalid file path|Commit message is required/}).first()).toBeVisible()).rejects.toThrow();
});

test('runner context inherits baseURL: missing explicit option is not a defect',async({browser})=>{
 const context=await browser.newContext(); try {await context.route('**/*',route=>route.fulfill({contentType:'text/html',body:'<p>OK</p>'})); const p=await context.newPage();await p.goto('/');await expect(p).toHaveURL('http://localhost:48199/');} finally{await context.close()}
});


test('REQ-5-2-3 immediate discussion snapshot falsely rejects normal asynchronous reload',async({page})=>{
 await page.route('**/*',route=>route.fulfill({contentType:'text/html',body:`<main></main><script>setTimeout(()=>document.querySelector('main').innerHTML='<article>Created issue</article>',200)</script>`}));
 await page.goto('/'); await expect(page.getByRole('article')).toBeVisible();
 const before=await page.getByRole('article').allTextContents();
 await page.reload(); const immediate=await page.getByRole('article').allTextContents();
 expect(()=>expect(immediate).toEqual(before)).toThrow();
 await expect(page.getByRole('article')).toHaveText('Created issue');
});

test('REQ-5-2-3 raw discussion snapshot falsely treats relative time as a changed record',async({page})=>{
 await page.setContent('<article>Created issue <time>1 minute ago</time></article>');
 const before=await page.getByRole('article').allTextContents();
 await page.setContent('<article>Created issue <time>2 minutes ago</time></article>');
 const later=await page.getByRole('article').allTextContents();
 expect(()=>expect(later).toEqual(before)).toThrow();
 await expect(page.getByRole('article')).toContainText('Created issue');
});
