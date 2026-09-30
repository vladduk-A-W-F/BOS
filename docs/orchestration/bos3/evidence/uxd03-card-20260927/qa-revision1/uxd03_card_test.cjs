#!/usr/bin/env node
'use strict';

/* B30-UXD03: one future in-memory presentation helper oracle, not app QA. */
const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function required(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Missing ${name}.`);
  return process.argv[index + 1];
}

const sourcePath = path.resolve(required('--source'));
const expectedCommit = required('--commit').toLowerCase();
const expectedHash = required('--sha256').toLowerCase();
if (!/^[0-9a-f]{40}$/.test(expectedCommit) || !/^[0-9a-f]{64}$/.test(expectedHash)) {
  throw new Error('Commit or SHA-256 guard has an invalid format.');
}
const repo = path.dirname(path.dirname(sourcePath));
const status = childProcess.execFileSync('git', ['-C', repo, 'status', '--porcelain'], {encoding: 'utf8'});
assert.equal(status, '', 'Source checkout must be clean.');
const commit = childProcess.execFileSync('git', ['-C', repo, 'rev-parse', 'HEAD'], {encoding: 'utf8'}).trim().toLowerCase();
assert.equal(commit, expectedCommit, 'Unexpected source commit.');
const source = fs.readFileSync(sourcePath, 'utf8');
const hash = crypto.createHash('sha256').update(source).digest('hex');
assert.equal(hash, expectedHash, 'Unexpected full source SHA-256.');

// Babel is an existing repository parser dependency; frontend code is not imported.
const Babel = require(path.join(repo, 'assets', 'babel.js'));
const ast = Babel.transform(source, {ast: true, code: false, babelrc: false, configFile: false}).ast;
const requiredNames = ['c01TaskCardFacts', 'c01Id', 'c01HandoffShape', 'c01Object', 'c01Display', 'c01Date', 'c01SourceRefs'];
const declarations = new Map();
for (const node of ast.program.body) {
  if (node.type === 'FunctionDeclaration' && requiredNames.includes(node.id?.name)) {
    assert.equal(declarations.has(node.id.name), false, `Duplicate declaration: ${node.id.name}`);
    declarations.set(node.id.name, source.slice(node.start, node.end));
  }
  if (node.type === 'VariableDeclaration') for (const item of node.declarations) {
    if (requiredNames.includes(item.id?.name)) {
      assert.equal(declarations.has(item.id.name), false, `Duplicate declaration: ${item.id.name}`);
      declarations.set(item.id.name, source.slice(node.start, node.end));
    }
  }
}
assert.deepEqual([...declarations.keys()].sort(), [...requiredNames].sort(), 'Exact helper dependencies not found.');
const helperSource = declarations.get('c01TaskCardFacts');
assert.doesNotMatch(
  helperSource,
  /\b(?:fetch|XMLHttpRequest|localStorage|sessionStorage|window|document|React|useState|useEffect|require|import)\b/,
  'Helper must remain a synchronous presentation function.'
);
const helperC01Names = new Set(helperSource.match(/\bc01[A-Z][A-Za-z0-9_]*/g) || []);
assert.deepEqual([...helperC01Names].sort(), ['c01HandoffShape', 'c01Id', 'c01TaskCardFacts'], 'Helper called an unreviewed c01 dependency.');
const execution = ['c01Id', 'c01Object', 'c01Display', 'c01Date', 'c01SourceRefs', 'c01HandoffShape', 'c01TaskCardFacts']
  .map(name => declarations.get(name)).join('\n');
const context = vm.createContext(Object.create(null));
vm.runInContext(`${execution}\nglobalThis.cardFacts = c01TaskCardFacts;`, context, {timeout: 1000});
const cardFacts = context.cardFacts;
assert.equal(typeof cardFacts, 'function');

function fullHandoff({state = 'sent', current = true, recipientId = 22, departmentId = 7, departmentName = 'Відділ контролю'} = {}) {
  return {
    schema: 'bos.task-handoff.v1', state, current,
    recipient: {employee_id: recipientId, user_id: 502, role: 'manager', department: {id: departmentId, name: departmentName}},
    sender: {user_id: 501, employee_id: 11, role: 'manager', department: {id: 3, name: 'Продажі'}},
    previous_assignee: {employee_id: 11}, expected_result: 'SECRET_EXPECTED_RESULT',
    deadline: '2026-10-02', as_of: '2026-09-27', source_refs: [{order_id: 77}],
  };
}

const employees = [{id: 22, branch: 9, full_name: 'Олена Виконавець'}, {id: 99, branch: 12, full_name: 'Інший отримувач'}];
const departments = [{id: 9, name: 'Поточний відділ'}, {id: 7, name: 'Відділ контролю'}, {id: 12, name: 'Логістика'}];
function task(overrides = {}) {
  return {
    id: 55, title: 'Наддовге приватне доручення '.repeat(12), status: 'active', archived: false,
    is_overdue: false, assignee_id: 22, assignee_name: 'Олена Виконавець', branch_name: 'Виробнича філія',
    order_id: 77, order_code: 'SO-77', handoff: fullHandoff(), result: 'SECRET_ACTUAL_RESULT', ...overrides,
  };
}

function expected(overrides = {}) {
  return {
    orderLabel: 'SO-77 · №77', assigneeDepartment: 'Поточний відділ · №9', businessBranch: 'Виробнича філія',
    handoffLabel: 'Призначення чинне', recipientId: 22, recipientDepartment: 'Відділ контролю · №7', ...overrides,
  };
}

function facts(value, people = employees, units = departments) {
  const before = JSON.stringify([value, people, units]);
  const result = JSON.parse(JSON.stringify(cardFacts(value, people, units)));
  assert.equal(JSON.stringify([value, people, units]), before, 'Helper mutated an input.');
  assert.deepEqual(Object.keys(result).sort(), ['assigneeDepartment', 'businessBranch', 'handoffLabel', 'orderLabel', 'recipientDepartment', 'recipientId']);
  const serialized = JSON.stringify(result);
  for (const secret of ['SECRET_EXPECTED_RESULT', 'SECRET_ACTUAL_RESULT', '501', '502', 'source_refs']) {
    assert.equal(serialized.includes(secret), false, `Leaked non-card data: ${secret}`);
  }
  return result;
}

assert.deepEqual(facts(task({handoff: null})), expected({handoffLabel: 'Відомостей про передачу немає', recipientId: null, recipientDepartment: null}));
assert.deepEqual(facts(task({handoff: undefined})), expected({handoffLabel: 'Відомостей про передачу немає', recipientId: null, recipientDepartment: null}));
assert.deepEqual(facts(task({handoff: {schema: 'legacy.v0', expected_result: 'SECRET_EXPECTED_RESULT'}})), expected({handoffLabel: 'Відомості про передачу не підтверджено', recipientId: null, recipientDepartment: null}));
assert.deepEqual(facts(task({handoff: fullHandoff({recipientId: 99})})), expected({handoffLabel: 'Чинність призначення не підтверджено', recipientId: 99, recipientDepartment: 'Відділ контролю · №7'}));
assert.deepEqual(facts(task({handoff: fullHandoff({state: 'superseded', current: false, recipientId: 99})})), expected({handoffLabel: 'Попереднє призначення', recipientId: 99, recipientDepartment: 'Відділ контролю · №7'}));
assert.deepEqual(facts(task({status: 'done'})), expected());
const longUnicode = 'ЗАМ-' + 'Ґвинт🔩'.repeat(40);
assert.deepEqual(facts(task({order_code: longUnicode})), expected({orderLabel: longUnicode + ' · №77'}));
assert.deepEqual(facts(task({order_id: 88, order_code: ''})), expected({orderLabel: '№88'}));
assert.deepEqual(facts(task({order_id: null, order_code: 'SHOULD-NOT-LEAK'})), expected({orderLabel: 'Поточне замовлення не прив’язано'}));

process.stdout.write(JSON.stringify({
  result: 'PASS', scope: 'B30-UXD03 pure in-memory presentation helper',
  source: sourcePath, commit, sha256: hash,
  cases: ['legacy', 'unknown_schema', 'recipient_mismatch', 'superseded', 'done_task', 'long_unicode', 'order_fallback'],
}) + '\n');
