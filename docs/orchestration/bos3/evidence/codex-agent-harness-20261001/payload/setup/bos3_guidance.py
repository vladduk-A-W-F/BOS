"""Bounded read-only BoS 3.0 card projection for the explicit legacy `next` command."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess


BOSDEV = Path('D:/3/BOSDev').resolve()
CANONICAL = BOSDEV / 'workspaces/bos3-canonical/repo'
GIT = Path('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe')
DELTA = BOSDEV / 'release-planning/bos-3.0-20260927/POST_CHECKPOINT_OPERATIONAL_DELTA.json'
RECEIPT = BOSDEV / 'evidence/resume-solutions-20260930/integrator/GC06_APPLIED_RECEIPT_20261001.json'
DOCS = ('docs/orchestration/QUEUE.json', 'docs/orchestration/STATE.json',
        'docs/orchestration/bos3/CONTROL_STATE.json',
        'docs/orchestration/bos3/ACTIVE_WORK_PLAN_RU.md')
PRODUCT_FILES = ('training/service.py', 'training/test_sessions.py')
GC06 = 'GUIDED-LEARNING-GC-F06-CURRENT-STEP-SOURCE-20261001'
MAX_SOURCE_BYTES = 256 * 1024
MAX_REFERENCE_BYTES = 2 * 1024 * 1024
MAX_RESULT_BYTES = 32 * 1024
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


class Reconcile(Exception):
    """A source discrepancy means no product proposal is safe to render."""


def require(condition, code):
    if not condition:
        raise Reconcile(code)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(raw, label):
    require(isinstance(raw, bytes) and len(raw) <= MAX_SOURCE_BYTES, label + '_size')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, label + '_duplicate_key')
            out[key] = value
        return out
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique,
                           parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (UnicodeError, ValueError) as exc:
        raise Reconcile(label + '_malformed') from exc
    require(isinstance(value, dict), label + '_object')
    return value


def text(value, label, limit=512):
    require(isinstance(value, str) and 0 < len(value) <= limit, label + '_text')
    return value


def hexpin(value, label, pattern=HEX64):
    require(isinstance(value, str) and pattern.fullmatch(value) is not None, label + '_hash')
    return value


def optional_pin(value, label):
    return None if value is None else hexpin(value, label, HEX40 if label.endswith('_sha') else HEX64)


def bounded_list(value, label, maximum=8):
    require(isinstance(value, list) and len(value) <= maximum, label + '_count')
    return [text(item, label + '_item', 600) for item in value]


def allowed_reference_path(value):
    path = Path(text(value, 'reference_path', 300))
    require(path.is_absolute(), 'reference_not_absolute')
    resolved = path.resolve()
    require(resolved.is_relative_to(BOSDEV) and resolved != BOSDEV, 'reference_outside_bosdev')
    return resolved


def reference(path, expected, digest):
    resolved = allowed_reference_path(path)
    pin = hexpin(expected, 'reference')
    require(digest(resolved) == pin, 'reference_hash_mismatch')
    return {'path': str(resolved), 'sha256': pin, 'verified': True}


def optional_reference(record, path_key, hash_key, digest):
    path, pin = record.get(path_key), record.get(hash_key)
    require((path is None) == (pin is None), 'reference_pair_missing')
    return None if path is None else reference(path, pin, digest)


def _track(record, digest):
    require(isinstance(record, dict), 'track_object')
    card = text(record.get('id'), 'card_id', 160)
    workspace = allowed_reference_path(record.get('workspace'))
    dependencies = bounded_list(record.get('dependencies'), 'dependencies')
    allowlist = bounded_list(record.get('allowlist', []), 'allowlist', 16)
    require(len(allowlist) == len(set(allowlist)), 'duplicate_allowlist')
    result = {
        'card_id': card,
        'owner_thread': text(record.get('owner_thread'), 'owner_thread', 80),
        'reviewer_thread': text(record.get('reviewer_thread'), 'reviewer_thread', 80)
                           if record.get('reviewer_thread') is not None else None,
        'workspace': str(workspace),
        'source_base': hexpin(record.get('base_sha'), 'base_sha', HEX40),
        'planned_status': text(record.get('status'), 'planned_status', 160),
        'dependencies': dependencies,
        'allowlist': allowlist,
        'allowlist_recorded': 'allowlist' in record,
        'done_when': text(record.get('done_when'), 'done_when', 800),
        'allowed_checks': text(record.get('allowed_checks'), 'allowed_checks', 500),
        'execution_disposition': (text(record['execution_disposition'], 'execution_disposition', 300)
                                  if 'execution_disposition' in record else None),
        'generated_outputs_accepted': record.get('generated_outputs_accepted'),
        'author_reference': optional_reference(record, 'result_snapshot', 'result_snapshot_sha256', digest),
        'author_manifest_sha256_recorded': optional_pin(record.get('result_manifest_sha256'), 'result_manifest'),
        'review_reference': optional_reference(record, 'review', 'review_sha256', digest),
        'application': None,
        'advice': None,
    }
    return result


def project(bundle, delta_raw, receipt_raw, digest):
    """Pure projection from one immutable Git snapshot and two fixed external records."""
    require(isinstance(bundle, dict), 'bundle_object')
    head = hexpin(bundle.get('head'), 'head', HEX40)
    require(bundle.get('post_head') == head, 'head_changed_during_read')
    require(bundle.get('dirty_docs') == [], 'dirty_document_divergence')
    docs = bundle.get('docs')
    require(isinstance(docs, dict) and set(docs) == set(DOCS), 'docs_missing')
    for path in DOCS:
        hexpin(docs[path].get('sha256') if isinstance(docs[path], dict) else None, 'doc', HEX64)
        hexpin(docs[path].get('worktree_raw_sha256') if isinstance(docs[path], dict) else None,
               'worktree_doc', HEX64)
    queue = strict_json(bundle.get('queue_raw'), 'queue')
    state = strict_json(bundle.get('state_raw'), 'state')
    delta = strict_json(delta_raw, 'operational_delta')
    receipt = strict_json(receipt_raw, 'gc06_receipt')
    current = queue.get('current_bos3')
    execution = state.get('execution')
    require(isinstance(current, dict) and isinstance(execution, dict), 'current_schema_missing')
    require(execution.get('current_assignments') == 'docs/orchestration/QUEUE.json#current_bos3.tracks',
            'queue_authority_mismatch')
    integrator = text(execution.get('shared_git_writer_thread'), 'sole_integrator', 80)
    require(execution.get('shared_git_writer') == 'sole integrator', 'sole_integrator_scope')
    for gate in ('product_execution_allowed', 'automatic_execution_allowed', 'ci_allowed',
                 'deploy_allowed'):
        require(execution.get(gate) is False, 'execution_gate_ambiguous')
    tracks_raw = current.get('tracks')
    require(isinstance(tracks_raw, list) and 1 <= len(tracks_raw) <= 8, 'tracks_count')
    tracks = [_track(item, digest) for item in tracks_raw]
    ids = [item['card_id'] for item in tracks]
    require(len(ids) == len(set(ids)), 'duplicate_card_id')
    source_ancestors = bundle.get('source_ancestors')
    require(isinstance(source_ancestors, dict) and
            all(source_ancestors.get(item['source_base']) is True for item in tracks),
            'source_ancestry_mismatch')
    gc06 = next((item for item in tracks if item['card_id'] == GC06), None)
    require(gc06 is not None, 'gc06_card_missing')
    delta_gc06 = delta.get('gc06_source_integration_20261001')
    require(isinstance(delta_gc06, dict), 'gc06_delta_missing')
    require(delta_gc06.get('receipt') == str(RECEIPT).replace('\\', '/'), 'receipt_path_mismatch')
    require(delta_gc06.get('status') == 'SOURCE_ONLY_APPLIED_COMMITTED_PUSHED_PR11_UPDATED',
            'gc06_delta_status_unknown')
    require(receipt.get('status') == delta_gc06['status'] and receipt.get('card') == GC06,
            'receipt_card_or_status_mismatch')
    require(receipt.get('gc_f06') == 'PARTIAL_CURRENT_STEP_SOURCE_ONLY' and
            delta_gc06.get('gc_f06') == 'PARTIAL_CURRENT_STEP_SOURCE_ONLY; no next_step/dynamic proof',
            'gc06_scope_mismatch')
    require(receipt.get('author') == gc06['owner_thread'] and
            receipt.get('reviewer') == gc06['reviewer_thread'] and
            receipt.get('integrator') == integrator and
            len({receipt.get('author'), receipt.get('reviewer'), receipt.get('integrator')}) == 3,
            'receipt_actor_chain_mismatch')
    require(delta_gc06.get('canonical_head') == receipt.get('integrated_sha') == head,
            'applied_head_mismatch')
    parent = hexpin(delta_gc06.get('parent_documentation_head'), 'parent_head', HEX40)
    require(bundle.get('parent') == parent == receipt.get('canonical_apply_base'),
            'source_parent_mismatch')
    require(receipt.get('author_source_base') == gc06['source_base'],
            'source_ancestry_mismatch')
    require(delta_gc06.get('source_allowlist') == gc06['allowlist'] == list(PRODUCT_FILES),
            'gc06_allowlist_mismatch')
    require(hexpin(delta_gc06.get('review_sha256'), 'delta_review') == receipt.get('review_sha256'),
            'review_hash_mismatch')
    publication = receipt.get('publication')
    require(isinstance(publication, dict) and publication.get('head_sha') == head,
            'publication_head_mismatch')
    require(delta_gc06.get('product_executions') == 0 and delta_gc06.get('qa') == 'NOT_RUN'
            and delta_gc06.get('readiness_change') is False, 'runtime_or_qa_claim_conflict')
    files = receipt.get('files')
    product_blobs = bundle.get('product_blobs')
    require(isinstance(files, list) and len(files) == len(PRODUCT_FILES)
            and isinstance(product_blobs, dict) and set(product_blobs) == set(PRODUCT_FILES),
            'applied_files_missing')
    seen = set()
    for item in files:
        require(isinstance(item, dict) and item.get('path') in PRODUCT_FILES
                and item['path'] not in seen, 'applied_file_path')
        path = item['path']
        seen.add(path)
        actual = product_blobs[path]
        require(item.get('git_blob') == actual.get('git_blob')
                and item.get('committed_lf_sha256') == actual.get('sha256'),
                'applied_blob_hash_mismatch')
        raw_key = 'raw_service_sha256' if path == PRODUCT_FILES[0] else 'raw_tests_sha256'
        require(item.get('reviewed_result_raw_sha256') == delta_gc06.get(raw_key),
                'reviewed_raw_hash_mismatch')
    application = {
        'scope': 'PARTIAL_CURRENT_STEP_SOURCE_ONLY',
        'delta_scope_recorded': delta_gc06['gc_f06'],
        'status': delta_gc06['status'],
        'head': head,
        'receipt': reference(str(RECEIPT), sha256(receipt_raw), digest),
        'review': reference(receipt.get('review'), receipt.get('review_sha256'), digest),
        'author': reference(receipt.get('author_snapshot'), receipt.get('author_snapshot_sha256'), digest),
        'product_qa': 'NOT_RUN', 'runtime_delivery': 'NOT_DELIVERED',
    }
    gc06['application'] = application
    for item in tracks:
        require(item['planned_status'] in ('ACTUAL_CONTEXT_ACCEPTED_AUTHOR_IN_PROGRESS',
                                           'AUTHOR_COMPLETE_UNREVIEWED',
                                           'ACCEPT_SCOPED_STATIC_GENERATION_PACKAGE'),
                'unknown_planned_status')
        if item['application'] is not None:
            require(item['planned_status'] == 'ACTUAL_CONTEXT_ACCEPTED_AUTHOR_IN_PROGRESS',
                    'application_planned_status_mismatch')
            item['advice'] = {'kind': 'REVIEW', 'scope': 'Check later source pin and partial application disposition; no dynamic QA or downstream completion claim'}
        elif item['planned_status'] == 'AUTHOR_COMPLETE_UNREVIEWED':
            item['advice'] = {'kind': 'REVIEW', 'scope': 'Independent design review of recorded author snapshot before dependent assignment'}
        elif item['planned_status'] == 'ACCEPT_SCOPED_STATIC_GENERATION_PACKAGE':
            require(item['generated_outputs_accepted'] is False and
                    isinstance(item['execution_disposition'], str) and
                    item['execution_disposition'].startswith('NOT_ADMITTED'),
                    'journey_executable_scope_ambiguous')
            item['advice'] = {'kind': 'PREPARATION', 'scope': 'Reconcile exact source and admission before any executable generation'}
        else:
            raise Reconcile('unrecognized_advice_scope')
    result = {
        'status': 'SCOPED_CURRENT_CARDS',
        'authority': 'same-head docs/orchestration/QUEUE.json#current_bos3.tracks',
        'canonical_head': head,
        'canonical_docs_sha256': {path: docs[path]['sha256'] for path in DOCS},
        'canonical_docs_worktree_raw_sha256': {path: docs[path]['worktree_raw_sha256'] for path in DOCS},
        'sole_integrator_thread': integrator,
        'execution_gate': 'NO_PRODUCT_OR_AUTOMATIC_EXECUTION',
        'operational_delta_sha256': sha256(delta_raw),
        'gc06_receipt_sha256': sha256(receipt_raw),
        'tracks': tracks,
        'automatic_product_proposals': False,
        'dispatch_performed': False,
        'dynamic_qa_inferred': False,
        'slots_inferred': False,
        'admission_inferred': False,
    }
    require(len(json.dumps(result, ensure_ascii=False).encode('utf-8')) <= MAX_RESULT_BYTES,
            'projection_size')
    return result


def _read_fixed(path, limit=MAX_SOURCE_BYTES):
    require(path.is_file() and path.stat().st_size <= limit, 'fixed_source_missing_or_oversized')
    raw = path.read_bytes()
    require(len(raw) <= limit, 'fixed_source_oversized')
    return raw


def reference_digest(path):
    return sha256(_read_fixed(allowed_reference_path(str(path)), MAX_REFERENCE_BYTES))


class GitReader:
    def _git(self, *args):
        try:
            result = subprocess.run([str(GIT), '--no-optional-locks', '-C', str(CANONICAL), *args],
                                    capture_output=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Reconcile('git_read_unavailable') from exc
        require(result.returncode == 0 and len(result.stdout) <= MAX_SOURCE_BYTES,
                'git_read_failed_or_oversized')
        return result.stdout

    def head(self):
        return text(self._git('rev-parse', 'HEAD').decode('ascii').strip(), 'git_head', 40)

    def parent(self, head):
        return self._git('rev-parse', head + '^').decode('ascii').strip()

    def ancestor(self, older, newer):
        try:
            result = subprocess.run([str(GIT), '--no-optional-locks', '-C', str(CANONICAL),
                                     'merge-base', '--is-ancestor', older, newer],
                                    capture_output=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Reconcile('git_ancestry_unavailable') from exc
        require(result.returncode in (0, 1), 'git_ancestry_error')
        return result.returncode == 0

    def clean_at_head(self, head, path):
        require(path in DOCS, 'nonfixed_git_path')
        try:
            result = subprocess.run([str(GIT), '--no-optional-locks', '-C', str(CANONICAL),
                                     'diff', '--quiet', '--no-ext-diff', head, '--', path],
                                    capture_output=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Reconcile('git_diff_unavailable') from exc
        require(result.returncode in (0, 1), 'git_diff_error')
        return result.returncode == 0

    def blob(self, head, path):
        require(path in DOCS + PRODUCT_FILES, 'nonfixed_git_path')
        blob_id = self._git('rev-parse', head + ':' + path).decode('ascii').strip()
        hexpin(blob_id, 'git_blob', HEX40)
        size = int(self._git('cat-file', '-s', blob_id).decode('ascii').strip())
        require(size <= MAX_SOURCE_BYTES, 'git_blob_oversized')
        raw = self._git('cat-file', 'blob', blob_id)
        require(len(raw) == size, 'git_blob_length_mismatch')
        return {'raw': raw, 'git_blob': blob_id, 'sha256': sha256(raw)}


def read_bundle(reader):
    head = hexpin(reader.head(), 'head', HEX40)
    docs, dirty = {}, []
    for path in DOCS:
        blob = reader.blob(head, path)
        docs[path] = {'sha256': blob['sha256'],
                      'worktree_raw_sha256': sha256(_read_fixed(CANONICAL / path))}
        if not reader.clean_at_head(head, path):
            dirty.append(path)
    queue_raw = reader.blob(head, DOCS[0])['raw']
    state_raw = reader.blob(head, DOCS[1])['raw']
    product_blobs = {path: reader.blob(head, path) for path in PRODUCT_FILES}
    strict_json(state_raw, 'state')
    queue = strict_json(queue_raw, 'queue')
    current = queue.get('current_bos3')
    require(isinstance(current, dict), 'current_schema_missing')
    tracks = current.get('tracks', [])
    require(isinstance(tracks, list), 'tracks_missing')
    require(1 <= len(tracks) <= 8, 'tracks_count')
    bases = {hexpin(track.get('base_sha'), 'track_source_base', HEX40)
             for track in tracks if isinstance(track, dict)}
    require(len(bases) > 0, 'track_sources_missing')
    return {'head': head, 'post_head': reader.head(), 'parent': reader.parent(head),
            'source_ancestors': {base: reader.ancestor(base, head) for base in bases},
            'docs': docs, 'dirty_docs': dirty,
            'queue_raw': queue_raw, 'state_raw': state_raw, 'product_blobs': product_blobs}


def verify_docs_unchanged(reader, bundle):
    require(reader.head() == bundle['head'], 'head_changed_during_projection')
    for path in DOCS:
        require(sha256(_read_fixed(CANONICAL / path)) ==
                bundle['docs'][path]['worktree_raw_sha256'], 'worktree_document_changed_during_read')
        require(reader.clean_at_head(bundle['head'], path), 'dirty_document_divergence')
    require(reader.head() == bundle['head'], 'head_changed_during_projection')


def current_bos3():
    """No sends, writes, model calls, or dynamic product checks."""
    try:
        reader = GitReader()
        bundle = read_bundle(reader)
        delta_raw = _read_fixed(DELTA)
        delta = strict_json(delta_raw, 'operational_delta')
        gc06 = delta.get('gc06_source_integration_20261001')
        require(isinstance(gc06, dict) and gc06.get('receipt') == str(RECEIPT).replace('\\', '/'),
                'receipt_path_mismatch')
        result = project(bundle, delta_raw, _read_fixed(RECEIPT), reference_digest)
        require(sha256(_read_fixed(DELTA)) == sha256(delta_raw), 'operational_delta_changed')
        verify_docs_unchanged(reader, bundle)
        return result
    except (Reconcile, OSError, TypeError, KeyError, OverflowError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, Reconcile) else 'source_read_or_schema_unavailable'
        return {'status': 'NEEDS_RECONCILIATION', 'reason': reason,
                'tracks': [], 'automatic_product_proposals': False,
                'dispatch_performed': False, 'dynamic_qa_inferred': False,
                'slots_inferred': False, 'admission_inferred': False}
