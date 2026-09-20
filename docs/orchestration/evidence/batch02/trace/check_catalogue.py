"""Read-only resolver/discovery wiring, not a check_access sweep or gate PASS."""
import collections, hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
from uuid import uuid4
root=Path(__file__).resolve().parent/'source'
with tempfile.TemporaryDirectory(prefix='bos-trace-catalogue-') as tmp:
    w=Path(tmp)
    os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings', BOS_VERIFY_DB='sqlite',
        BOS_TEST_DB_NAME=str(w/('check_'+uuid4().hex+'.sqlite3')), BOS_TEST_MEDIA=str(w/'media'),
        BOS_PROJECT_ROOT=str(w/'project'), BOS_DATA_MODE='demo', PYTHONDONTWRITEBYTECODE='1')
    sys.path.insert(0,str(root))
    import django
    django.setup()
    from django.conf import settings
    settings.ROOT_URLCONF = 'boss_project.server_urls'  # Same profile as check_access.main.
    from django.db import connection
    from scripts.check_access import catalogue, signature
    # Any cursor is forbidden: resolver enumeration/discovery must not query a DB.
    from unittest.mock import patch
    with patch.object(connection, 'cursor', side_effect=AssertionError('Read-only wiring must not open DB')):
        manifest=json.loads((root/'scripts/access_routes.json').read_text())
        actual=catalogue()
        actual_counter=collections.Counter(map(signature,actual)); expected_counter=collections.Counter(map(signature,manifest['patterns']))
        if actual_counter != expected_counter:
            print(json.dumps({'only_actual':list((actual_counter-expected_counter).elements()),'only_manifest':list((expected_counter-actual_counter).elements())}))
        assert actual_counter==expected_counter
        def flattened(suite):
            for test in suite:
                if isinstance(test,unittest.TestSuite): yield from flattened(test)
                else: yield test.id()
        discovered=sorted(flattened(unittest.TestLoader().loadTestsFromName('erp.test_order_trace')))
        required=sorted(x for x in manifest['required_field_tests'] if x.startswith('erp.test_order_trace.'))
        assert discovered==required,(discovered,required)
        assert len(discovered)==18
    assert not list(w.glob('*.sqlite3*'))
    result={'resolver_patterns':len(actual),'manifest_patterns':len(manifest['patterns']),
            'exact_signature_counter_equal':True,'discovered_new_test_ids':discovered,
            'exact_required_new_test_ids_equal':True,'database_cursor_calls':0,
            'database_files_created':0,'test_methods_run':0,'scope':'resolver/discovery only; no access sweep, no gate PASS'}
    out=Path(__file__).resolve().parent/'CATALOGUE_WIRING.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
