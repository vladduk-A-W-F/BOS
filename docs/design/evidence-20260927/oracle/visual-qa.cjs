/*
 * BoS 3.0 offline visual QA.
 *
 * This file deliberately has no web server.  Playwright intercepts every
 * request, serves the candidate's own compiled browser assets from disk, and
 * fulfils only synthetic read fixtures.  Any non-GET API call is refused.
 * It is a styling/layout review harness, not a workflow or acceptance test.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { chromium } = require('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

const DEFAULT_SOURCE = 'C:/Users/user/.codex/worktrees/bos3-product-design/repo';
const QA_ROOT = __dirname;
const NOW = '2026-09-27T12:00:00Z';
const ACCESS = 'offline-visual-qa-r1';
const OFFLINE_ORIGIN = 'https://bos3.qa';
const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 1000, deviceScaleFactor: 1 },
  { name: 'mobile', width: 390, height: 844, deviceScaleFactor: 1 },
];

function usage() {
  console.log(`Usage: node visual-qa.cjs --source <candidate-root> [--out <folder>] [--plan]\n\n` +
    'No server is started.  The normal run opens a locally installed browser and writes only to --out.');
}

function readArg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function requireFile(file, label) {
  if (!fs.existsSync(file)) throw new Error(`${label} is missing: ${file}`);
  return file;
}

function candidateFiles(source) {
  const assets = path.join(source, 'assets');
  return {
    html: requireFile(path.join(source, 'frontend', 'boss_app_html.html'), 'compiled application HTML'),
    content: requireFile(path.join(source, 'frontend', 'bos3_content.json'), 'BoS 3 content'),
    design: requireFile(path.join(source, 'frontend', 'bos_design.css'), 'shared design stylesheet'),
    app: requireFile(path.join(assets, 'app.js'), 'compiled application JS'),
    react: requireFile(path.join(assets, 'react.js'), 'local React runtime'),
    reactDom: requireFile(path.join(assets, 'react-dom.js'), 'local React DOM runtime'),
    marked: requireFile(path.join(assets, 'marked.js'), 'local marked runtime'),
    purify: requireFile(path.join(assets, 'purify.js'), 'local DOMPurify runtime'),
    networkMap: requireFile(path.join(assets, 'network-map.js'), 'local network map'),
    entryImage: requireFile(path.join(assets, 'bos3-fasteners-entry.png'), 'entry illustration'),
  };
}

function requireCurrentCompiledDesign(files) {
  const compiled = fs.readFileSync(files.html, 'utf8');
  const design = fs.readFileSync(files.design, 'utf8');
  if (!compiled.includes(design)) {
    throw new Error('Compiled HTML does not contain the exact current bos_design.css; rebuild before visual QA.');
  }
}

function nearestExistingAncestor(target) {
  let current = target;
  while (!fs.existsSync(current)) {
    const parent = path.dirname(current);
    if (parent === current) throw new Error(`No existing ancestor for output path: ${target}`);
    current = parent;
  }
  return current;
}

function response(status, value) {
  return { status, value, headers: { 'X-BoS-Access': ACCESS, 'X-BoS-Identity': 'accepted' } };
}

function fixtureState(content) {
  const first = content.cases[0];
  const employees = [
    { id: 11, full_name: 'Олена Коваль', name: 'Олена Коваль', role: 'Керівниця', dept: 'Управління', department: 'Управління', branch: 1, branch_name: 'Управління', archived_at: null, kpi: 92, phone: '+380 44 555 01 01', email: 'olena@example.test' },
    { id: 12, full_name: 'Андрій Марченко', name: 'Андрій Марченко', role: 'Менеджер продажів', dept: 'Продажі', department: 'Продажі', branch: 2, branch_name: 'Продажі', archived_at: null, kpi: 84, phone: '+380 44 555 01 02', email: 'andriy@example.test' },
  ];
  // The Sales screen and the original InitialImportDialog both read this
  // object directly.  Keep related IDs and arrays coherent, even where a
  // selected visual surface does not render every array.
  const snapshot = {
    as_of: '2026-09-27',
    employees,
    branches: [{ id: 1, name: 'Управління' }, { id: 2, name: 'Продажі' }],
    partners: [
      { id: 501, code: 'CUST-OFFLINE', name: 'ТОВ «ФасадСервіс»', type: 'customer' },
      { id: 502, code: 'SUP-OFFLINE', name: 'ТОВ «ПромКріплення»', type: 'supplier' },
    ],
    items: [{ id: 101, code: 'FAST-500', name: 'Кріплення M8', unit: 'шт.', revision: 'A', kind: 'product', method: 'buy', material: 'Сталь', bom: [], routing: [], external_codes: {}, required_documents: [], minimum: 50, planned_cost: 12, currency: 'UAH' }],
    locations: [{ id: 201, code: 'WH-KYIV', name: 'Склад Київ', kind: 'warehouse', branch_id: 2, supplier_id: null }],
    orders: [{ id: 401, code: 'SO-OFFLINE-001', customer_id: 501, owner_id: 12, status: 'confirmed', due_date: '2026-10-03', currency: 'UAH', fulfillment_location_id: 201, destination_country: 'UA', notes: 'Синтетичний рядок для візуальної перевірки.' }],
    lines: [{ id: 601, order_id: 401, item_id: 101, quantity: 500, shipped: 120, cancelled_quantity: 0, returned_quantity: 0, price: 48, revision: 'A', open_quantity: 380 }],
    lots: [], purchases: [], jobs: [], invoices: [], events: [{ id: 901, action: 'erp_order', created_at: '2026-09-27T09:00:00Z', role: 'ceo', result: { code: 'SO-OFFLINE-001' } }],
    costs: [], inspections: [], changes: [], transfers: [], reservations: [], documents: [], movements: [], replenishment: [], supplier_scores: [], operator_entries: [],
    source_movements: [], invoice_adjustments: [], supplier_claims: [], retentions: [], requests: [],
    plans: [], summary: { orders: 1, jobs: 0, blocked_lots: 0, review_jobs: 0 },
  };
  const steps = (first.presentation.handoffs || []).map((handoff, index) => ({
    id: handoff.step_id,
    status: index === 0 ? 'available' : 'locked',
    title: handoff.department,
    prompt: handoff.action,
    evidence: { passed: false, observed: handoff.control },
    answer_fields: index === 0 ? [{ id: 'source', label: 'Перевірене джерело', type: 'text', required: true }] : [],
  }));
  return {
    unknownGets: [],
    runtime: {
      authenticated: true,
      user_id: 901,
      employee_id: 11,
      role: 'ceo',
      mode: 'training',
      as_of: '2026-09-27',
      access_revision: ACCESS,
      training_enabled: true,
      // Controls may be visible for visual review.  The route layer still
      // rejects every mutation before it reaches any application service.
      capabilities: { write: true, finance: true, hr_private: true, export_workspace: false, view_documents: true },
    },
    training: {
      available: true,
      content,
      cases: content.cases.map(item => ({ case_id: item.id, status: item.id === first.id ? 'available' : 'not_started' })),
    },
    session: {
      session_id: 'offline-visual-session-supply',
      case_id: first.id,
      status: 'in_progress',
      learning_mode: 'read_only',
      current_step: steps[0]?.id,
      steps,
      facts: {
        client: first.presentation.client,
        product: first.presentation.product,
        order_quantity: '500',
        washer_shortage: '120',
      },
      sources: [{ label: 'Навчальний набір', value: 'bos3-fasteners-uk-v1' }],
    },
    employees,
    tasks: [
      { id: 701, title: 'Узгодити наступний контакт щодо залишку 6 400 грн', description: 'Навчальне доручення для візуального перегляду.', status: 'process', priority: 'high', deadline: '2026-09-30', assignee_id: 12, assignee: 'Андрій Марченко', assignee_name: 'Андрій Марченко', category: 'Продажі', branch: 2, branch_name: 'Продажі', order_id: 401, order_code: 'SO-OFFLINE-001', result: null, handoff: null, is_overdue: false, archived: false, archived_at: null },
      { id: 702, title: 'Перевірити документ заблокованої партії', description: 'Статус якості не змінюється у стенді.', status: 'active', priority: 'medium', deadline: '2026-10-01', assignee_id: 11, assignee: 'Олена Коваль', assignee_name: 'Олена Коваль', category: 'Навчання', branch: 1, branch_name: 'Управління', order_id: null, order_code: '', result: '', handoff: null, is_overdue: false, archived: false, archived_at: null },
    ],
    crm: { items: [{ id: 41, title: 'ТОВ «ФасадСервіс» · відкритий залишок', stage: 'collection', next_action: 'Узгодити дату оплати 6 400 грн', owner: { id: 12, name: 'Андрій Марченко' }, case_id: 'BOS3-CASE-03', counterparty: { id: 501, name: 'ТОВ «ФасадСервіс»' }, order: { id: 401, code: 'SO-OFFLINE-001' }, invoice: { id: 801, code: 'INV-OFFLINE-001' }, contact: { id: 71, name: 'Ірина Савчук' }, activities: [{ id: 91, kind: 'follow_up', summary: 'Уточнити дату оплати', status: 'planned', owner: { id: 12, name: 'Андрій Марченко' }, due_date: '2026-09-30' }] }] },
    snapshot,
  };
}

function apiFixture(url, method, state, signedIn) {
  if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
    return response(405, { error: 'Offline visual QA is read-only: mutation intentionally refused.' });
  }
  const route = url.pathname;
  if (route === '/api/auth/csrf/') return response(200, { mode: 'training', training_enabled: true, csrfToken: 'offline-only' });
  if (route === '/api/auth/me/') return signedIn ? response(200, { authenticated: true }) : response(401, { error: 'Offline entry view has no session.' });
  if (route === '/api/operations/status/') return response(200, state.runtime);
  if (route === '/api/training/content/') return response(200, state.training);
  if (/^\/api\/training\/sessions\/BOS3-CASE-01\/$/.test(route)) return response(200, state.session);
  if (/^\/api\/training\/sessions\//.test(route)) return response(200, { ...state.session, case_id: url.pathname.includes('CASE-02') ? 'BOS3-CASE-02' : state.session.case_id });
  if (route === '/api/employees/') return response(200, state.employees);
  if (route === '/api/tasks/') return response(200, state.tasks);
  if (route === '/api/branches/') return response(200, [{ id: 1, name: 'Управління', type: 'department', children: [{ id: 2, name: 'Продажі', type: 'department', children: [] }] }]);
  if (route === '/api/dashboard/summary/') return response(200, { metrics: {}, employees: [], tasks: state.tasks, alerts: [] });
  if (route === '/api/crm/') return response(200, state.crm);
  if (/^\/api\/crm\/deals\//.test(route)) return response(200, { ...state.crm.items[0], activities: [], sources: [] });
  if (route === '/api/erp/modules/') return response(200, { modules: [] });
  if (route === '/api/erp/snapshot/') return response(200, state.snapshot);
  if (route === '/api/erp/orders/401/next/') return response(200, { title: 'Перевірити забезпечення замовлення', why: 'Синтетичний наступний крок для візуального перегляду.', payload: null });
  if (/^\/api\/(counterparties|contracts|transactions|salaries)\/$/.test(route)) return response(200, []);
  if (route === '/api/runtime/status/') return response(200, { ai_configured: false });
  state.unknownGets.push(route + url.search);
  return response(404, { error: `No offline visual fixture is registered for ${route}.` });
}

function mime(file) {
  return ({ '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.png': 'image/png' })[path.extname(file)] || 'application/octet-stream';
}

async function wireOfflinePage(page, files, state, signedIn) {
  const assets = {
    '/assets/app.js': files.app,
    '/assets/react.js': files.react,
    '/assets/react-dom.js': files.reactDom,
    '/assets/marked.js': files.marked,
    '/assets/purify.js': files.purify,
    '/assets/network-map.js': files.networkMap,
    '/assets/bos3-fasteners-entry.png': files.entryImage,
  };
  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.hostname !== 'bos3.qa') return route.abort('blockedbyclient');
    if (url.pathname.startsWith('/api/')) {
      const item = apiFixture(url, request.method(), state, signedIn);
      return route.fulfill({ status: item.status, contentType: 'application/json; charset=utf-8', headers: item.headers, body: JSON.stringify(item.value) });
    }
    if (url.pathname === '/' || url.pathname === '/index.html') return route.fulfill({ path: files.html, contentType: mime(files.html) });
    const local = assets[url.pathname];
    if (local) return route.fulfill({ path: local, contentType: mime(local) });
    return route.fulfill({ status: 404, contentType: 'text/plain', body: 'Offline visual QA fixture has no such resource.' });
  });
}

async function waitForApp(page) {
  await page.waitForFunction(() => document.querySelector('#root')?.textContent?.trim().length > 30, null, { timeout: 15_000 });
  await page.waitForTimeout(300);
}

async function capture(page, diagnostics, output, label, report, fullPage = true) {
  await page.screenshot({ path: path.join(output, `${label}.png`), fullPage });
  const overflow = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth > window.innerWidth + 1,
    main: [...document.querySelectorAll('[data-bos-main], .erp-workspace, .bos3-start')].some(node => node.scrollWidth > node.clientWidth + 1),
  }));
  report.screens.push({ label, overflow, consoleErrors: [...diagnostics.consoleErrors], pageErrors: [...diagnostics.pageErrors], expectedEntryAuth401: diagnostics.expectedEntryAuth401 });
}

async function openPage(browser, files, state, scenario, viewport, trainingSlug = 'supply') {
  const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height }, deviceScaleFactor: viewport.deviceScaleFactor });
  // Secure context is required by the product's existing erpPendingBinding()
  // guard for window.crypto.subtle. The routed origin still never connects.
  await context.addCookies([{ name: 'csrftoken', value: 'offline-visual-csrf', url: OFFLINE_ORIGIN, sameSite: 'Lax' }]);
  const page = await context.newPage();
  const diagnostics = { consoleErrors: [], pageErrors: [], expectedEntryAuth401: 0 };
  page.on('response', response => {
    if (scenario === 'entry' && response.url() === `${OFFLINE_ORIGIN}/api/auth/me/` && response.status() === 401) diagnostics.expectedEntryAuth401 += 1;
  });
  page.on('console', msg => {
    const expectedGuestAuthNotice = scenario === 'entry'
      && diagnostics.expectedEntryAuth401 > 0
      && msg.text() === 'Failed to load resource: the server responded with a status of 401 (Unauthorized)';
    if (msg.type() === 'error' && !expectedGuestAuthNotice) diagnostics.consoleErrors.push(msg.text());
  });
  page.on('pageerror', error => diagnostics.pageErrors.push(String(error)));
  await wireOfflinePage(page, files, state, scenario !== 'entry');
  const parameters = new URLSearchParams();
  if (scenario === 'entry') parameters.set('training', trainingSlug);
  if (scenario === 'runner') parameters.set('training', 'supply');
  await page.goto(`${OFFLINE_ORIGIN}/?${parameters}`, { waitUntil: 'networkidle' });
  await waitForApp(page);
  if (scenario === 'entry' && diagnostics.expectedEntryAuth401 < 1) throw new Error('Guest entry did not receive the expected synthetic /api/auth/me/ 401 response.');
  return { context, page, diagnostics };
}

async function clickText(page, text) {
  const candidates = await page.getByRole('button', { name: text, exact: false }).all();
  for (const locator of candidates) {
    if (await locator.isVisible()) { await locator.click(); await page.waitForTimeout(250); return true; }
  }
  return false;
}

async function requireClick(page, text, label = text) {
  if (!await clickText(page, text)) throw new Error(`Required visible control is absent: ${label}`);
}

async function closeActualDialog(page) {
  const dialog = page.locator('dialog[open]').first();
  const close = dialog.getByRole('button', { name: 'Закрити', exact: true });
  try {
    await close.click();
    await page.locator('dialog[open]').waitFor({ state: 'hidden', timeout: 5_000 });
  } catch {
    throw new Error('Actual ERP modal did not close through its visible Закрити control.');
  }
}

async function requireVisible(page, selector, label) {
  const locator = page.locator(selector).first();
  try {
    await locator.waitFor({ state: 'visible', timeout: 5_000 });
  } catch {
    throw new Error(`Expected visual anchor is absent: ${label} (${selector})`);
  }
}

async function requireNormalSurface(page, label) {
  const alerts = page.locator('[role="alert"]:visible');
  if (await alerts.count()) throw new Error(`Unexpected visible alert on normal surface: ${label}: ${await alerts.first().innerText()}`);
  const boundary = page.getByRole('heading', { name: 'Щось пішло не так', exact: true });
  if (await boundary.count()) throw new Error(`ErrorBoundary recovery is visible on normal surface: ${label}`);
}

async function requireScrollable(page, selector, label) {
  const result = await page.locator(selector).evaluate(node => ({
    scrollHeight: node.scrollHeight,
    clientHeight: node.clientHeight,
    overflowY: getComputedStyle(node).overflowY,
  }));
  if (result.scrollHeight <= result.clientHeight + 1 || !['auto', 'scroll'].includes(result.overflowY)) {
    throw new Error(`Expected independently scrollable surface is absent: ${label}`);
  }
}

async function navigate(page, section, sub = null) {
  const mobile = page.locator('select.bos-mobile-nav');
  if (await mobile.isVisible()) {
    await mobile.selectOption(`${section}:${sub || ''}`);
    await page.waitForTimeout(300);
    return;
  }
  const labels = { info: 'Про систему', erp: 'ERP', hr: 'HR', crm: 'CRM' };
  const trigger = page.getByRole('button', { name: labels[section] || section, exact: true }).first();
  await trigger.click();
  const subLabels = { sales: 'Продажі', tasks: 'Доручення' };
  if (sub) await page.getByRole('button', { name: subLabels[sub] || sub, exact: true }).last().click();
  await page.waitForTimeout(300);
}

async function run(files, output, remainingOnly = false) {
  const content = JSON.parse(fs.readFileSync(files.content, 'utf8'));
  const state = fixtureState(content);
  if (fs.existsSync(output)) {
    if (fs.readdirSync(output).length) throw new Error(`Output directory must be new and empty: ${output}`);
  } else fs.mkdirSync(output, { recursive: true });
  const source = { root: path.dirname(path.dirname(files.html)), appSha256: sha256(files.app), htmlSha256: sha256(files.html), contentSha256: sha256(files.content) };
  let continuation = null;
  if (remainingOnly) {
    const reusedFrom = path.join(QA_ROOT, 'artifacts-run2', 'visual-qa-report.json');
    const prior = JSON.parse(fs.readFileSync(reusedFrom, 'utf8'));
    if (JSON.stringify(prior.source) !== JSON.stringify(source) || prior.unknownGets?.length || prior.screens?.some(screen => screen.overflow?.document || screen.overflow?.main || screen.consoleErrors?.length || screen.pageErrors?.length)) {
      throw new Error('Run2 evidence cannot be reused for this targeted continuation.');
    }
    continuation = { reusedFrom, reusedSource: prior.source, inheritedLabels: prior.screens.map(screen => screen.label) };
  }
  const report = {
    classification: 'NEW visual styling validation',
    scope: 'Offline synthetic render only; no functional acceptance of historical capped progress, payment, network, E2E, browser, PG, full-suite, or column workflows.',
    source,
    viewports: VIEWPORTS,
    screens: [],
    unknownGets: state.unknownGets,
    readOnly: 'Non-GET API requests receive 405 from the in-memory fixture router.',
    ...(continuation ? { continuation } : {}),
  };
  let browser = null;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
  } catch (error) {
    browser = await chromium.launch({ headless: true });
    report.browserFallback = `msedge unavailable: ${String(error)}`;
  }
  try {
    for (const viewport of VIEWPORTS) {
      const captureEntryAndRunner = !remainingOnly || viewport.name === 'mobile';
      const captureErp = !remainingOnly || viewport.name === 'mobile';
      if (captureEntryAndRunner) for (const caseDef of content.cases) {
        const { context, page, diagnostics } = await openPage(browser, files, state, 'entry', viewport, caseDef.slug);
        await requireVisible(page, `h1, h2`, `entry heading for ${caseDef.id}`);
        await requireVisible(page, '.bos-preview-path', `entry handoff path for ${caseDef.id}`);
        await requireVisible(page, `a.bos-preview-case[href*="${caseDef.slug}"]`, `entry case link for ${caseDef.id}`);
        await requireNormalSurface(page, `entry ${caseDef.id}`);
        await requireScrollable(page, '.bos-entry-shell', 'entry shell');
        await capture(page, diagnostics, output, `entry-${caseDef.slug}-${viewport.name}-hero`, report, false);
        await page.locator('.bos-preview-path').scrollIntoViewIfNeeded();
        await capture(page, diagnostics, output, `entry-${caseDef.slug}-${viewport.name}-handoff`, report, false);
        await page.locator('.bos-light-login').scrollIntoViewIfNeeded();
        await requireVisible(page, '.bos-light-login-form', 'entry login form');
        await capture(page, diagnostics, output, `entry-${caseDef.slug}-${viewport.name}-login`, report, false);
        await context.close();
      }
      if (captureEntryAndRunner) {
        const { context, page, diagnostics } = await openPage(browser, files, state, 'runner', viewport);
        await navigate(page, 'info');
        await requireVisible(page, '.bos3-runner', 'actual Bos3CaseRunner');
        await requireVisible(page, '.bos3-steps', 'runner step list');
        await requireNormalSurface(page, 'training runner');
        await capture(page, diagnostics, output, `runner-supply-${viewport.name}`, report);
        await context.close();
      }
      {
        const { context, page, diagnostics } = await openPage(browser, files, state, 'workspace', viewport);
        if (captureErp) {
          await navigate(page, 'erp', 'sales');
          await requireVisible(page, '.erp-workspace', 'ERP workspace');
          await requireVisible(page, 'h2', 'ERP sales heading');
          await requireVisible(page, 'text=Продажі та виконання замовлень', 'ERP sales surface heading');
          await requireVisible(page, 'text=SO-OFFLINE-001', 'known synthetic ERP sales order');
          await requireVisible(page, '.erp-table tbody tr', 'non-empty ERP sales table row');
          await requireNormalSurface(page, 'ERP sales');
          await capture(page, diagnostics, output, `workspace-erp-table-${viewport.name}`, report);
          await requireClick(page, 'Початковий імпорт', 'ERP modal trigger');
          await requireVisible(page, 'dialog[open]', 'actual ERP modal');
          await requireVisible(page, 'dialog form', 'actual ERP modal form');
          await requireVisible(page, 'dialog select', 'actual ERP modal owner selector');
          await requireNormalSurface(page, 'ERP initial-import modal');
          await capture(page, diagnostics, output, `workspace-modal-${viewport.name}`, report);
          await closeActualDialog(page);
        }
        await navigate(page, 'crm');
        await requireVisible(page, '.crm-workspace', 'CRM workspace');
        await requireVisible(page, '.crm-list button', 'non-empty CRM list');
        await requireVisible(page, 'text=ТОВ «ФасадСервіс» · відкритий залишок', 'known synthetic CRM deal');
        await page.getByRole('button', { name: 'ТОВ «ФасадСервіс» · відкритий залишок', exact: false }).first().click();
        await requireVisible(page, '.crm-detail-header', 'selected actual CRM detail');
        await requireVisible(page, '.crm-form', 'actual CRM detail form');
        await requireNormalSurface(page, 'CRM workspace');
        await capture(page, diagnostics, output, `workspace-crm-${viewport.name}`, report);
        await navigate(page, 'hr', 'tasks');
        await requireVisible(page, '.c01-current', 'non-empty task card');
        await requireVisible(page, 'text=Узгодити наступний контакт щодо залишку 6 400 грн', 'known synthetic task');
        await requireNormalSurface(page, 'HR tasks');
        await capture(page, diagnostics, output, `workspace-hr-tasks-${viewport.name}`, report);
        await context.close();
      }
    }
  } finally {
    if (browser) await browser.close();
    fs.writeFileSync(path.join(output, 'visual-qa-report.json'), JSON.stringify(report, null, 2) + '\n');
  }
  const invalid = report.screens.filter(screen => screen.overflow.document || screen.overflow.main || screen.consoleErrors.length || screen.pageErrors.length);
  if (state.unknownGets.length || invalid.length) {
    const reasons = [
      state.unknownGets.length && `unregistered GET fixtures: ${[...new Set(state.unknownGets)].join(', ')}`,
      invalid.length && `invalid visual captures: ${invalid.map(item => item.label).join(', ')}`,
    ].filter(Boolean);
    throw new Error(reasons.join('; '));
  }
}

function main() {
  if (process.argv.includes('--help')) { usage(); return; }
  const source = path.resolve(readArg('--source', DEFAULT_SOURCE));
  const output = path.resolve(readArg('--out', path.join(QA_ROOT, 'artifacts')));
  const relativeOutput = path.relative(QA_ROOT, output);
  if (relativeOutput === '' || relativeOutput.startsWith('..') || path.isAbsolute(relativeOutput)) {
    throw new Error(`--out must be a descendant of the isolated staging root: ${QA_ROOT}`);
  }
  const qaReal = fs.realpathSync(QA_ROOT);
  const outputParentReal = fs.realpathSync(nearestExistingAncestor(output));
  const relativeReal = path.relative(qaReal, outputParentReal);
  if (relativeReal.startsWith('..') || path.isAbsolute(relativeReal)) {
    throw new Error(`--out resolves outside the isolated staging root: ${outputParentReal}`);
  }
  const files = candidateFiles(source);
  requireCurrentCompiledDesign(files);
  const plan = {
    classification: 'NEW visual styling validation',
    source,
    output,
    browser: 'Playwright with installed Edge, then bundled Chromium fallback',
    viewports: VIEWPORTS,
    screenshots: ['entry × 3 cases × desktop/mobile', 'training runner × desktop/mobile', 'ERP table/form, modal, CRM, HR/tasks × desktop/mobile'],
    safeguards: ['no server', 'no network', 'candidate assets loaded directly from disk', 'in-memory synthetic GET fixtures only', 'all API mutations return 405'],
  };
  if (process.argv.includes('--plan')) { console.log(JSON.stringify(plan, null, 2)); return; }
  run(files, output, process.argv.includes('--remaining')).catch(error => { console.error(error.stack || String(error)); process.exitCode = 1; });
}

main();
