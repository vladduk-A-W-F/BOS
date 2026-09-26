from pathlib import Path
import hashlib, html, json, re
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader
import runpy
runpy.run_path(str(Path(__file__).with_name("assert_full27_evidence.py")))

r=Path('/workspace/sites/bos-original-refined'); s=Path('/workspace/scratch/c7b51e996a9f')
a=json.loads((r/'evidence/D03/AFTER_FULL27.json').read_text()); v=json.loads((r/'evidence/D03/verify-1/report.json').read_text())
assert not v['complete'] and a['source_unchanged'] and a['django']=={'tests':571,'ok':True}
assert len(a['gate8']['failures'])==1 and a['gate8']['failures'][0]['error_type']=='ConnectionResetError'
font=Path('/usr/share/fonts/truetype/dejavu')
for n,f in [('BoS','DejaVuSans.ttf'),('BoSB','DejaVuSans-Bold.ttf')]: pdfmetrics.registerFont(TTFont(n,str(font/f)))
pdfmetrics.registerFontFamily('BoS',normal='BoS',bold='BoSB',italic='BoS',boldItalic='BoSB')
body=ParagraphStyle('body',fontName='BoS',fontSize=9.1,leading=13,textColor=HexColor('#273341'),spaceAfter=7)
title=ParagraphStyle('title',parent=body,fontName='BoSB',fontSize=23,leading=28,spaceAfter=10)
h=ParagraphStyle('h',parent=body,fontName='BoSB',fontSize=12,leading=17,spaceBefore=6,spaceAfter=6)
cell=ParagraphStyle('cell',parent=body,fontSize=8,leading=11,spaceAfter=0)
small=ParagraphStyle('small',parent=body,fontSize=7.5,leading=10)
def p(t,style=body):
 t=html.escape(t);t=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',t);return Paragraph(t,style)
def table(rows,widths):
 data=[[p(str(t),cell) for t in row] for row in rows]
 tb=Table(data,colWidths=widths,hAlign='LEFT',repeatRows=1)
 tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#EDF1F5')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,HexColor('#C5CFD9')),('LINEBELOW',(0,1),(-1,-1),.35,HexColor('#E0E6EC')),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]));return tb

intro='BoS 0.2.16-dev · 12.09.2026 · локальна збірка розробки'
decision='Локальні доопрацювання та незалежний огляд завершено в перевірених межах. Повний verify №27 повернув 1: готовність MVP не прийнята. Код Django й оригінальний інтерфейс збережено; усі 11 умов приймання залишаються обов’язковими.'
changes='Наскрізний процес пов’язує закупівлю, часткове приймання, повернення, склад, продаж, рахунок, CSV-виписку, оплату та доручення з результатом. Дії мають перегляд і погодження; повтор не створює дубль. Імпорт виписки сам не проводить гроші; валюти рахуються окремо. Додано українські інструкції за ролями, карту можливостей, навчальний CSV і PDF-пам’ятку.'
evidence=[['Доказ у комплекті','Що підтверджено'],['evidence/A01/RESULT_UA.md; A02/RESULT_UA.md','До: A01 — 5 з 6 регресій падали. Після: 6/6 для A01 та 6/6 для A02; актуальний стан партії й захищена виплата.'],['evidence/D03/verify-1/report.json','Linux/SQLite: 151 + 5 + 571 тест; 5 × 1000 інваріантів; права 9432 HTTP + 9 redirects / 57 перевірок полів.'],['evidence/D03/verify-1/gate-06-actual.json','821/821 наскрізна перевірка, 42 погодження через HTTP. Еталон і суми до копійки зійшлися.'],['evidence/D03/AFTER_FULL27.json','109 паралельних методів / 116 контрольних записів покриття / 35 дій; restore 18/18; код і дві вихідні бази незмінні.'],['evidence/D03/RESULT_UA.md','Статична перевірка інструкцій: до 1/15, після 15/15. CSV: 3 рядки / 3 валюти. PDF: 3 переглянуті сторінки.']]
inventory='Інвентар 0.1 залишається замороженим: 85 шляхів запису, 12 дефектних місць. Прийнята оцінка A05 — 6–10 людино-днів; валютні зміни A02 — ще 0,25–0,5. Це оцінки обсягу, не облік фактично витраченого часу.'
reconcile='Звірка 0.5 виконана лише для читання на копії. Підтвердженої грошової розбіжності не встановлено; у джерелі бракує ERP-таблиць для повного покриття. Кандидати на дубль потребують людської перевірки. Історію не виправляли автоматично; приватні дані не включено до комплекту.'
environment='Фактичне середовище: Linux, Python 3.12.14, Django 6.0.5, SQLite 3.53.1. PostgreSQL, Windows, браузерний прогін і навантаження не запускалися. Підготовлені CI-файли не є доказом виконаного конвеєра.'
rows=[['№','Обов’язкова умова','Фактичний стан'],['1','Порожні міграції','SQLite пройдено; PostgreSQL не запущено'],['2','Усі тести на обох СУБД','SQLite 151+5+571; PostgreSQL не запущено'],['3','П’ять інваріантів × 1000','SQLite пройдено; PostgreSQL не запущено'],['4','Ролі, API/admin та поля','Пройдено у локальному прогоні'],['5','Одночасні грошові й складські дії','SQLite пройдено; PostgreSQL не запущено'],['6','Чистий наскрізний сценарій','SQLite 821/821; PostgreSQL не запущено'],['7','Відновлення в чисту установку','Локально 18/18, точні 56 таблиць і файли'],['8','Чиста робоча установка','30/31: відомий reset на 13 MiB; не прийнято'],['9','Оновлення N → N+1 та rollback','Не реалізовано / не прийнято'],['10','Розміри, zoom, клавіатура, мережа','Браузерний критерій не реалізовано / не запущено'],['11','Чиста Windows / Python 3.12','Не запущено; потрібен фактичний runner']]
blocks='Наступний зовнішній крок — адреса та доступ до репозиторію CI саме BoS: GitLab або GitHub. У локальному Git немає remote; доступний FOS — інший проєкт. Потрібні ізольований PostgreSQL, Windows runner і дозволений браузерний стенд. A09 вичерпала ліміт спроб; нових експериментів не виконано. Роботу над A10 activation зупинила автоматична перевірка вмісту з повідомленням про можливий cybersecurity risk; дію не повторювали. A11 заблокована середовищем; Node/source review її не замінює.'
scope='Нова прогалина F04: немає підтриманого операторського створення першого адміністратора через конфігурацію установки. Оцінка 0,5–1,5 людино-дня, рішення після блоку 3. B04–B07 — тільки за наявності власного виробництва клієнта; інакше лишаються відкладеними. B08/B09/C02/C04/D02 — оцінений беклог. Потрібні рішення: платформа BoS CI; власне виробництво — так/ні; F04 — окреме наступне доопрацювання або відкладення серверного пілота.'
conditions='До запуску: погоджені дані й підпис пілотного клієнта (D01); договір пілота з правилами обробки, експорту й видалення даних, власністю доробок та підтримкою; незалежне приймання людиною. Консенсус агентів ці умови не закриває.'
disagreement='Зауваження до промпту: твердження про вже доступний GitLab не підтвердилося у підключеннях BoS. Вимогу реального CI збережено; непідтверджений доступ не замінено припущенням. Паспорт релізу до повного exit 0 не створюється.'
story=[p('BoS · результат роботи',title),p(intro,small),p(decision),p('Що вже пов’язано',h),p(changes),table(evidence,[215,296]),Spacer(1,8),p(inventory),p(reconcile),p(environment,small),PageBreak(),p('Що відділяє від запуску',title),table(rows,[32,206,273]),Spacer(1,8),p(blocks),p(scope),p(conditions),p(disagreement,small)]
def page(c,d):
 w,hh=A4;c.setFillColor(HexColor('#E4B63B'));c.rect(0,hh-8,w,8,fill=1,stroke=0);c.setFont('BoSB',12);c.setFillColor(HexColor('#172331'));c.drawString(42,hh-35,'BoS');c.setFont('BoS',8);c.drawRightString(w-42,hh-33,'СТАН РОЗРОБКИ · НЕ ПАСПОРТ РЕЛІЗУ');c.setStrokeColor(HexColor('#DAE2E9'));c.line(42,47,w-42,47);c.setFont('BoS',7);c.setFillColor(HexColor('#506174'));c.drawString(42,33,'Source: '+a['source_sha256']);c.drawString(42,21,'Report: '+a['report_sha256']);c.drawRightString(w-42,59,str(d.page))
out=s/'output/pdf/BoS_Status_UA.pdf';out.parent.mkdir(parents=True,exist_ok=True)
doc=SimpleDocTemplate(str(out),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=56,bottomMargin=62,title='BoS · стан розробки та умови запуску',author='BoS');doc.build(story,onFirstPage=page,onLaterPages=page)
reader=PdfReader(out);assert len(reader.pages)==2,len(reader.pages)
def mdtable(rows):return '\n'.join('| '+' | '.join(row)+' |' for row in [rows[0],['---']*len(rows[0]),*rows[1:]])
md='\n\n'.join(['# BoS · результат роботи',intro,decision,'## Що вже пов’язано',changes,mdtable(evidence),inventory,reconcile,environment,'## Що відділяє від запуску',mdtable(rows),blocks,scope,conditions,disagreement,'Source SHA: '+a['source_sha256']+'. Report SHA: '+a['report_sha256']+'.'])+'\n'
(s/'tmp/COMPLETION_REPORT_UA.md').write_text(md)
qa={'pdf':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'pages':len(reader.pages),'source_sha256':a['source_sha256'],'report_sha256':a['report_sha256'],'visual_review':'pending'}
(s/'tmp/BoS_Status_PDF_QA.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n');print(json.dumps(qa,ensure_ascii=False,indent=2))
