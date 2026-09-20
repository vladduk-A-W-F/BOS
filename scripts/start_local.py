"""Local launcher: recover incomplete installs, retain diagnostics, open browser.
Uses only the standard library until the isolated environment is ready.
"""
import argparse
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / 'BoS_STARTUP.log'
VENV = ROOT / '.venv'
STAMP = VENV / 'bos-requirements.sha256'

def version_ok(version):
    return (3, 12) <= tuple(version[:2]) < (3, 15)

def venv_python():
    return VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

def pick_port():
    for port in range(8000, 8011):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError('Порти 8000–8010 зайняті. Зупиніть інший локальний сервер.')

def emit(message):
    print(message, flush=True)
    with LOG.open('a', encoding='utf-8') as stream:
        stream.write(message + '\n')

def run(command, env):
    with subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace') as proc:
        for line in proc.stdout:
            emit(line.rstrip('\n'))
        code = proc.wait()
    if code:
        raise RuntimeError('Крок завершився з помилкою (%s): %s' % (code, ' '.join(str(c) for c in command[1:3])))

def open_when_ready(url, process):
    # Do not use a proxy for the local application.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(60):
        if process.poll() is not None:
            return
        try:
            with opener.open(url, timeout=1) as response:
                html = response.read(1_000_000)
                if response.status == 200 and b'id="root"' in html and b'/assets/app.js' in html and process.poll() is None:
                    webbrowser.open(url)
                    return
        except (OSError, ValueError):
            pass
        time.sleep(.5)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true', help='Prepare dependencies and check Django without starting a server.')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--original', action='store_true', help='Відкрити окрему робочу копію оригінальної бази')
    args = parser.parse_args()
    LOG.write_text('BoS · локальний запуск\n', encoding='utf-8')
    emit('Python: ' + sys.version.split()[0])
    if not version_ok(sys.version_info):
        raise RuntimeError('Потрібен Python 3.12–3.14. Рекомендовано 3.12.')
    env = dict(os.environ)
    env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', DJANGO_SETTINGS_MODULE='demo_settings', BOS_DATA_MODE='original' if args.original else 'demo')
    # A pre-existing DJANGO_SETTINGS_MODULE must never select production data.
    python = venv_python()
    if not python.is_file():
        emit('Створення окремого середовища…')
        run([sys.executable, '-m', 'venv', str(VENV)], env)
    probe = subprocess.run([str(python), '-c', 'import sys; sys.exit(not ((3,12)<=sys.version_info[:2]<(3,15)))'], cwd=ROOT,env=env, capture_output=True)
    if probe.returncode:
        raise RuntimeError('Наявне середовище несумісне. Перейменуйте .venv на .venv_old і повторіть запуск. База збережеться.')
    requirements = ROOT / 'requirements.txt'
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stored = STAMP.read_text().strip() if STAMP.exists() else ''
    dependency_probe = subprocess.run([str(python), 'manage.py', 'check'], cwd=ROOT,env=env,capture_output=True)
    if stored != digest or dependency_probe.returncode:
        emit('Перевірка бібліотек. Перший запуск потребує інтернету; зачекайте…')
        run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(requirements)], env)
        run([str(python), '-c', 'import django; django.setup()'], env)
        STAMP.write_text(digest, encoding='utf-8')
    run([str(python), 'manage.py', 'check'], env)
    if args.check_only:
        emit('Перевірки запуску пройдено.')
        return
    import sqlite3
    db=ROOT/('BoS_Working.sqlite3' if args.original else 'BoS_Demo.sqlite3')
    if args.original and not db.exists() and (ROOT/'db.sqlite3').exists():
        with sqlite3.connect(ROOT/'db.sqlite3') as source, sqlite3.connect(db) as target:source.backup(target)
    if db.exists():
        backup=ROOT/'backups';backup.mkdir(exist_ok=True)
        with sqlite3.connect(db) as source,sqlite3.connect(backup/(db.stem+'-'+str(time.time_ns())+'.sqlite3')) as target:source.backup(target)
    run([str(python), 'manage.py', 'migrate', '--noinput'], env)
    if not args.original:
        run([str(python),'manage.py','seed_bos_demo'],env)
        run([str(python),'manage.py','seed_erp_demo'],env)
        run([str(python),'manage.py','seed_bos_workspace'],env)
        run([str(python),'manage.py','seed_bos_ua'],env)
    port = pick_port()
    url = 'http://127.0.0.1:%s/' % port
    emit('Відкрити: ' + url)
    emit('Залиште вікно відкритим. Ctrl+C — зупинити. Оригінал db.sqlite3 не змінюється.')
    with subprocess.Popen([str(python), 'manage.py', 'runserver', '127.0.0.1:%s' % port, '--noreload'], cwd=ROOT, env=env, stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace') as server:
        if not args.no_browser:
            threading.Thread(target=open_when_ready,args=(url,server),daemon=True).start()
        try:
            for line in server.stdout:
                emit(line.rstrip('\n'))
            code=server.wait()
            if code:
                raise RuntimeError('Сервер завершився з кодом %s. Перегляньте повідомлення вище.' % code)
        except KeyboardInterrupt:
            server.terminate()
            server.wait(timeout=10)
            emit('BoS зупинено.')

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nЗупинено. Для повтору відкрийте START_DEMO.bat.',flush=True)
        sys.exit(1)
    except Exception as error:
        message='ПОМИЛКА ЗАПУСКУ: '+str(error)
        try:
            emit(message)
            emit('Надішліть знімок помилки. Журнал: BoS_STARTUP.log')
        except OSError:
            print(message,flush=True)
            print('Не вдалося записати журнал. Розпакуйте BoS у доступну для запису папку.',flush=True)
        sys.exit(1)
