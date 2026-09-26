"""D03 instructions audit; read-only, no Django setup or database access."""
from pathlib import Path
import json,re,sys,hashlib
r=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);checks=[]
def get(n):p=r/n;return p.read_text() if p.is_file() else ''
def check(n,ok,detail=''):checks.append({'case':n,'passed':bool(ok),'detail':detail})
html=get('frontend/boss_app_source.html');menu=re.search(r"\{id:'bank',label:'([^']+)'",html);label=menu.group(1);expected='Фінанси → '+label+' → Виписки'
check('CEO CSV instructions match actual NAV label',expected in get('docs/STATEMENTS_UA.md') and 'Фінанси → Банк' not in get('README_UA.md'),expected)
restore=get('docs/DEMO_AND_IMPORT_UA.md');check('Local database copy explicitly separated from private file restore','rehearsal-media' in restore and 'лише SQLite' in restore and 'скопіюйте обрану резервну копію як' not in restore)
check('Current product explanation no longer denies existing authentication','серверні облікові записи ще не підключені' not in html and 'робочий профіль — вхід із призначеними правами' in html)
check('Current plan no longer schedules implemented C01 fields','Додати погоджувані зміни терміну/відповідального' not in get('docs/NEXT_STEPS_UA.md'))
check('Current test instructions use isolated full verify and separate historical evidence','verify.sh' in get('docs/TEST_REPORT_UA.md') and 'verify.ps1' in get('docs/TEST_REPORT_UA.md') and 'history/TEST_REPORT_UA.md' in get('docs/TEST_REPORT_UA.md'))
check('Standard demo totals and synthetic cash have explicit distinct sources','21 600' in restore and 'не є залишком C03' in restore)
check('Active parameters describe actual User identity and ERP snapshot','Django User' in get('docs/PARAMETERS_UA.md') and 'Поточний ERP snapshot' in get('docs/PARAMETERS_UA.md'))
check('Missing operator bootstrap is disclosed, not represented as completed','Перший адміністратор — відкрита умова' in get('docs/SERVER_INSTALL_UA.md'))
required=['docs/ROLE_GUIDE_UA.md','docs/CAPABILITIES_UA.md','docs/DEMO_30_MIN_UA.md','docs/STATEMENT_DEMO_UA.md','docs/examples/BoS_Statement_Demo.csv','docs/BoS_Roles_UA.pdf']
for n in required:check('Deliverable '+n,(r/n).is_file())
files=['README_UA.md','docs/ERP_GUIDE_UA.md','docs/STATEMENTS_UA.md','docs/MVP_GUIDE_UA.md','docs/DEMO_AND_IMPORT_UA.md','docs/BACKUP_RESTORE_UA.md','docs/ACCESS_UA.md','docs/NEXT_STEPS_UA.md','docs/TEST_REPORT_UA.md','docs/SERVER_INSTALL_UA.md',*required[:4]]
broken=[]
for n in files:
 for dest in re.findall(r'\[[^\]]+\]\(([^)]+)\)',get(n)):
  dest=dest.split('#',1)[0]
  if not dest or re.match(r'^[a-z]+:',dest):continue
  if not (r/n).parent.joinpath(dest).resolve().exists():broken.append({'from':n,'target':dest})
check('All explicit local links in current user docs resolve',not broken,broken)
value={'complete':all(c['passed'] for c in checks),'checks':checks,'passed':sum(c['passed'] for c in checks),'total':len(checks),'scope':'Static instructions and artifact availability only; not runtime/browser acceptance.','files_sha256':{n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in files if (r/n).is_file()}}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in value.items() if k!='files_sha256'},ensure_ascii=False,indent=2));sys.exit(0 if value['complete'] else 1)
