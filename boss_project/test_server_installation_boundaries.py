"""Independent installer trust-boundary regressions on disposable owned files only.

Actual stdlib venv and pip run against an empty local wheelhouse. No network,
application SQL, or existing installation is used. Canonical module paths are resolved from this source package.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

DRAFT = Path(__file__).resolve().parents[1] / 'scripts'

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

installer = load('installer_independent_tests', DRAFT / 'install_server.py')
provision = load('provision_independent_tests', DRAFT / 'provision_runtime.py')


class InstallerTrustBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='a09-independent-boundaries-')
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.source = self.work / 'source'
        (self.source / 'boss_project').mkdir(parents=True)
        (self.source / 'boss_project/version.py').write_text("VERSION='0.2.8-dev'\n")
        (self.source / 'manage.py').write_text('# synthetic source; never execute Django\n')
        (self.source / 'requirements.txt').write_text('Django==6.0.5\n')
        (self.source / 'requirements-server.txt').write_text('-r requirements.txt\nwaitress==3.0.2\n')
        self.target = self.work / 'company-a'
        self.registry = self.work / 'registry'
        self.wheels = self.work / 'wheels'
        self.wheels.mkdir()
        self.pack()

    def pack(self):
        body = {'format': 'BoS-source-package-1', 'version': '0.2.8-dev', 'files': {
            p.relative_to(self.source).as_posix(): installer.sha(p.read_bytes())
            for p in self.source.rglob('*') if p.is_file() and p.name != 'BOS_PACKAGE.json'}}
        (self.source / 'BOS_PACKAGE.json').write_bytes(installer.canonical({**body,
            'source_sha256': installer.sha(installer.canonical(body))}))

    def files(self, root):
        return {p.relative_to(root).as_posix(): installer.sha(p.read_bytes())
                for p in root.rglob('*') if p.is_file()}

    def args(self, **extra):
        values = dict(target=self.target, registry=self.registry,
                      source_root=self.source, origin='https://bos.example.test')
        values.update(extra)
        return values

    def failed_empty_pip(self, **extra):
        with self.assertRaisesRegex(installer.InstallRefused, 'offline-pip'):
            provision.provision_install(installer=installer, wheelhouse=self.wheels, **self.args(**extra))
        self.assertFalse((self.target / 'state/data/bos.sqlite3').exists())
        records = installer.InstallerRegistry(self.registry).records()
        return next(record for record in records if record['root'] == str(self.target))

    def evidence(self, case, **facts):
        print('BOS_A09_INSTALLER_REVIEW_CASE ' + json.dumps({'case': case, **facts}, ensure_ascii=False), flush=True)

    def test_source_registry_all_overlap_directions_refuse_before_writes(self):
        original = self.files(self.source)
        for registry in (self.source / 'new-registry', self.source, self.work):
            with self.subTest(registry=str(registry)), self.assertRaisesRegex(installer.InstallRefused, 'окремими каталогами'):
                installer.prepare_install(**self.args(registry=registry))
            self.assertFalse(self.target.exists())
            self.assertEqual(self.files(self.source), original)
        self.assertFalse((self.source / 'new-registry').exists())
        self.assertFalse((self.work / 'REGISTRY.json').exists())
        self.evidence('source_registry_overlap', refused=3, source_unchanged=True, target_absent=True)

    def module_shadow(self, module):
        marker = self.work / ('unexpected-' + module)
        (self.source / (module + '.py')).write_text("from pathlib import Path\nPath(" + repr(str(marker))
            + ").write_text('SOURCE MODULE MUST NOT RUN DURING BOOTSTRAP')\nraise SystemExit(29)\n")
        self.pack()
        original = self.files(self.source)
        record = self.failed_empty_pip()
        self.assertFalse(marker.exists(), 'Source package shadowed trusted Python bootstrap module')
        self.assertEqual(self.files(self.source), original)
        facts = record['runtime']['commands']
        self.assertEqual([(x['step'], x['returncode']) for x in facts], [('venv', 0), ('offline-pip', 1)])
        self.assertTrue((self.target / 'venv/bin/python').is_file())
        self.evidence(module + '_module_shadow', source_module_executed=False, actual_venv=True,
                      actual_offline_pip_refused=True, database_absent=True, source_unchanged=True)

    def test_source_venv_module_cannot_shadow_bootstrap(self):
        self.module_shadow('venv')

    def test_source_pip_module_cannot_shadow_bootstrap(self):
        self.module_shadow('pip')

    @unittest.skipUnless(os.name == 'posix', 'Exact POSIX executable hardlink regression')
    def test_own_venv_hardlink_cannot_overwrite_second_company(self):
        company_b = self.work / 'company-b'
        other = installer.prepare_install(**self.args(target=company_b, origin='https://b.example.test'))
        record = self.failed_empty_pip()
        self.assertNotEqual(record['id'], other['installation_id'])
        executable = self.target / 'venv/bin' / Path(sys._base_executable).name
        foreign = company_b / 'state/private/client-canary.bin'
        foreign.write_bytes(b'COMPANY B PRIVATE FILE MUST NOT CHANGE')
        foreign.chmod(0o600)
        executable.unlink()
        os.link(foreign, executable)
        b_before = self.files(company_b)
        a_before = self.files(self.target)
        registry_before = self.files(self.registry)
        with self.assertRaisesRegex(installer.InstallRefused, 'жорстке посилання'):
            installer.inspect_partial(record)
        with self.assertRaisesRegex(installer.InstallRefused, 'жорстке посилання'):
            provision.provision_install(installer=installer, wheelhouse=self.wheels, **self.args(resume=record['id']))
        self.assertEqual(self.files(company_b), b_before)
        self.assertEqual(self.files(self.target), a_before)
        self.assertEqual(self.files(self.registry), registry_before)
        self.evidence('venv_hardlink_two_companies', refused=True, company_a_unchanged=True,
                      company_b_unchanged=True, registry_unchanged=True)

    def test_completed_record_refuses_reprovision_before_runtime_changes(self):
        first = installer.prepare_install(**self.args())
        owner = installer.InstallerRegistry(self.registry)
        with owner.lock():
            record = owner.get(first['installation_id'])
            record['runtime']['application_provisioned'] = True
            owner.update(record)
        before = self.files(self.target)
        registry_before = self.files(self.registry)
        for entry in ('bootstrap', 'runtime'):
            with self.subTest(entry=entry), self.assertRaisesRegex(installer.InstallRefused, 'готової інсталяції'):
                if entry == 'bootstrap':
                    installer.prepare_install(**self.args(resume=record['id']))
                else:
                    provision.provision_install(installer=installer, wheelhouse=self.wheels, **self.args(resume=record['id']))
            self.assertEqual(self.files(self.target), before)
            self.assertEqual(self.files(self.registry), registry_before)
        self.assertFalse((self.target / 'venv').exists())
        self.assertFalse((self.target / 'state/data/bos.sqlite3').exists())
        self.evidence('completed_record_no_reprovision', refused=2, bundle_unchanged=True,
                      registry_unchanged=True, venv_absent=True, database_absent=True)

    def test_offline_wheelhouse_file_refuses_before_bootstrap(self):
        links = self.work / 'links.html'
        links.write_text('<html>synthetic local file, not a wheel directory</html>')
        before = self.files(self.source)
        with self.assertRaisesRegex(installer.InstallRefused, 'локальним каталогом'):
            provision.provision_install(installer=installer, wheelhouse=links, **self.args())
        self.assertFalse(self.target.exists())
        self.assertFalse(self.registry.exists())
        self.assertEqual(self.files(self.source), before)
        self.evidence('wheelhouse_directory_required', refused=True, target_absent=True, registry_absent=True)

    def test_offline_metadata_url_cannot_install_outside_unpinned_dependency(self):
        def wheel(directory, name, version, requirement=None):
            filename = directory / (name + '-' + version + '-py3-none-any.whl')
            info = name + '-' + version + '.dist-info/'
            metadata = 'Metadata-Version: 2.1\nName: ' + name + '\nVersion: ' + version + '\n'
            if requirement:
                metadata += 'Requires-Dist: ' + requirement + '\n'
            with zipfile.ZipFile(filename, 'w') as archive:
                archive.writestr(info + 'METADATA', metadata)
                archive.writestr(info + 'WHEEL', 'Wheel-Version: 1.0\nGenerator: synthetic-review\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
                archive.writestr(info + 'RECORD', '')
            return filename
        outside = self.work / 'outside-wheelhouse'
        outside.mkdir()
        extra = wheel(outside, 'synthetic_outside', '0.0.1')
        wheel(self.wheels, 'Django', '6.0.5', 'synthetic-outside @ ' + extra.as_uri())
        wheel(self.wheels, 'waitress', '3.0.2')
        before = self.files(outside)
        with self.assertRaisesRegex(installer.InstallRefused, 'pip-check'):
            provision.provision_install(installer=installer, wheelhouse=self.wheels, **self.args())
        query = "import importlib.metadata as m,json; print(json.dumps(sorted(d.metadata['Name'] for d in m.distributions())))"
        output = subprocess.run([str(self.target/'venv/bin/python'), '-I', '-c', query],
                                capture_output=True, text=True, check=True)
        names = json.loads(output.stdout)
        self.assertNotIn('synthetic_outside', names)
        self.assertEqual(names, ['Django', 'pip', 'waitress'])
        self.assertFalse((self.target / 'state/data/bos.sqlite3').exists())
        self.assertEqual(self.files(outside), before)
        self.evidence('offline_direct_dependency_url', outside_dependency_installed=False,
                      actual_pip_check_refused=True, database_absent=True, outside_files_unchanged=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
