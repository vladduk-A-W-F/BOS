"""Draft A09 owned-bootstrap filesystem acceptance; genuine files, no SQL/server."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/install_server.py'
spec = importlib.util.spec_from_file_location('a09_install_server_draft', MODULE)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class OwnedInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bos-a09-own-installs-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / 'package'
        (self.source/'boss_project').mkdir(parents=True)
        (self.source/'boss_project/version.py').write_text("VERSION = '0.2.8-dev'\n")
        (self.source/'requirements.txt').write_text('Django==6.0.5\n')
        (self.source/'manage.py').write_text('# synthetic package metadata only\n')
        self.registry = self.work/'installer-state'
        self.target = self.work/'company-a'

    def run_install(self, **options):
        values=dict(target=self.target, registry=self.registry, source_root=self.source,origin='https://bos.example.test')
        values.update(options)
        return installer.prepare_install(**values)

    def files(self, root):
        return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_existing_empty_and_foreign_targets_refused_without_registry_creation(self):
        self.target.mkdir()
        with self.assertRaises(installer.InstallRefused): self.run_install()
        self.assertFalse(self.registry.exists())
        canary=self.target/'client-data.bin'
        canary.write_bytes(b'keep client data')
        with self.assertRaises(installer.InstallRefused): self.run_install()
        self.assertEqual(canary.read_bytes(),b'keep client data')
        self.assertFalse(self.registry.exists())

    def test_symlink_paths_and_nested_source_or_registry_refused(self):
        outside=self.work/'outside'
        outside.mkdir()
        link=self.work/'linked-parent'
        link.symlink_to(outside,target_is_directory=True)
        for target in (link/'company',self.source/'new-company',self.registry):
            with self.subTest(target=target), self.assertRaises(installer.InstallRefused):
                self.run_install(target=target)
        self.assertFalse(self.registry.exists())
        self.assertEqual(list(outside.iterdir()),[])
        self.target.symlink_to(outside,target_is_directory=True)
        with self.assertRaises(installer.InstallRefused):self.run_install()
        self.assertTrue(self.target.is_symlink())
        self.assertFalse(self.registry.exists())

    def test_own_partial_claim_and_config_resume_keep_id_secret_and_existing_bytes(self):
        first=self.run_install(stop_after='claim')
        self.assertEqual(self.files(self.target),{})
        second=self.run_install(resume=first['installation_id'],stop_after='config')
        before=self.files(self.target)
        self.assertEqual(set(before),{'config/server.json'})
        third=self.run_install(resume=first['installation_id'])
        self.assertEqual(first['installation_id'],second['installation_id'])
        self.assertEqual(second['installation_id'],third['installation_id'])
        self.assertEqual((self.target/'config/server.json').read_bytes(),before['config/server.json'])
        self.assertEqual(set(self.files(self.target)),{'config/server.json','INSTALLATION.json'})
        again=self.run_install(resume=first['installation_id'])
        self.assertEqual(third,again)
        self.assertFalse((self.target/'state/data/bos.sqlite3').exists())
        self.assertFalse(third['complete'])
        self.assertEqual(third['exit_code'],2)

    def test_two_roots_have_unique_ids_secrets_and_disjoint_paths(self):
        first=self.run_install()
        target_b=self.work/'company-b'
        second=self.run_install(target=target_b,origin='https://second.example.test')
        a=json.loads((self.target/'config/server.json').read_text())
        b=json.loads((target_b/'config/server.json').read_text())
        for field in ('BOS_INSTALLATION_ID','BOS_SECRET_KEY','BOS_DATABASE_PATH','BOS_MEDIA_ROOT'):
            self.assertNotEqual(a[field],b[field])
        for config in (a,b):
            self.assertGreaterEqual(len(config['BOS_SECRET_KEY']),50)
            self.assertGreaterEqual(len(set(config['BOS_SECRET_KEY'])),12)
            self.assertEqual(config['BOS_DATA_MODE'],'working')
            self.assertEqual(config['DJANGO_SETTINGS_MODULE'],'server_settings')
        self.assertNotIn(a['BOS_SECRET_KEY'],json.dumps(first))
        self.assertNotIn(b['BOS_SECRET_KEY'],json.dumps(second))
        if os.name=='posix':
            for root in (self.target,target_b,self.registry): self.assertEqual(root.stat().st_mode&0o777,0o700)
            for root in (self.target,target_b):
                for path in root.rglob('*'):
                    self.assertEqual(path.stat().st_mode&0o777,0o700 if path.is_dir() else 0o600)

    def test_copied_foreign_marker_or_replaced_root_does_not_authorize_resume(self):
        first=self.run_install()
        foreign=self.work/'foreign'
        shutil.copytree(self.target,foreign)
        before=self.files(foreign)
        with self.assertRaises(installer.InstallRefused):self.run_install(target=foreign,resume=first['installation_id'])
        self.assertEqual(self.files(foreign),before)
        old=self.work/'owned-original'
        self.target.rename(old)
        shutil.copytree(old,self.target)
        replaced=self.files(self.target)
        with self.assertRaises(installer.InstallRefused):self.run_install(resume=first['installation_id'])
        self.assertEqual(self.files(self.target),replaced)
        self.assertEqual(self.files(old),replaced)

    def test_nested_existing_installation_unknown_files_and_changed_config_refused(self):
        first=self.run_install()
        with self.assertRaises(installer.InstallRefused):self.run_install(target=self.target/'nested')
        self.assertFalse((self.target/'nested').exists())
        unknown=self.target/'foreign.bin'
        unknown.write_bytes(b'foreign bytes')
        before=self.files(self.target)
        with self.assertRaises(installer.InstallRefused):self.run_install(resume=first['installation_id'])
        self.assertEqual(self.files(self.target),before)
        unknown.unlink()
        config=self.target/'config/server.json'
        config.write_bytes(config.read_bytes()+b'changed')
        before=self.files(self.target)
        with self.assertRaises(installer.InstallRefused):self.run_install(resume=first['installation_id'])
        self.assertEqual(self.files(self.target),before)

    def test_different_source_version_is_not_an_implicit_upgrade(self):
        first=self.run_install(stop_after='claim')
        before=self.files(self.target)
        (self.source/'boss_project/version.py').write_text("VERSION = '99.0'\n")
        with self.assertRaises(installer.InstallRefused):self.run_install(resume=first['installation_id'])
        self.assertEqual(self.files(self.target),before)

    def test_concurrent_installer_process_cannot_enter_owned_registry(self):
        first=self.run_install(stop_after='claim')
        before=self.files(self.target)
        owner=installer.InstallerRegistry(self.registry)
        with owner.lock():
            run=subprocess.run([sys.executable,str(MODULE),'--target',str(self.target),
                '--registry',str(self.registry),'--source-root',str(self.source),'--origin','https://bos.example.test',
                '--resume',first['installation_id']],capture_output=True,text=True,check=False)
        self.assertEqual(run.returncode,3,run.stdout+run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'],'refused')
        self.assertEqual(self.files(self.target),before)
        resumed=self.run_install(resume=first['installation_id'])
        self.assertEqual(resumed['installation_id'],first['installation_id'])

    def test_cli_reports_incomplete_nonzero_without_exposing_secret(self):
        run=subprocess.run([sys.executable,str(MODULE),'--target',str(self.target),
            '--registry',str(self.registry),'--source-root',str(self.source),'--origin','https://bos.example.test'],
            capture_output=True,text=True,check=False)
        self.assertEqual(run.returncode,2,run.stdout+run.stderr)
        report=json.loads(run.stdout)
        self.assertFalse(report['complete'])
        self.assertTrue(all(check['status']=='НЕ ВИКОНАНО' for check in report['checks'].values()))
        secret=json.loads((self.target/'config/server.json').read_text())['BOS_SECRET_KEY']
        self.assertNotIn(secret,run.stdout+run.stderr)


if __name__=='__main__':unittest.main(verbosity=2)
