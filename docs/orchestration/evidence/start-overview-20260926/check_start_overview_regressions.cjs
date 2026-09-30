// Four focused regressions found by independent review of V18-START-OVERVIEW.
// Parses actual JSX with the bundled Babel runtime; no app server or browser.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const rootFlag = process.argv.indexOf('--root');
assert.notEqual(rootFlag, -1, 'Pass --root <candidate-path>.');
const root = path.resolve(process.argv[rootFlag + 1] || '');
const html = fs.readFileSync(path.join(root, 'frontend', 'boss_app_source.html'), 'utf8');
const babel = require(path.join(root, 'assets', 'babel.js'));

function slice(prefix, endMarker) {
  const start = html.indexOf(prefix);
  const end = html.indexOf(endMarker, start);
  assert(start !== -1 && end !== -1 && end > start, `Cannot isolate ${prefix}.`);
  return html.slice(start, end);
}

const home = slice('function BoSHome(', 'function BoSProductGuide(');
const gate = slice('function AuthGate(', 'ReactDOM.createRoot');
const app = slice('function App(', 'function AuthGate(');
babel.transform(home, { presets: ['react'], compact: false });
babel.transform(gate, { presets: ['react'], compact: false });
babel.transform(app, { presets: ['react'], compact: false });

const passed = [];
function test(name, check) {
  check();
  passed.push(name);
  console.log(`PASS ${name}`);
}

test('overdue KPI preserves its distinct filtered selection', () => {
  assert.match(home, /\['Прострочені доручення',overdue\.length,'tasks',true\]/);
  assert.match(home, /\.map\(\(\[title,n,key,late\]\)=>/);
  assert.match(home, /open\(\{kind:'list',key,title,overdue:late\}\)/);
  // The list is rendered in the adjacent inspector component, not BoSHome.
  assert.match(html, /selection\.overdue\?t\.is_overdue===true:t\.status!=='done'/);
});

test('one credential form has the universal auth layout in both modes', () => {
  assert.match(gate, /const passwordForm=<form className="bos-auth-form"/);
  assert.match(gate, /<details className="bos-auth-secondary"[^>]*>.*?\{passwordForm\}<\/details>/s);
  assert.match(gate, /<\/\>:passwordForm\}/);
  assert.match(html, /\.bos-auth-form\{display:grid;gap:14px\}/);
  assert.match(html, /\.bos-auth-secondary \.bos-auth-form\{margin-top:14px\}/);
});

test('daily view exposes the same selected currency used by its invoice filter', () => {
  const header = home.slice(home.indexOf('return <div className="bos-home">'), home.indexOf('<section aria-label="Свіжість робочого огляду"'));
  assert.match(header, /\{financial&&<Select aria-label=\{readOnlyOverview\?'Валюта показників':'Валюта рахунків'\}/);
  assert.doesNotMatch(header, /\{readOnlyOverview&&financial&&<Select/);
  assert.match(header, /onChange=\{e=>\{select\(null\);life\.current\.nextSelection=null;setCurrency\(e\.target\.value\);\}\}/);
  assert.match(home, /data\.invoices\.filter\(x=>x\.currency===cur\)/);
});

test('route-specific component keys clear hidden overview state on navigation', () => {
  assert.match(app, /if\(section==='heli'\)\s*return\s*<BoSHome key="heli-overview" readOnlyOverview/);
  assert.match(app, /if\(section==='dash'\)\s*return\s*<BoSHome key="today-work" focus/);
  assert.notEqual('heli-overview', 'today-work');
});

console.log(JSON.stringify({
  schema: 'bos.v18.start-overview-regressions.v1',
  result: 'PASS',
  checks: passed,
  scope: 'actual JSX Babel parse plus exact regression assertions; no server, TCP, database, browser, or product writes',
}, null, 2));
