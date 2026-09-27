#!/usr/bin/env node
'use strict';

// UXD02 bounded QA: exact helper slices plus AST shape checks. No app import.
const assert = require('assert/strict');
const childProcess = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

function stop(message) { throw new Error(`UXD02-MONITOR-QA: ${message}`); }
function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) stop(`missing ${name}`);
  return process.argv[index + 1];
}
function hash(value) { return crypto.createHash('sha256').update(value).digest('hex'); }
function git(repo, args) {
  return childProcess.execFileSync('git', ['-C', repo, ...args], {encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']}).trim();
}
function name(node) {
  if (!node || typeof node !== 'object') return '';
  if (node.type === 'Identifier' || node.type === 'JSXIdentifier') return node.name;
  if (node.type === 'StringLiteral') return node.value;
  return '';
}
function literal(node) { return node?.type === 'StringLiteral' ? node.value : undefined; }
function walk(node, visit, parent = null) {
  if (!node || typeof node !== 'object') return;
  if (typeof node.type === 'string') visit(node, parent);
  for (const [key, value] of Object.entries(node)) {
    if (key === 'loc' || key === 'start' || key === 'end' || key === 'extra') continue;
    if (Array.isArray(value)) value.forEach(child => walk(child, visit, node));
    else if (value && typeof value === 'object') walk(value, visit, node);
  }
}
function functionDeclaration(ast, expected) {
  const found = [];
  walk(ast, node => { if (node.type === 'FunctionDeclaration' && name(node.id) === expected) found.push(node); });
  assert.equal(found.length, 1, `exact function declaration required: ${expected}`);
  return found[0];
}
function descendants(node) { const result = []; walk(node, child => result.push(child)); return result; }
function hasIdentifier(node, expected) {
  return descendants(node).some(child => name(child) === expected);
}
function hasCall(node, callee, firstArgument) {
  return descendants(node).some(child => child.type === 'CallExpression'
    && name(child.callee) === callee
    && (firstArgument === undefined || literal(child.arguments[0]) === firstArgument));
}
function memberPath(node) {
  const pathParts = [];
  let current = node;
  while (current?.type === 'MemberExpression') {
    pathParts.unshift(name(current.property));
    current = current.object;
  }
  pathParts.unshift(name(current));
  return pathParts;
}
function jsxAttribute(opening, expected) {
  return (opening.attributes || []).find(attribute => attribute.type === 'JSXAttribute' && name(attribute.name) === expected);
}
function jsxElements(node, component) {
  return descendants(node).filter(child => child.type === 'JSXElement' && name(child.openingElement?.name) === component);
}
function frontendBody(html) {
  const scripts = [...html.matchAll(/<script type="text\/babel">([\s\S]*?)<\/script>/g)];
  assert.equal(scripts.length, 1, 'exactly one text/babel script required');
  const body = scripts[0][1].replace('{% verbatim %}', '').replace('{% endverbatim %}', '');
  assert(!/\{%\s*(?:end)?verbatim\s*%\}/.test(body), 'unstripped verbatim marker');
  return body;
}
function parse(repo, body) {
  const babel = require(path.join(repo, 'assets', 'babel.js'));
  return babel.transform(body, {ast: true, code: false, babelrc: false, configFile: false, parserOpts: {plugins: ['jsx']}}).ast;
}
function sourceOf(body, node) {
  assert(Number.isInteger(node.start) && Number.isInteger(node.end), 'AST range missing');
  return body.slice(node.start, node.end);
}

function exactHelpers(ast, body) {
  const required = ['purchaseRemaining', 'b03Positive', 'b03OpenLine', 'monitorRows', 'b03FindRecord', 'homeSelectionVisible'];
  const slices = required.map(item => sourceOf(body, functionDeclaration(ast, item)));
  const context = {BigInt, Number, String, Object, Array, Set};
  const prelude = "const BOS_METRICS=[]; const bosCan=()=>false; const homeKnownNumber=()=>false;\n";
  const expose = '\nglobalThis.__uxd02={monitorRows,homeSelectionVisible};';
  vm.runInNewContext(prelude + slices.join('\n') + expose, context, {timeout: 1000});
  return context.__uxd02;
}

function ids(rows) { return rows.map(row => row.id); }
function assertRows(actual, expectedIds, originalById, label) {
  assert.deepEqual(ids(actual), expectedIds, `${label} IDs`);
  assert.equal(new Set(ids(actual)).size, actual.length, `${label} must not duplicate IDs`);
  actual.forEach(row => assert.strictEqual(row, originalById.get(row.id), `${label} preserves row identity`));
}
function assertPredicates(helpers) {
  const snapshot = {
    orders: [
      {id: 101, status: 'quote'},
      {id: 102, status: 'confirmed'},
      {id: 103, status: 'draft'},
    ],
    lines: [
      {order_id: 101, quantity: '10', shipped: '10', open_quantity: '2'},
      {order_id: 101, quantity: '10', shipped: '9', open_quantity: '1'},
      {order_id: 102, quantity: '8', shipped: '0', open_quantity: '0'},
      {order_id: 103, quantity: '7', shipped: '2'},
    ],
    jobs: [{id: 201, status: 'done'}, {id: 202, status: 'queued'}, {id: 203, status: 'held'}],
    lots: [
      {id: 301, quantity: '10', quality: 'approved', missing_documents: []},
      {id: 302, quantity: '10', quality: 'blocked', missing_documents: []},
      {id: 303, quantity: '10', quality: 'approved', missing_documents: ['certificate']},
      {id: 304, quantity: '0', quality: 'blocked', missing_documents: ['certificate']},
      {id: 305, quantity: '-1', quality: 'blocked', missing_documents: ['certificate']},
    ],
  };
  const before = JSON.stringify(snapshot);
  assertRows(helpers.monitorRows(snapshot, 'orders'), [101, 103], new Map(snapshot.orders.map(row => [row.id, row])), 'orders');
  assertRows(helpers.monitorRows(snapshot, 'jobs'), [202, 203], new Map(snapshot.jobs.map(row => [row.id, row])), 'jobs');
  assertRows(helpers.monitorRows(snapshot, 'quality'), [302, 303], new Map(snapshot.lots.map(row => [row.id, row])), 'quality');
  const assertEmpty = (value, label) => {
    assert(Array.isArray(value), `${label} returns an array`);
    assert.equal(value.length, 0, `${label} is empty`);
  };
  assertEmpty(helpers.monitorRows(null, 'orders'), 'null snapshot');
  for (const key of ['', 'tasks', 'receivable', 'unknown']) assertEmpty(helpers.monitorRows(snapshot, key), `unknown key ${key}`);
  assert.equal(JSON.stringify(snapshot), before, 'monitorRows must not mutate input');
}
function assertSelection(helpers) {
  const data = {orders: [{id: 11}], jobs: [{id: 12}], lots: [{id: 13}], home: {financial: []}};
  assert.equal(helpers.homeSelectionVisible({kind: 'monitor-list', key: 'orders', monitorOrigin: 'orders'}, data), true, 'orders monitor-list origin');
  assert.equal(helpers.homeSelectionVisible({kind: 'monitor-list', key: 'quality', monitorOrigin: 'quality'}, data), true, 'quality monitor-list origin');
  assert.equal(helpers.homeSelectionVisible({kind: 'monitor-list', key: 'orders', monitorOrigin: 'jobs'}, data), false, 'mismatched monitor origin');
  assert.equal(helpers.homeSelectionVisible({kind: 'monitor-list', key: 'tasks', monitorOrigin: 'tasks'}, data), false, 'unknown monitor key');
  assert.equal(helpers.homeSelectionVisible({kind: 'list', key: 'orders', monitorOrigin: 'orders'}, data), false, 'generic list cannot inherit monitor origin');
  assert.equal(helpers.homeSelectionVisible({kind: 'metric', key: 'receivable', monitorOrigin: 'orders'}, data), false, 'metric cannot inherit monitor origin');
  assert.equal(helpers.homeSelectionVisible({kind: 'orders', id: 11, monitorOrigin: 'orders'}, data), true, 'visible monitor-origin record');
  assert.equal(helpers.homeSelectionVisible({kind: 'orders', id: 99, monitorOrigin: 'orders'}, data), false, 'foreign record ID');
}

function assertReadOnlyAst(ast) {
  const docViewer = functionDeclaration(ast, 'DocViewer');
  const readOnlyParameter = docViewer.params.find(parameter => parameter.type === 'ObjectPattern')?.properties
    .map(property => property.value)
    .find(value => value?.type === 'AssignmentPattern' && name(value.left) === 'readOnly');
  assert.equal(readOnlyParameter?.right?.type, 'BooleanLiteral', 'DocViewer readOnly default missing');
  assert.equal(readOnlyParameter.right.value, false, 'DocViewer readOnly must default false');
  assert(
    hasIdentifier(docViewer, 'readOnly')
      && hasCall(docViewer, 'bosCan', 'write')
      && hasIdentifier(docViewer, 'current')
      && descendants(docViewer).some(node => literal(node) === 'needs_review'),
    'manual review must retain readOnly/write/current/needs_review gate',
  );

  const inspector = functionDeclaration(ast, 'BoSInspector');
  const viewerCalls = jsxElements(inspector, 'DocViewer');
  assert.equal(viewerCalls.length, 1, 'BoSInspector must forward one DocViewer');
  assert.equal(name(jsxAttribute(viewerCalls[0].openingElement, 'readOnly')?.value?.expression), 'readOnly', 'DocViewer readOnly forwarding');

  const home = functionDeclaration(ast, 'BoSHome');
  const monitorInspectors = jsxElements(home, 'BoSInspector').filter(element => {
    const attributes = element.openingElement.attributes || [];
    return !!jsxAttribute(element.openingElement, 'readOnly')
      && !attributes.some(attribute => name(attribute.name) === 'onAction' || name(attribute.name) === 'onNavigate');
  });
  assert.equal(monitorInspectors.length, 1, 'monitor inspector must be readOnly without action/navigation props');
  const begin = descendants(home).find(node => node.type === 'FunctionDeclaration' && name(node.id) === 'begin');
  assert(begin && hasIdentifier(begin, 'monitor') && hasIdentifier(begin, 'readOnlyOverview'), 'begin must retain monitor/readOnly gate');
}
function assertSelectionAst(ast) {
  const home = functionDeclaration(ast, 'BoSHome');
  const inspectRecord = descendants(home).find(node => node.type === 'FunctionDeclaration' && name(node.id) === 'inspectMonitorRecord');
  assert(inspectRecord, 'inspectMonitorRecord missing');
  assert(hasCall(inspectRecord, 'monitorRows'), 'initial selection must use monitorRows');
  assert(descendants(inspectRecord).some(node => node.type === 'CallExpression' && name(node.callee?.property) === 'some'), 'initial selection must check membership');
  assert(hasCall(inspectRecord, 'open') && hasIdentifier(inspectRecord, 'monitorOrigin'), 'initial selection must retain origin into open');

  const traceSelect = descendants(home).find(node => node.type === 'FunctionDeclaration' && name(node.id) === 'traceSelect');
  assert(traceSelect, 'traceSelect missing');
  const monitorNull = descendants(traceSelect).some(node => node.type === 'AssignmentExpression'
    && memberPath(node.left).join('.') === 'life.current.nextSelection'
    && node.right?.type === 'ConditionalExpression'
    && name(node.right.test) === 'monitor'
    && node.right.consequent?.type === 'NullLiteral');
  assert(monitorNull, 'trace handoff must clear monitor nextSelection');

  const publish = descendants(home).find(node => node.type === 'FunctionDeclaration' && name(node.id) === 'publish');
  const publishClearsSelection = publish && descendants(publish).some(node => node.type === 'CallExpression'
    && name(node.callee) === 'select' && node.arguments[0]?.type === 'NullLiteral');
  const publishClearsOrigin = publish && descendants(publish).some(node => node.type === 'AssignmentExpression'
    && memberPath(node.left).join('.') === 'life.current.nextSelection' && node.right?.type === 'NullLiteral');
  assert(publishClearsSelection && publishClearsOrigin, 'non-ready publish must clear selection/origin state');
}

function main() {
  const source = path.resolve(argument('--source'));
  const expectedCommit = argument('--commit').toLowerCase();
  const expectedHash = argument('--sha256').toLowerCase();
  assert.match(expectedCommit, /^[0-9a-f]{40}$/, 'full commit SHA required');
  assert.match(expectedHash, /^[0-9a-f]{64}$/, 'full source SHA-256 required');
  assert(source.endsWith(path.join('frontend', 'boss_app_source.html')), 'expected frontend/boss_app_source.html');
  const repo = path.resolve(path.dirname(source), '..');
  assert.equal(git(repo, ['status', '--porcelain']), '', 'target checkout is not clean');
  assert.equal(git(repo, ['rev-parse', 'HEAD']).toLowerCase(), expectedCommit, 'target commit mismatch');
  const html = fs.readFileSync(source, 'utf8');
  assert.equal(hash(html), expectedHash, 'full source SHA-256 mismatch');
  const body = frontendBody(html);
  const ast = parse(repo, body);
  const helpers = exactHelpers(ast, body);
  assertPredicates(helpers);
  assertSelection(helpers);
  assertReadOnlyAst(ast);
  assertSelectionAst(ast);
  process.stdout.write(JSON.stringify({
    status: 'PASS',
    classification: 'NEW_THREE_METRIC_SELECTION_PREDICATES_AND_READONLY_PRESENTATION_NOT_LEARNING_PAYMENT_BROWSER_RETRY',
    source, commit: expectedCommit, sha256: expectedHash,
    checks: ['monitorRows-predicates', 'selection-origin', 'readOnly-boundary', 'stale-trace-clear'],
  }) + '\n');
}

main();
