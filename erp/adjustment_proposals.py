"""Versioned dependencies for CEO stock adjustment proposals only.

These are state digests, not revision counters. The ERP mutex still serializes
business writers. Legacy proposals and every other action use the global token.
"""
import hashlib
import json
import re

from django.core.serializers.json import DjangoJSONEncoder
from django.core.exceptions import ObjectDoesNotExist

from boss_project.policy import Policy
from operations.models import Document
from operations.private_storage import PrivateFileError, verified_document_bytes
from operations.service import Conflict
from .models import Item, Location, Lot, Movement, Reservation
from .balances import exact

MODE = 'erp_adjust'
VERSION = 1
KEYS = {'mode', 'version', 'payload_sha256', 'dependency_sha256',
        'access_revision', 'effect_sha256', 'impact_sha256'}
HASH_KEYS = KEYS - {'mode', 'version'}
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, cls=DjangoJSONEncoder).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _document_metadata(document):
    row = {field.attname: getattr(document, field.attname)
           for field in Document._meta.fields
           if field.name not in {'content', 'text', 'original_file'}}
    row['original_file'] = document.original_file.name or ''
    row['content_sha256'] = hashlib.sha256(bytes(document.content or b'')).hexdigest()
    row['text_sha256'] = hashlib.sha256(document.text.encode('utf-8')).hexdigest()
    return row


def dependencies(payload, policy):
    """Read complete target sets, including absence and new set membership.

    Existing linked source bytes must be verifiable for scoped mode. Capture may
    choose legacy mode on that known failure; confirm must instead refuse it.
    """
    policy.action(payload)
    lot = Lot.objects.get(pk=payload['lot_id'])
    item = Item.objects.get(pk=lot.item_id)
    linked = set(lot.documents.values())
    if item.document_id is not None:
        linked.add(item.document_id)
    selected = []
    codes = set()
    for identity in sorted(linked):
        document = Document.objects.filter(pk=identity).first()
        if document is None:
            selected.append({'id': identity, 'missing': True})
            continue
        raw = verified_document_bytes(document)
        selected.append({'id': identity, 'bytes_sha256': hashlib.sha256(raw).hexdigest()})
        codes.add(document.code)
    return {
        'mode': MODE, 'version': VERSION, 'payload': payload,
        'access_revision': policy.access_revision(),
        'lot': Lot.objects.filter(pk=lot.pk).values().get(),
        'item': Item.objects.filter(pk=item.pk).values().get(),
        'location': Location.objects.filter(pk=lot.location_id).values().get(),
        'reservations': list(Reservation.objects.filter(lot_id=lot.pk).order_by('pk').values()),
        'movements': list(Movement.objects.filter(lot_id=lot.pk).order_by('pk').values()),
        'selected_documents': selected,
        'document_versions': [_document_metadata(row) for row in
                              Document.objects.filter(code__in=codes).order_by('pk')],
    }


def capture(payload, policy):
    """Only the ERP preview issues this context, before its rollback simulation."""
    if payload.get('action') != MODE:
        return None
    try:
        state = dependencies(payload, policy)
    except PrivateFileError:
        return None
    return {'mode': MODE, 'version': VERSION,
            'payload_sha256': digest(payload),
            'dependency_sha256': digest(state),
            'access_revision': state['access_revision']}


@exact
def snapshot(payload, policy):
    """The same lot fields displayed by queries.snapshot -> experience.impact.

    Adjustment changes no other impact-whitelisted row. Plans, totals, event
    feeds and supplier scores are dashboard context, not adjustment impact.
    """
    from decimal import Decimal
    from .service import accepted_documents, free, reserved, usable
    policy.action(payload)
    lot = Lot.objects.select_related('item').get(pk=payload['lot_id'])
    row = Lot.objects.filter(pk=lot.pk).values().get()
    row.update(reserved=str(reserved(lot)),
               available=str(free(lot) if usable(lot) else Decimal(0)),
               missing_documents=accepted_documents(lot.item, lot.documents))
    return json.loads(json.dumps({'lots': [row]}, cls=DjangoJSONEncoder))


def finish(context, effect, impact):
    return {**context, 'effect_sha256': digest(effect), 'impact_sha256': digest(impact)}


def pending(proposal, policy):
    """Return False only for genuine legacy proposals; bad metadata fails closed."""
    context = proposal.dependency_context
    if context is None:
        return False
    if (not isinstance(context, dict) or set(context) != KEYS
            or context.get('mode') != MODE or type(context.get('version')) is not int
            or context['version'] != VERSION or proposal.payload.get('action') != MODE
            or any(not isinstance(context.get(key), str) or not SHA256.fullmatch(context[key])
                   for key in HASH_KEYS)):
        raise Conflict('Контракт погодження застарів. Підготуйте новий перегляд.')
    if context['payload_sha256'] != digest(proposal.payload):
        raise Conflict('Намір погодження змінився. Підготуйте новий перегляд.')
    try:
        current = dependencies(proposal.payload, policy)
    except (PrivateFileError, ObjectDoesNotExist, ValueError, TypeError) as exc:
        raise Conflict('Джерело погодження змінилося. Підготуйте новий перегляд.') from exc
    if (context['access_revision'] != current['access_revision']
            or context['dependency_sha256'] != digest(current)):
        raise Conflict('Пов’язані дані або права змінилися. Підготуйте новий перегляд.')
    return True


def verify_outcome(proposal, request, result, impact):
    context = proposal.dependency_context
    policy = Policy(request)
    policy.action(proposal.payload)
    effect = {key: value for key, value in result.items() if key != 'erp_event_id'}
    if (policy.access_revision() != context['access_revision']
            or digest(effect) != context['effect_sha256']
            or digest(impact) != context['impact_sha256']):
        raise Conflict('Вплив погодження змінився. Дію не виконано; підготуйте новий перегляд.')
