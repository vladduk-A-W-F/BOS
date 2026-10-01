"""Synthetic completeness check for the owner-local source package."""
import ast
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.package_server import package


def main():
    if not __debug__:
        raise RuntimeError('Run package regression checks without -O')
    repository = Path(__file__).resolve().parents[1]
    settings = ast.parse((repository / 'demo_settings.py').read_text(encoding='utf-8'))
    installed = next(ast.literal_eval(node.value) for node in settings.body
                     if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == 'INSTALLED_APPS'
                             for target in node.targets))
    local_apps = {name.split('.')[0] for name in installed
                  if (repository / name.split('.')[0]).is_dir()}
    assert {'crm', 'training'} <= local_apps

    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        source, output = root / 'source', root / 'package'
        source.mkdir()
        expected = {
            'boss_project/version.py': b"VERSION = 'dev.10'\n",
            'scripts/install_server.py': b'# install\n',
            'scripts/start_server.py': b'# start\n',
            'server_settings.py': b'# server\n',
            'requirements-server.txt': b'# requirements\n',
            'bos3_local_settings.py': b'# owner-local settings\r\n',
            'crm/__init__.py': b'',
            'crm/models.py': b'# crm models\n',
            'crm/migrations/0001_initial.py': b'# crm migration\n',
            'training/__init__.py': b'',
            'training/service.py': b'# training service\n',
            'training/models.py': b'# training models\n',
            'training/migrations/0001_initial.py': b'# training migration\n',
            'docs/BoS_3_0_Start_UA.pdf': b'%PDF-1.4\nsynthetic brochure\n',
            'docs/BoS_v18_Start_UA.pdf': b'%PDF-1.4\nsynthetic help\n',
            'docs/BoS_3_0_Start_UA.manifest.json': b'{"synthetic":true}\n',
        }
        for name in local_apps:
            expected[f'{name}/package_marker.py'] = f'{name}: \u0443\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430\n'.encode()
        for relative, data in expected.items():
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for relative in ('db.sqlite3', 'media/private.json', 'crm/.private.py',
                         'training/__pycache__/state.py'):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'private-state')

        report = package(source, output)
        manifest = json.loads((output / 'BOS_PACKAGE.json').read_bytes())
        assert report['files'] == len(expected)
        assert report['database_files'] == 0
        assert manifest['files'] == {name: hashlib.sha256(data).hexdigest()
                                     for name, data in sorted(expected.items())}
        assert {path.relative_to(output).as_posix() for path in output.rglob('*') if path.is_file()} == (
            set(expected) | {'BOS_PACKAGE.json'})
        for relative, data in expected.items():
            assert (output / relative).read_bytes() == data
        before = (output / 'BOS_PACKAGE.json').read_bytes()
        try:
            package(source, output)
        except ValueError:
            pass
        else:
            raise AssertionError('Existing package was overwritten')
        assert (output / 'BOS_PACKAGE.json').read_bytes() == before
        for missing in ('crm/__init__.py', 'training/service.py'):
            (source / missing).unlink()
            missing_output = root / ('missing-' + Path(missing).stem)
            try:
                package(source, missing_output)
            except ValueError:
                pass
            else:
                raise AssertionError(f'Incomplete package was accepted: {missing}')
            assert not missing_output.exists()
            (source / missing).write_bytes(expected[missing])


if __name__ == '__main__':
    main()
