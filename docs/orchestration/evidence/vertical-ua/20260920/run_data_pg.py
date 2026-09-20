import hashlib, json, os, pathlib, subprocess, sys, time, uuid
import psycopg
from psycopg import sql

work = pathlib.Path(__file__).resolve().parent
repo = work.parent / 'bos-fullgit-20260920'
env = dict(os.environ)
env.update(json.loads((work/'pg-secrets/runner-env.json').read_text(encoding='utf-8-sig')))
name = 'bos_verify_' + uuid.uuid4().hex[:16]
env.update(BOS_TEST_DB_NAME=name, BOS_VERIFY_DB='postgres', DJANGO_SETTINGS_MODULE='verification_settings',
           BOS_TEST_MEDIA=str(work/'pg-data-test-media'), BOS_DATA_MODE='demo', PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
output = work/'data-evidence/pg16'
output.mkdir(exist_ok=False)
config = dict(host=env['BOS_PGHOST'], port=env['BOS_PGPORT'], user=env['BOS_PGUSER'], password=env['BOS_PGPASSWORD'])
def digest():
    paths = ['erp/models.py','erp/service.py','erp/queries.py','erp/workpoints.py','erp/views.py','erp/urls.py',
        'boss_project/policy.py','operations/projections.py','erp/migrations/0006_branch_links.py',
        'erp/management/commands/seed_bos_ua.py','erp/test_workpoints.py']
    return {p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in paths}
receipt = {'scope':'VERTICAL-UA-DATA targeted PostgreSQL16 only','allocated_database':name,
           'allocated_test_database':'test_'+name,'source_before':digest(),'full_suite':False,'browser_e2e':False}
with psycopg.connect(dbname='postgres',autocommit=True,**config) as conn:
    with conn.cursor() as c:
        c.execute('SHOW server_version_num'); receipt['server_version_num'] = int(c.fetchone()[0])
        assert 160000 <= receipt['server_version_num'] < 170000
        c.execute('SELECT datname FROM pg_database ORDER BY datname'); before = [r[0] for r in c.fetchall()]
        assert name not in before and 'test_'+name not in before
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        command = [sys.executable,'-X','utf8','manage.py','test','erp.test_workpoints','--settings=verification_settings','--noinput','-v','2']
        receipt['command'] = command
        start=time.monotonic()
        with (output/'raw.log').open('w',encoding='utf-8') as log:
            run=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        receipt.update(exit_code=run.returncode,elapsed_seconds=round(time.monotonic()-start,3))
    finally:
        with conn.cursor() as c:
            for target in ('test_'+name,name):
                c.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(target)))
            c.execute('SELECT datname FROM pg_database ORDER BY datname'); after=[r[0] for r in c.fetchall()]
        receipt['database_inventory_restored']=before==after
        receipt['source_after']=digest()
        receipt['source_unchanged']=receipt['source_before']==receipt['source_after']
        receipt['raw_sha256']=hashlib.sha256((output/'raw.log').read_bytes()).hexdigest()
        (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:receipt[k] for k in ('server_version_num','exit_code','elapsed_seconds','database_inventory_restored','source_unchanged','raw_sha256')}))
sys.exit(receipt['exit_code'])
