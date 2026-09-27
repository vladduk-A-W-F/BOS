/*
 * B30-04F NEW static UI oracle.
 *
 * Usage (only when independently authorized):
 *   node check_b30_04f_entry_brochure.cjs <absolute-path-to-boss_app_source.html>
 *
 * This parser parses the actual JSX and examines its AST. It does not open a
 * browser, load the application, call fetch, access a server, or write files.
 */
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const sourcePath = process.argv[2];
if (!sourcePath || !path.isAbsolute(sourcePath)) {
  throw new Error('Provide one absolute boss_app_source.html path.');
}
const html = fs.readFileSync(sourcePath, 'utf8');
const script = html.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
if (!script) throw new Error('JSX entrypoint is missing.');

const sourceRoot = path.dirname(path.dirname(sourcePath));
const registryPath = path.join(sourceRoot, 'frontend', 'bos3_content.json');
function sha256File(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}
const babel = require(path.join(sourceRoot, 'assets', 'babel.js'));
const jsx = script[1].replace('{% verbatim %}', '').replace('{% endverbatim %}', '');
const parsed = babel.transform(jsx, {
  ast: true,
  code: false,
  parserOpts: {plugins: ['jsx']},
  filename: path.basename(sourcePath),
});
const program = parsed.ast.program;
let checks = 0;
function check(label, fn) {
  fn();
  checks += 1;
  console.log('PASS ' + label);
}
function walk(node, visit) {
  if (!node || typeof node !== 'object') return;
  visit(node);
  for (const [key, value] of Object.entries(node)) {
    if (key === 'loc' || key === 'start' || key === 'end' || key === 'extra') continue;
    if (Array.isArray(value)) value.forEach(item => walk(item, visit));
    else walk(value, visit);
  }
}
function directWalk(node, visit) {
  if (!node || typeof node !== 'object') return;
  visit(node);
  for (const [key, value] of Object.entries(node)) {
    if (key === 'loc' || key === 'start' || key === 'end' || key === 'extra') continue;
    const items = Array.isArray(value) ? value : [value];
    for (const item of items) {
      if (!item || typeof item !== 'object') continue;
      if ((item.type === 'FunctionDeclaration' || item.type === 'FunctionExpression'
          || item.type === 'ArrowFunctionExpression') && item !== node) continue;
      directWalk(item, visit);
    }
  }
}
function functionNamed(name) {
  let found = null;
  walk(program, node => {
    if (node.type === 'FunctionDeclaration' && node.id && node.id.name === name) found = node;
  });
  assert(found, 'Missing function ' + name);
  return found;
}
function variableFunction(container, name) {
  let found = null;
  directWalk(container.body, node => {
    if (node.type === 'VariableDeclarator' && node.id.type === 'Identifier' && node.id.name === name
        && (node.init?.type === 'ArrowFunctionExpression' || node.init?.type === 'FunctionExpression')) found = node.init;
  });
  assert(found, 'Missing callback ' + name);
  return found;
}
function jsxName(node) {
  if (!node) return null;
  if (node.type === 'JSXIdentifier') return node.name;
  if (node.type === 'JSXMemberExpression') return jsxName(node.object) + '.' + jsxName(node.property);
  return null;
}
function callName(node) {
  if (!node || !['CallExpression', 'OptionalCallExpression'].includes(node.type)) return null;
  if (node.callee.type === 'Identifier') return node.callee.name;
  if (['MemberExpression', 'OptionalMemberExpression'].includes(node.callee.type)
      && node.callee.property.type === 'Identifier') return node.callee.property.name;
  return null;
}
function callsIn(node) {
  const calls = new Set();
  walk(node, item => {
    const name = callName(item);
    if (name) calls.add(name);
  });
  return calls;
}
function directCallsIn(node) {
  const calls = new Set();
  directWalk(node, item => {
    const name = callName(item);
    if (name) calls.add(name);
  });
  return calls;
}
function identifiersIn(node) {
  const names = new Set();
  directWalk(node, item => { if (item.type === 'Identifier') names.add(item.name); });
  return names;
}
function directReturns(fn) {
  const returns = [];
  directWalk(fn.body, node => { if (node.type === 'ReturnStatement') returns.push(node); });
  return returns;
}
function jsxOpenings(node, name) {
  const results = [];
  directWalk(node, item => {
    if (item.type === 'JSXOpeningElement' && jsxName(item.name) === name) results.push(item);
  });
  return results;
}
function jsxAttributes(opening, name) {
  return opening.attributes.filter(attribute => attribute.type === 'JSXAttribute' && jsxName(attribute.name) === name);
}
function attributeCallback(attribute) {
  const expression = attribute?.value?.expression;
  assert(expression, 'Expected callback expression for ' + jsxName(attribute.name));
  return expression;
}
function resolveCallback(attribute, container) {
  return resolveCallbackExpression(attributeCallback(attribute), container);
}
function resolveCallbackExpression(expression, container) {
  if (expression.type === 'ArrowFunctionExpression' || expression.type === 'FunctionExpression') return expression;
  if (expression.type === 'Identifier') return variableFunction(container, expression.name);
  throw new Error('Callback must be inline or name a callback declared in its component.');
}
function callbackExpression(attribute) {
  const expression = attributeCallback(attribute);
  if (expression.type === 'ArrowFunctionExpression' || expression.type === 'FunctionExpression'
      || expression.type === 'Identifier') return expression;
  throw new Error('Callback must be inline or an identifier.');
}
function isReactStateSetter(expression) {
  return expression?.type === 'Identifier' && /^set[A-Z]/.test(expression.name);
}
function literalValues(node) {
  const values = new Set();
  directWalk(node, item => {
    if (item.type === 'StringLiteral') values.add(item.value);
  });
  return values;
}
function ifTests(fn) {
  const values = [];
  directWalk(fn.body, item => { if (item.type === 'IfStatement') values.push(item.test); });
  return values;
}
function hasGuard(fn, names) {
  return ifTests(fn).some(test => names.every(name => identifiersIn(test).has(name)));
}
function forbidden(node, context) {
  const calls = directCallsIn(node);
  for (const name of ['fetch', 'trainingFetch', 'crmFetch', 'opFetch', 'localStorage']) {
    assert(!calls.has(name), context + ' must not perform ' + name + '.');
  }
  const persistent = [];
  directWalk(node, item => {
    if (['CallExpression', 'OptionalCallExpression'].includes(item.type)
        && ['MemberExpression', 'OptionalMemberExpression'].includes(item.callee.type)
        && item.callee.object.type === 'Identifier' && item.callee.object.name === 'localStorage') {
      persistent.push(item.callee.property.type === 'Identifier' ? item.callee.property.name : '<computed>');
    }
  });
  assert.equal(persistent.length, 0, context + ' must not persist to localStorage: ' + persistent.join(', '));
}
function hasNew(node, name) {
  let found = false;
  walk(node, item => {
    if (item.type === 'NewExpression' && item.callee.type === 'Identifier' && item.callee.name === name) found = true;
  });
  return found;
}

const content = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
check('registry is the expected public brochure catalog', () => {
  assert.equal(content.schema, 'bos.training.content.v1');
  assert.equal(content.areas.length, 11);
  assert.deepEqual(content.cases.map(item => item.id), ['BOS3-CASE-01', 'BOS3-CASE-02', 'BOS3-CASE-03']);
});

const authGate = functionNamed('AuthGate');
const authReturns = directReturns(authGate);
const entryReturn = authReturns.find(item => jsxOpenings(item.argument, 'Bos3Brochure').length > 0);
check('unauthenticated entry return contains brochure before password form', () => {
  assert(entryReturn, 'AuthGate has no unauthenticated brochure return.');
  const brochures = jsxOpenings(entryReturn.argument, 'Bos3Brochure');
  const passwordReferences = [];
  directWalk(entryReturn.argument, node => {
    if (node.type === 'Identifier' && node.name === 'passwordForm') passwordReferences.push(node);
  });
  assert(brochures.length >= 1, 'No entry brochure component found.');
  const pdfFlags = brochures.flatMap(opening => jsxAttributes(opening, 'showBrochurePdf'));
  assert(pdfFlags.some(flag => flag.value?.expression?.type === 'BooleanLiteral'
      && flag.value.expression.value === false),
    'Public entry must explicitly suppress the protected brochure PDF link.');
  assert(passwordReferences.length >= 1, 'Existing password login form is not retained.');
  assert(Math.min(...brochures.map(node => node.start)) < Math.min(...passwordReferences.map(node => node.start)),
    'Brochure must precede the password form in the unauthenticated entry tree.');
  assert(!hasGuard(authGate, ['ready']) || authReturns.some(item => jsxOpenings(item.argument, 'App').length > 0),
    'Authenticated workspace branch is not retained.');
});

check('entry case intent is URL-only and has no write side effect', () => {
  const brochures = jsxOpenings(entryReturn.argument, 'Bos3Brochure');
  const callbacks = brochures.flatMap(opening => jsxAttributes(opening, 'onSelectCase')
    .map(callbackExpression));
  assert(callbacks.length >= 1, 'Entry brochure needs onSelectCase intent callback.');
  for (const callback of callbacks) {
    // AuthGate is allowed to receive an ordinary React state setter. The URL
    // mutation belongs to Bos3Brochure.selectCase below, not to AuthGate.
    if (isReactStateSetter(callback)) continue;
    forbidden(resolveCallbackExpression(callback, authGate), 'Entry case selection');
  }
});

const caseCards = functionNamed('Bos3CaseCards');
check('case links preserve a case slug without training or CRM mutation', () => {
  const clickAttributes = [];
  walk(caseCards.body, node => {
    if (node.type === 'JSXAttribute' && jsxName(node.name) === 'onClick') clickAttributes.push(node);
  });
  const callbacks = clickAttributes.map(attribute => resolveCallback(attribute, caseCards));
  assert(callbacks.length >= 1, 'Case card click callback is missing.');
  assert(callbacks.some(callback => directCallsIn(callback).has('preventDefault') && directCallsIn(callback).has('onSelect')),
    'Case click must prevent native navigation and notify its parent with the case slug.');
  callbacks.forEach(callback => forbidden(callback, 'Case click'));
});

const brochure = functionNamed('Bos3Brochure');
check('brochure itself is read-only and surfaces both areas and cases', () => {
  forbidden(brochure, 'Brochure rendering');
  const selectCase = variableFunction(brochure, 'selectCase');
  const selectCalls = directCallsIn(selectCase);
  assert(selectCalls.has('bos3SetSlug') && selectCalls.has('onSelectCase'),
    'Brochure must write validated URL intent and notify its entry parent.');
  forbidden(selectCase, 'Brochure case intent');
  const branches = directReturns(brochure).filter(branch =>
    jsxOpenings(branch.argument, 'Bos3AreaGrid').length || jsxOpenings(branch.argument, 'Bos3CaseCards').length);
  assert.equal(branches.length, 2, 'Brochure must retain exactly one entry and one authenticated render branch.');
  for (const branch of branches) {
    assert.equal(jsxOpenings(branch.argument, 'Bos3AreaGrid').length, 1,
      'Each brochure render branch must contain one area grid.');
    assert.equal(jsxOpenings(branch.argument, 'Bos3CaseCards').length, 1,
      'Each brochure render branch must contain one case-card set.');
  }
});

const slugReader = functionNamed('bos3Slug');
const trainingHub = functionNamed('Bos3TrainingHub');
check('authenticated training consumes the same validated URL intent', () => {
  const slugCalls = callsIn(trainingHub);
  assert(slugCalls.has('bos3Slug'), 'Training hub must consume selected case intent.');
  assert(hasNew(slugReader, 'URLSearchParams'), 'Case intent must be read from URL state.');
  assert(literalValues(slugReader).has('training'), 'Case intent must remain the training URL parameter.');
});

const enter = variableFunction(authGate, 'enter');
check('training login preserves password gate and denies demo entry', () => {
  const literals = literalValues(enter);
  assert(literals.has('/api/auth/login/'), 'Password login endpoint is missing.');
  assert(literals.has('/api/auth/demo/'), 'Demo endpoint branch is missing.');
  assert(hasGuard(enter, ['demo', 'trainingEnabled']), 'Training demo denial guard is missing.');
});

console.log(JSON.stringify({
  result: 'PASS',
  checks,
  scope: 'B30-04F AST-only entry brochure, case URL intent, and non-mutation boundary; no browser, network, server, DB, fixture, lifecycle, or historical suite',
  source: path.resolve(sourcePath),
  source_sha256: sha256File(sourcePath),
  registry_sha256: sha256File(registryPath),
}, null, 2));
