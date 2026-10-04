const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/boss_app_source.html'), 'utf8');
const begin = source.indexOf('function structureCounts(');
const end = source.indexOf('function NetworkStructure(', begin);
assert(begin >= 0 && end > begin);
const count = vm.runInNewContext(source.slice(begin, end) + '\nstructureCounts');
const rows = {
  lots: [{location_id: 1}, {location_id: 1}, {location_id: 2}],
  orders: [{location_id: 1, open_line_count: 2}, {location_id: 1, open_line_count: 0}, {location_id: 2, open_line_count: 1}],
  jobs: [{location_id: 1, status: 'running'}, {location_id: 1, status: 'done'}, {location_id: 2, status: 'planned'}],
};
assert.deepEqual(JSON.parse(JSON.stringify(count(rows, [1]))), {lots: 2, orders: 1, jobs: 1});
assert.deepEqual(JSON.parse(JSON.stringify(count(rows, [1, 2]))), {lots: 3, orders: 2, jobs: 2});
assert.deepEqual(JSON.parse(JSON.stringify(count(rows, []))), {lots: 0, orders: 0, jobs: 0});
const component = source.slice(end, source.indexOf('function ERPNetwork(', end));
assert(!/inventory_value|receivable|retained/.test(component), 'structure cells must not infer money or debt');
console.log('M6 scoped structure counts: PASS');
