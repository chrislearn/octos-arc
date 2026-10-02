'use strict';
// Canonical owner of the workbooks collection: initial seed, shape and shared access.
const {collection} = require('./collection');

const cell = (value) => ({original: value, displayed: value});

const initial = [
  {
    id: 'q3-sales',
    name: 'Q3 Sales',
    lastUpdated: '2024-01-15T10:00:00.000Z',
    worksheets: [
      {
        id: 'q3-sales-sheet1',
        name: 'Sheet1',
        cells: {
          A1: cell('Region'), B1: cell('Sales'), C1: cell('Status'),
          A2: cell('East'), B2: cell('1200'), C2: cell('Open'),
          A3: cell('North'), B3: cell('800'), C3: cell('Closed'),
          A4: cell('South'), B4: cell('700'), C4: cell('Open')
        },
        selection: {current: 'A1', rectangle: {top: 1, left: 1, bottom: 1, right: 1}}
      }
    ]
  },
  {
    id: 'row-operations-seed',
    name: 'Row operations seed',
    lastUpdated: '2024-01-15T10:00:00.000Z',
    worksheets: [
      {
        id: 'row-ops-sheet1',
        name: 'Sheet1',
        cells: {
          A1: cell('Label'), B1: cell('Value'),
          A2: cell('first'), B2: cell('10'),
          A3: cell('second'), B3: cell('20')
        },
        selection: {current: 'A1', rectangle: {top: 1, left: 1, bottom: 1, right: 1}}
      }
    ]
  },
  {
    id: 'column-operations-seed',
    name: 'Column operations seed',
    lastUpdated: '2024-01-15T10:00:00.000Z',
    worksheets: [
      {
        id: 'col-ops-sheet1',
        name: 'Sheet1',
        cells: {
          A1: cell('first'), A2: cell('alpha'),
          B1: cell('second'), B2: cell('beta'),
          C1: cell('third'), C2: cell('gamma')
        },
        selection: {current: 'A1', rectangle: {top: 1, left: 1, bottom: 1, right: 1}}
      }
    ]
  }
];

const blankSelection = () => ({current: 'A1', rectangle: {top: 1, left: 1, bottom: 1, right: 1}});

module.exports = collection('workbooks', {
  idKey: 'id',
  initial,
  normalize(record) {
    if (!record.lastUpdated) record.lastUpdated = new Date().toISOString();
    if (!Array.isArray(record.worksheets)) record.worksheets = [];
    return record;
  }
});

module.exports.createBlank = function createBlank(name) {
  return module.exports.create({
    name,
    lastUpdated: new Date().toISOString(),
    worksheets: [{
      id: `sheet-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: 'Sheet1',
      cells: {},
      selection: blankSelection()
    }]
  });
};
