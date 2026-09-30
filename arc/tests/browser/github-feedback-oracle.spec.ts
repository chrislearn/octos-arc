import { test, expect, text } from '../../derived-tests/hackathon--github/helpers';

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
