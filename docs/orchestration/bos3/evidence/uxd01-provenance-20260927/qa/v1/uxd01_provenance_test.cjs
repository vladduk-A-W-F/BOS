#!/usr/bin/env node
'use strict';

// AST-only QA oracle for UXD01. It intentionally never mounts the application.
const assert = require('assert/strict');
const crypto = require('crypto');
const childProcess = require('child_process');
const fs = require('fs');
const path = require('path');

function fail(message) {
  throw new Error(`UXD01-PROVENANCE-QA: ${message}`);
}

function readArgument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) fail(`missing ${name}`);
  return process.argv[index + 1];
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function git(repo, args) {
  return childProcess.execFileSync('git', ['-C', repo, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

function nodeName(node) {
  if (!node || typeof node !== 'object') return '';
  if (node.type === 'Identifier' || node.type === 'JSXIdentifier') return node.name;
  if (node.type === 'StringLiteral') return node.value;
  return '';
}

function propertyName(property) {
  return property && property.type === 'ObjectProperty' ? nodeName(property.key) : '';
}

function propertyValue(object, name) {
  return (object.properties || []).find(property => propertyName(property) === name)?.value;
}

function literalValue(node) {
  return node?.type === 'StringLiteral' ? node.value : undefined;
}

function walk(node, visit, parent = null) {
  if (!node || typeof node !== 'object') return;
  if (typeof node.type === 'string') visit(node, parent);
  for (const [key, value] of Object.entries(node)) {
    if (key === 'loc' || key === 'start' || key === 'end' || key === 'extra') continue;
    if (Array.isArray(value)) value.forEach(child => walk(child, visit, node));
    else if (value && typeof value === 'object') walk(value, visit, node);
  }
}

function functionDeclaration(ast, name) {
  let found = null;
  walk(ast, node => {
    if (node.type === 'FunctionDeclaration' && nodeName(node.id) === name) {
      if (found) fail(`more than one function ${name}`);
      found = node;
    }
  });
  if (!found) fail(`function ${name} not found`);
  return found;
}

function functionNodes(fn) {
  const nodes = [];
  walk(fn.body, node => nodes.push(node));
  return nodes;
}

function containsIdentifier(node, name) {
  let found = false;
  walk(node, current => {
    if (nodeName(current) === name) found = true;
  });
  return found;
}

function containsCall(node, calleeName, firstArgument) {
  let found = false;
  walk(node, current => {
    if (current.type !== 'CallExpression' || nodeName(current.callee) !== calleeName) return;
    if (firstArgument === undefined || literalValue(current.arguments[0]) === firstArgument) found = true;
  });
  return found;
}

function jsxAttribute(element, name) {
  return (element.openingElement?.attributes || []).find(attribute =>
    attribute.type === 'JSXAttribute' && nodeName(attribute.name) === name,
  );
}

function className(element) {
  return literalValue(jsxAttribute(element, 'className')?.value);
}

function jsxElements(nodes, tag, classValue) {
  return nodes.filter(node => node.type === 'JSXElement'
    && nodeName(node.openingElement?.name) === tag
    && (classValue === undefined || className(node) === classValue));
}

function allStringLiterals(nodes) {
  const values = new Set();
  nodes.forEach(node => walk(node, current => {
    if (current.type === 'StringLiteral') values.add(current.value);
  }));
  return values;
}

function objectProperties(object) {
  return new Set((object.properties || []).map(propertyName).filter(Boolean));
}

function descriptorByKey(objects, key) {
  const matches = objects.filter(object => literalValue(propertyValue(object, 'key')) === key);
  assert.equal(matches.length, 1, `expected exactly one ${key} descriptor`);
  return matches[0];
}

function assertDescriptor(descriptor, expected) {
  const fields = objectProperties(descriptor);
  for (const field of ['key', 'label', 'value', 'note', 'section', 'sub', 'provenance']) {
    assert(fields.has(field), `${expected.key} lacks ${field}`);
  }
  assert.equal(literalValue(propertyValue(descriptor, 'section')), expected.section, `${expected.key} section`);
  assert.equal(literalValue(propertyValue(descriptor, 'sub')), expected.sub, `${expected.key} subsection`);
  const provenance = propertyValue(descriptor, 'provenance');
  assert.equal(provenance?.type, 'ObjectExpression', `${expected.key} provenance object`);
  const provenanceFields = objectProperties(provenance);
  for (const field of ['source', 'calculation', 'deviation', 'action']) {
    assert(provenanceFields.has(field), `${expected.key} provenance lacks ${field}`);
  }
  assert((provenance.properties || []).some(property =>
    property.type === 'SpreadElement' && nodeName(property.argument) === 'provenance',
  ), `${expected.key} must inherit shared scope/branch/period`);
}

function isMetricsPush(node) {
  return node?.type === 'CallExpression'
    && node.callee?.type === 'MemberExpression'
    && nodeName(node.callee.object) === 'metrics'
    && nodeName(node.callee.property) === 'push';
}

function expressionHasReadyAndAllowed(expression) {
  return containsIdentifier(expression, 'ready') && containsIdentifier(expression, 'allowed');
}

function babelBody(html) {
  const scripts = [...html.matchAll(/<script type="text\/babel">([\s\S]*?)<\/script>/g)];
  assert.equal(scripts.length, 1, 'expected exactly one text/babel script');
  const body = scripts[0][1].replace('{% verbatim %}', '').replace('{% endverbatim %}', '');
  assert(!/\{%\s*(?:end)?verbatim\s*%\}/.test(body), 'unstripped verbatim marker');
  return body;
}

function parseAst(repo, body) {
  const babel = require(path.join(repo, 'assets', 'babel.js'));
  return babel.transform(body, {
    ast: true,
    code: false,
    babelrc: false,
    configFile: false,
    parserOpts: {plugins: ['jsx']},
  }).ast;
}

function assertMetricModel(home) {
  const nodes = functionNodes(home);
  const provenanceDecl = nodes.find(node => node.type === 'VariableDeclarator' && nodeName(node.id) === 'provenance');
  assert.equal(provenanceDecl?.init?.type, 'ObjectExpression', 'shared provenance descriptor missing');
  const sharedFields = objectProperties(provenanceDecl.init);
  for (const field of ['scope', 'branch', 'period']) assert(sharedFields.has(field), `shared provenance lacks ${field}`);

  const metricArray = nodes.find(node => node.type === 'ArrayExpression' &&
    node.elements.filter(element => element?.type === 'ObjectExpression' && literalValue(propertyValue(element, 'key'))).length === 4 &&
    ['orders', 'jobs', 'quality', 'tasks'].every(key => node.elements.some(element =>
      element?.type === 'ObjectExpression' && literalValue(propertyValue(element, 'key')) === key,
    )));
  assert(metricArray, 'four base metric descriptors missing');
  const descriptors = metricArray.elements.filter(element => element?.type === 'ObjectExpression');
  for (const expected of [
    {key: 'orders', section: 'erp', sub: 'sales'},
    {key: 'jobs', section: 'erp', sub: 'production'},
    {key: 'quality', section: 'erp', sub: 'quality'},
    {key: 'tasks', section: 'hr', sub: 'tasks'},
  ]) assertDescriptor(descriptorByKey(descriptors, expected.key), expected);

  const financePush = nodes.find(node => isMetricsPush(node) &&
    literalValue(propertyValue(node.arguments[0], 'key')) === 'receivable');
  assert(financePush, 'finance-only receivable descriptor missing');
  assertDescriptor(financePush.arguments[0], {key: 'receivable', section: 'erp', sub: 'costs'});
  const financeIf = nodes.find(node => node.type === 'IfStatement'
    && containsCall(node.test, 'bosCan', 'finance')
    && containsIdentifier(node.consequent, 'receivable'));
  assert(financeIf, 'receivable must remain under bosCan(finance)');
}

function assertMonitorDisclosure(monitor) {
  const nodes = functionNodes(monitor);
  const labels = allStringLiterals(nodes);
  for (const label of [
    'Джерело', 'Як обчислено', 'Охоплення', 'Філія', 'Період',
    'Бізнес-дата розрахунку', 'Прочитано у цьому вікні', 'Оновлення джерел',
    'Причина відхилення', 'Наступний крок',
  ]) assert(labels.has(label), `disclosure label missing: ${label}`);

  const disclosure = jsxElements(nodes, 'div', 'bos-monitor-disclosure');
  assert.equal(disclosure.length, 1, 'trusted provenance disclosure missing');
  assert(containsIdentifier(disclosure[0], 'businessDate'), 'business date not bound to disclosure');
  assert(containsIdentifier(disclosure[0], 'readTime'), 'local read time not bound to disclosure');
  assert(containsIdentifier(disclosure[0], 'at'), 'read timestamp not bound to disclosure');

  const readyDisclosure = nodes.find(node => node.type === 'ConditionalExpression'
    && nodeName(node.test) === 'ready'
    && containsIdentifier(node.consequent, 'businessDate')
    && containsIdentifier(node.consequent, 'readTime')
    && jsxElements([node.alternate], 'p', 'bos-monitor-disclosure-empty').length === 1);
  assert(readyDisclosure, 'provenance must have a ready-only disclosure and an empty fallback');

  const trustedTimes = jsxElements(nodes, 'time');
  assert(trustedTimes.some(element => containsIdentifier(element, 'businessDate')), 'business date time element missing');
  assert(trustedTimes.some(element => containsIdentifier(element, 'at')), 'local read time element missing');

  const metricButton = jsxElements(nodes, 'button', 'bos-monitor-open');
  assert.equal(metricButton.length, 1, 'metric navigation button missing');
  const disabled = jsxAttribute(metricButton[0], 'disabled')?.value?.expression;
  assert(expressionHasReadyAndAllowed(disabled), 'metric navigation must require ready and metric.allowed');

  const selects = jsxElements(nodes, 'select');
  assert.equal(selects.length, 1, 'monitor must not add a branch selector');
  assert.equal(literalValue(jsxAttribute(selects[0], 'aria-label')?.value), 'Валюта моніторингу', 'monitor select must be currency only');
}

function assertGuardedNavigation(home) {
  const nodes = functionNodes(home);
  const monitorUse = jsxElements(nodes, 'BosGlobalMonitor');
  assert.equal(monitorUse.length, 1, 'BosGlobalMonitor usage missing');
  const businessDate = jsxAttribute(monitorUse[0], 'businessDate')?.value?.expression;
  assert.equal(nodeName(businessDate), 'businessDate', 'monitor must receive validated business date');

  const guardedNavigation = nodes.find(node => node.type === 'ArrowFunctionExpression'
    && containsCall(node.body, 'canUse')
    && containsCall(node.body, 'available')
    && containsCall(node.body, 'onNavigate'));
  assert(guardedNavigation, 'monitor navigation must retain canUse and available guards');
  assert(nodes.some(node => node.type === 'CallExpression' && nodeName(node.callee) === 'homeBusinessDate'), 'business date must be validated before use');
}

function main() {
  const source = path.resolve(readArgument('--source'));
  const expectedCommit = readArgument('--commit').toLowerCase();
  const expectedHash = readArgument('--sha256').toLowerCase();
  assert.match(expectedCommit, /^[0-9a-f]{40}$/, 'commit must be a full SHA-1');
  assert.match(expectedHash, /^[0-9a-f]{64}$/, 'sha256 must be lowercase hexadecimal');
  assert(source.endsWith(path.join('frontend', 'boss_app_source.html')), 'source must be frontend/boss_app_source.html');
  assert(fs.existsSync(source), 'source file missing');

  const repo = path.resolve(path.dirname(source), '..');
  assert.equal(git(repo, ['status', '--porcelain']), '', 'target checkout is not clean');
  assert.equal(git(repo, ['rev-parse', 'HEAD']).toLowerCase(), expectedCommit, 'target commit mismatch');
  const html = fs.readFileSync(source, 'utf8');
  assert.equal(sha256(html), expectedHash, 'full source SHA-256 mismatch');

  const ast = parseAst(repo, babelBody(html));
  const monitor = functionDeclaration(ast, 'BosGlobalMonitor');
  const home = functionDeclaration(ast, 'BoSHome');
  assertMetricModel(home);
  assertMonitorDisclosure(monitor);
  assertGuardedNavigation(home);
  process.stdout.write(JSON.stringify({
    status: 'PASS',
    classification: 'NEW_AST_PRESENTATION_DISCLOSURE',
    source,
    commit: expectedCommit,
    sha256: expectedHash,
    checks: ['five-metric-provenance', 'ready-disclosure', 'time-caveats', 'guarded-navigation'],
  }) + '\n');
}

main();
