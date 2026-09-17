"""Build an exact code-only server package in a NEW directory. No database reads."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat

ROOTS = ('boss_project', 'operations', 'erp', 'finance', 'employees', 'branches',
         'tasks', 'ai_assistant', 'scripts', 'assets', 'static', 'frontend', 'deploy')
EXTENSIONS = {'.py', '.js', '.cjs', '.css', '.html', '.json', '.svg', '.png', '.ico',
              '.woff', '.woff2', '.ttf', '.txt', '.sh', '.ps1', '.bat', '.yml', '.yaml'}
TOP = ('manage.py', 'demo_settings.py', 'server_settings.py', 'verification_settings.py',
       'requirements.txt', 'requirements-server.txt', 'requirements-ci.txt',
       'docs/KNOWLEDGE_UA.md', 'docs/PARAMETERS_UA.md')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode() + b'\n'


def package(source, output):
    source, output = Path(source), Path(output)
    if not source.is_absolute() or not output.is_absolute() or '..' in output.parts:
        raise ValueError('Потрібні абсолютні шляхи без переходів до батьків.')
    for path in (source, output):
        for parent in (*reversed(path.parents), path):
            if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
                raise ValueError('Посилання у шляхах пакета заборонено.')
    if output == source or source in output.parents or output in source.parents or output.exists():
        raise ValueError('Пакет потребує нового окремого каталогу поза джерелом.')
    paths = [source / name for name in TOP if (source / name).is_file()]
    for name in ROOTS:
        base = source / name
        for path in base.rglob('*'):
            rel = path.relative_to(source)
            if path.is_symlink():
                raise ValueError('Посилання у джерелі пакета заборонено.')
            if any(part.startswith('.') or part == '__pycache__' for part in rel.parts):
                continue
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                paths.append(path)
    contents = {}
    for path in sorted(set(paths)):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Джерело має містити окремі звичайні файли.')
        contents[path.relative_to(source).as_posix()] = path.read_bytes()
    for required in ('boss_project/version.py', 'scripts/install_server.py', 'scripts/start_server.py',
                     'server_settings.py', 'requirements-server.txt'):
        if required not in contents:
            raise ValueError('Джерело не містить повного серверного коду.')
    versions = [node.value.value for node in ast.parse(contents['boss_project/version.py']).body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in node.targets)]
    if len(versions) != 1 or not isinstance(versions[0], str):
        raise ValueError('Неоднозначна версія коду.')
    manifest = {'format': 'BoS-source-package-1', 'version': versions[0],
                'files': {rel: hashlib.sha256(data).hexdigest() for rel, data in contents.items()}}
    manifest['source_sha256'] = hashlib.sha256(canonical(manifest)).hexdigest()
    # Exclusive creation: a failed build is retained, never overwritten or removed.
    output.mkdir(mode=0o700)
    for rel, data in {**contents, 'BOS_PACKAGE.json': canonical(manifest)}.items():
        dest = output / rel
        dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
    return {'version': versions[0], 'source_sha256': manifest['source_sha256'],
            'files': len(contents), 'database_files': 0, 'output': str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(package(args.source, args.output), ensure_ascii=False))
    except (OSError, ValueError) as error:
        print(json.dumps({'complete': False, 'reason': str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
