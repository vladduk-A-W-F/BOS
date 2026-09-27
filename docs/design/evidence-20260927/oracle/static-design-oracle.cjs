/* Read-only static oracle for the BoS 3 light-design candidate. */
'use strict';

const fs = require('fs');
const path = require('path');

const root = path.resolve(process.argv[2] || 'C:/Users/user/.codex/worktrees/bos3-product-design/repo');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');
const failures = [];
let checks = 0;

function need(value, description) {
  checks += 1;
  if (!value) failures.push(description);
}
function includes(text, token, description) { need(text.includes(token), description); }
function excludes(text, token, description) { need(!text.includes(token), description); }

const source = read('frontend/boss_app_source.html');
const css = read('frontend/bos_design.css');
const build = read('scripts/build_frontend.cjs');
const html = read('frontend/boss_app_html.html');

// Build wiring and offline-delivery boundary.
includes(source, '<!-- BOS_DESIGN_STYLES -->', 'source must retain the BOS_DESIGN_STYLES insertion point');
includes(build, "'frontend/bos_design.css'", 'build must read the shared design stylesheet');
includes(build, 'BOS_DESIGN_STYLES', 'build must replace the design placeholder');
includes(html, '/* BoS 3 · shared product design.', 'compiled output must inline the shared design stylesheet');
includes(html, css, 'compiled output must contain the exact current shared design stylesheet');
need(html.indexOf('/* BoS 3 · shared product design.') < html.indexOf('<script src="/assets/app.js"></script>'), 'inlined design CSS must precede the compiled application script');
excludes(html, 'fonts.googleapis.com', 'compiled HTML must not depend on Google Fonts');
excludes(html, 'fonts.gstatic.com', 'compiled HTML must not depend on Google Fonts static assets');
includes(html, '<script src="/assets/react.js"></script>', 'compiled HTML must keep the local React runtime');
includes(html, '<script src="/assets/react-dom.js"></script>', 'compiled HTML must keep the local React DOM runtime');

// Product behavior is present in the candidate; this oracle only checks that
// the build and style layer have not removed its real navigation/API hooks.
includes(source, 'function bosNavigation()', 'existing navigation handler must remain in product source');
includes(source, 'function bosCan(', 'existing capability handler must remain in product source');
includes(source, "fetch('/api/auth/me/')", 'existing authenticated-session route must remain in product source');
includes(source, "fetch('/api/operations/status/')", 'existing status route must remain in product source');
includes(source, "function Bos3TrainingHub", 'actual training component must remain in product source');
includes(source, "function ERPWorkspace", 'actual ERP workspace component must remain in product source');
includes(source, "function CRMWorkspace", 'actual CRM workspace component must remain in product source');

// Static visual regression guards for the redesigned, light hierarchy.
includes(css, '@media(min-width:1201px)', 'desktop rail media query must be present');
includes(css, '.bos-app { display:grid!important;', 'desktop rail must use the application shell');
includes(css, '.nav-dropdown,.nav-dropdown.open', 'desktop rail must style existing navigation disclosures');
includes(source, '.nav-dropdown[hidden]{display:none}', 'existing disclosure hidden behavior must remain');
includes(source, 'aria-expanded={hasSubs', 'existing disclosure ARIA control must remain');
includes(source, 'focusCurrentContent()', 'existing navigation focus handoff must remain');
includes(css, '.bos-light-brand .bos-mark', 'entry brand mark contrast rule must be present');
includes(css, '.bos-preview-case{', 'entry case-card rule must be present');
need(/a\.bos-preview-case\s*,\s*a\.bos3-case-link\s*\{[^}]*text-decoration\s*:\s*none\s*;/s.test(css), 'entry card anchors must explicitly remove default underlines');
need(/\.bos-next\s*\{/.test(css), 'shared next-action surface rule must be present');
includes(css, '.bos-click-row:hover', 'shared click-row hover rule must be present');
need(/\.network-map\s*\{/.test(css), 'network-map light surface rule must be present');
includes(css, '.network-pin', 'network pin contrast rule must be present');
excludes(css, '#1c2835', 'legacy dark next-action color must not survive in shared design CSS');
excludes(css, '#242e3d', 'legacy dark click-row hover color must not survive in shared design CSS');
excludes(css, '#0A0C10', 'legacy dark canvas color must not survive in shared design CSS');

const summary = { classification: 'NEW static design wiring review', checks, failures, source: root };
console.log(JSON.stringify(summary, null, 2));
if (failures.length) process.exitCode = 1;
