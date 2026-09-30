const path = require('node:path');
const output = process.env.OCTOS_BROWSER_PROOF_DIR || path.resolve('.arc/helper-browser-tests');
module.exports = {
  testDir: __dirname,
  testMatch: '*-oracle.spec.ts',
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 1_000 },
  use: { browserName: 'chromium', headless: true, trace: 'on' },
  outputDir: path.join(output, 'test-results'),
  reporter: [['line'], ['json', { outputFile: path.join(output, 'report.json') }]],
};
