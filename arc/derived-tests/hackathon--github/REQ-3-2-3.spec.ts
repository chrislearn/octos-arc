import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-2-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.copyClone(page,"HTTPS"); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-3-2-3: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.copyClone(page,"SSH"); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-3-2-3: stage2 feedback: HTTPS copy has one persistent confirmation and an unchanged action name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await page.clock.install();
  const copied=await h.copyClone(page,'HTTPS');
  await expect(page.getByText(/copied/i)).toHaveCount(1);
  await expect(page.getByText(/copied/i)).toBeVisible();
  await expect(h.button(page,'Copy clone value')).toBeEnabled();
  await page.clock.fastForward(6000); await expect(page.getByText(/copied/i)).toBeVisible();
  expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(copied);
  await page.keyboard.press('Escape'); await h.button(page,'Code').click();
  await expect(page.getByText(/copied/i)).toHaveCount(0);
});

test("REQ-3-2-3: stage2 feedback: SSH copy has one persistent confirmation and an unchanged action name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await page.clock.install();
  const copied=await h.copyClone(page,'SSH');
  await expect(page.getByText(/copied/i)).toHaveCount(1);
  await expect(page.getByText(/copied/i)).toBeVisible();
  await expect(h.button(page,'Copy clone value')).toBeEnabled();
  await page.clock.fastForward(6000); await expect(page.getByText(/copied/i)).toBeVisible();
  expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(copied);
  await page.keyboard.press('Escape'); await h.button(page,'Code').click();
  await expect(page.getByText(/copied/i)).toHaveCount(0);
});

test("REQ-3-2-3: stage2 feedback: changing protocol clears prior success and copies the newly displayed value", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); const https=await h.copyClone(page,'HTTPS');
  await page.getByRole('tab',{name:'SSH',exact:true}).click(); await expect(h.text(page,'Copied')).toHaveCount(0);
  await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied')).toBeVisible();
  const ssh=await page.evaluate(()=>navigator.clipboard.readText()); expect(ssh).not.toBe(https);
  const displayed=await page.locator('input:visible').evaluateAll(els=>els.map(el=>(el as HTMLInputElement).value));
  expect(displayed).toContain(ssh);
  await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied')).toHaveCount(1);
  expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(ssh);
});

test("REQ-3-2-3: stage2 feedback: an unavailable asynchronous clipboard still performs a real user-initiated copy", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.button(page,'Code').click();
  await page.evaluate(()=>{
    (window as any).readActualClipboard=navigator.clipboard.readText.bind(navigator.clipboard);
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});
  });
  const displayed=await page.locator('input:visible').evaluateAll(els=>els.map(el=>(el as HTMLInputElement).value));
  await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied')).toBeVisible();
  const copied=await page.evaluate(()=>(window as any).readActualClipboard()); expect(displayed).toContain(copied);
});

test("REQ-3-2-3: stage2 feedback: refused clipboard writes report failure without false success and allow retry", async ({ page, browser }) => {
  test.setTimeout(60_000);
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
});

test("REQ-3-2-3: stage2 feedback: a late copy completion cannot confirm a different protocol or reopened menu", async ({ page, browser }) => {
  test.setTimeout(60_000);
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
});

test("REQ-3-2-3: copy exact displayed HTTPS clone value without modifying repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.copyClone(page,"HTTPS"); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-3-2-3: copy exact displayed SSH clone value without modifying repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.copyClone(page,"SSH"); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});
