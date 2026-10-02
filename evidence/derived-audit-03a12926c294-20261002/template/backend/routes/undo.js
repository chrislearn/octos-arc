'use strict';
const workbooks = require('../lib/workbookStore');
const history = require('../lib/undo');

module.exports = (app) => {
  app.get('/api/workbooks/:id/history', (req, res) => {
    if (!workbooks.get(req.params.id)) return res.status(404).json({error: 'Workbook not found'});
    res.json(history.status(req.params.id));
  });

  app.post('/api/workbooks/:id/undo', (req, res) => {
    if (!workbooks.get(req.params.id)) return res.status(404).json({error: 'Workbook not found'});
    const result = history.apply(req.params.id, 'undo');
    if (!result) return res.status(409).json({error: 'Nothing to undo'});
    res.json(result);
  });

  app.post('/api/workbooks/:id/redo', (req, res) => {
    if (!workbooks.get(req.params.id)) return res.status(404).json({error: 'Workbook not found'});
    const result = history.apply(req.params.id, 'redo');
    if (!result) return res.status(409).json({error: 'Nothing to redo'});
    res.json(result);
  });
};
