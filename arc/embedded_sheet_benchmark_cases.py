"""Requirement witnesses added after comparing the two Sheet run artifacts.

These remain requirement tests. Evaluator-specific locator choices belong in the
separate compatibility suite, not in this frozen derived oracle.
"""


def register(s):
    s('REQ-4-1-1', 'benchmark regression: aggregates ignore boolean-looking text as well as blanks and ordinary text', r'''
    await h.blank(page); await h.paste(page, 'A1', '2\nTRUE\nFALSE\nplain');
    const formulas = [
      ['B1', '=COUNT(A1:A5)', '1'],
      ['B2', '=SUM(A1:A5)', '2'],
      ['B3', '=AVERAGE(A1:A5)', '2'],
      ['B4', '=MIN(A1:A5)', '2'],
      ['B5', '=MAX(A1:A5)', '2'],
    ] as const;
    for (const [at, expression] of formulas) await h.edit(page, at, expression);
    await h.persisted(page, async () => {
      await h.values(page, {A1:'2', A2:'TRUE', A3:'FALSE', A4:'plain', A5:''});
      for (const [at, expression, result] of formulas) await h.formula(page, at, expression, result);
    });
    ''', requires=['REQ-4-1-1', 'REQ-1-2-1', 'REQ-3-1-1', 'REQ-3-1-2'])

    s('REQ-5-2-1', 'benchmark regression: editing an interior cell reopens the full rule and changes every constrained cell', r'''
    await h.blank(page); await h.paste(page, 'A1', '10\n20');
    await h.numericRule(page, 'A1', 'A2', '0', '100'); await page.reload();
    await h.cell(page, 'A2').click(); await h.data(page, 'Data validation');
    const dialog = page.getByRole('dialog', {name:'Data validation', exact:true});
    await expect(h.button(dialog, 'Delete rule')).toBeVisible();
    await expect(h.field(dialog, 'Maximum')).toHaveValue('100');
    await h.field(dialog, 'Maximum').fill('30'); await h.button(dialog, 'Save').click();
    await expect(dialog).toBeHidden();
    await h.edit(page, 'A1', '31');
    await expect(h.text(page, 'Please enter a number between 0 and 30').first()).toBeVisible();
    await h.values(page, {A1:'10', A2:'20'});
    await h.edit(page, 'A2', '31');
    await expect(h.text(page, 'Please enter a number between 0 and 30').first()).toBeVisible();
    await h.persisted(page, () => h.values(page, {A1:'10', A2:'20'}));
    await h.cell(page, 'A1').click(); await h.data(page, 'Data validation');
    await h.button(dialog, 'Delete rule').click(); await expect(dialog).toBeHidden();
    await h.edit(page, 'A1', '31'); await h.edit(page, 'A2', '31');
    await h.persisted(page, () => h.values(page, {A1:'31', A2:'31'}));
    ''', requires=['REQ-5-2-1', 'REQ-1-2-1', 'REQ-3-1-1', 'REQ-3-1-2', 'REQ-3-1-3'])
