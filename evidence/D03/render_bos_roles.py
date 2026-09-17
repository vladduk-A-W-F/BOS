from pathlib import Path
import re,html,json,hashlib
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader,PdfWriter
root=Path('/workspace/scratch/c7b51e996a9f');src=root/'tmp/d03_docs/ROLE_GUIDE_UA.md';out=root/'output/pdf';out.mkdir(parents=True,exist_ok=True);tmp=root/'tmp/pdfs';tmp.mkdir(exist_ok=True)
font=Path('/usr/share/fonts/truetype/dejavu');pdfmetrics.registerFont(TTFont('BoS',str(font/'DejaVuSans.ttf')));pdfmetrics.registerFont(TTFont('BoSB',str(font/'DejaVuSans-Bold.ttf')));pdfmetrics.registerFontFamily('BoS',normal='BoS',bold='BoSB',italic='BoS',boldItalic='BoSB')
text=src.read_text();sections=re.split(r'^## ',text,flags=re.M)[1:];roles=[]
for sec in sections[:3]:
 title,body=sec.split('\n',1);roles.append((title,body.strip()))
body_style=ParagraphStyle('body',fontName='BoS',fontSize=10,leading=15,textColor=HexColor('#273341'),spaceAfter=9)
title_style=ParagraphStyle('title',fontName='BoSB',fontSize=21,leading=27,textColor=HexColor('#172331'),spaceAfter=15)
sub_style=ParagraphStyle('sub',fontName='BoS',fontSize=9,leading=13,textColor=HexColor('#506174'),spaceAfter=16)
step_style=ParagraphStyle('step',parent=body_style,leftIndent=17,firstLineIndent=-17,spaceAfter=10)
def inline(s):
 s=s.replace('—','-').replace('–','-').replace('\u2011','-');s=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',s);s=html.escape(s);s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s);s=re.sub(r'`([^`]+)`',r'\1',s);return s
counts={};writer=PdfWriter()
for idx,(title,body) in enumerate(roles,1):
 path=tmp/f'roles-{idx}.pdf';role=title.split(' · ')[0]
 def page(canvas,doc,role=role):
  w,h=A4;canvas.setFillColor(HexColor('#E4B63B'));canvas.rect(0,h-9,w,9,fill=1,stroke=0)
  canvas.setFont('BoSB',16);canvas.setFillColor(HexColor('#172331'));canvas.drawString(42,h-42,'BoS')
  canvas.setFont('BoS',9);canvas.setFillColor(HexColor('#506174'));canvas.drawRightString(w-42,h-40,'ПАМ’ЯТКА ДЛЯ РОБОТИ')
  canvas.setStrokeColor(HexColor('#DCE2E8'));canvas.line(42,44,w-42,44)
  canvas.setFont('BoS',8);canvas.drawString(42,29,'Локальна збірка розробки · загальне приймання відкрите')
  canvas.drawRightString(w-42,29,f'{role} / {doc.page}');canvas.setFont('BoS',7);canvas.drawString(42,17,'Повний посібник: docs/ROLE_GUIDE_UA.md у комплекті BoS')
 story=[Paragraph(inline(title),title_style),Paragraph('Перевірте джерело. Знайдіть факт. Передайте питання.' if idx==3 else 'Перевірте джерело. Погодьте дію. Збережіть результат.',sub_style)]
 paragraphs=re.split(r'\n\s*\n',body)
 for p in paragraphs:
  lines=p.splitlines()
  if any(re.match(r'^\d+\. ',x) for x in lines):
   for line in lines:story.append(Paragraph(inline(line),step_style))
  else:story.append(Paragraph(inline(' '.join(lines)),body_style))
 if idx==3:
  story.extend([Spacer(1,12),Paragraph('Як повідомити про проблему',ParagraphStyle('h',parent=title_style,fontSize=14,leading=18)),Paragraph('Передайте відповідальному за установку версію BoS, свою роль, час, код запису або номер погодження та точний текст помилки. Прихований запис не означає відсутність операції. Паролі не передавайте.',body_style)])
 doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=67,bottomMargin=60,title='BoS · '+role,author='BoS');doc.build(story,onFirstPage=page,onLaterPages=page)
 reader=PdfReader(path);counts[role]=len(reader.pages);assert len(reader.pages)<=2,(role,len(reader.pages))
 for pg in reader.pages:writer.add_page(pg)
writer.add_metadata({'/Title':'BoS · пам’ятки керівнику, менеджеру та спостерігачу','/Author':'BoS','/Subject':'D03 · інструкції за ролями; загальне приймання відкрите'})
final=out/'BoS_Roles_UA.pdf'
with final.open('wb') as f:writer.write(f)
report={'source':str(src),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'pdf':str(final),'pdf_sha256':hashlib.sha256(final.read_bytes()).hexdigest(),'pages':len(PdfReader(final).pages),'pages_by_role':counts,'browser_acceptance':False}
(tmp/'ROLES_PDF_QA.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
