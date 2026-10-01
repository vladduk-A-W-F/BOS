"""Ліміт доданої документації в PR: docs/ та evidence/ разом."""
import subprocess
import sys

LIMIT_LINES = 500
LIMIT_FILES = 20
PREFIXES = ('docs/', 'evidence/')


def main(base, head):
    out = subprocess.check_output(['git', 'diff', '--numstat', '--no-renames', f'{base}...{head}'], text=True)
    lines = files = 0
    for row in out.splitlines():
        added, _, path = row.split('\t', 2)
        if path.startswith(PREFIXES):
            files += 1
            lines += int(added) if added != '-' else 0
    print(f'docs: +{lines} рядків у {files} файлах (ліміт {LIMIT_LINES} рядків / {LIMIT_FILES} файлів)')
    if lines > LIMIT_LINES or files > LIMIT_FILES:
        print('FAIL: забагато документації. Скоротіть або власник ставить мітку docs-ok.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
