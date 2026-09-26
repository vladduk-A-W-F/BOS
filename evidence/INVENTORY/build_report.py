from pathlib import Path
import re,html
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.colors import HexColor,white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader
root=Path('/workspace/scratch/c7b51e996a9f')
source=Path('/workspace/sites/bos-original-refined/docs/BLOCK0_REPORT_UA.md').read_text()
for n,f in [('BoS','DejaVuSans.ttf'),('BoS-Bold','DejaVuSans-Bold.ttf')]:
 pdfmetrics.registerFont(TTFont(n,'/usr/share/fonts/truetype/dejavu/'+f))
pdfmetrics.registerFontFamily('BoS',normal='BoS',bold='BoS-Bold',italic='BoS',boldItalic='BoS-Bold')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle('BodyUA',fontName='BoS',fontSize=9.2,leading=13.3,textColor=HexColor('#243246'),spaceAfter=8))
styles.add(ParagraphStyle('TitleUA',fontName='BoS-Bold',fontSize=21,leading=26,textColor=HexColor('#172c42'),spaceAfter=13))
styles.add(ParagraphStyle('HeadingUA',fontName='BoS-Bold',fontSize=12,leading=16,textColor=HexColor('#174875'),spaceBefore=8,spaceAfter=8))
styles.add(ParagraphStyle('CellUA',fontName='BoS',fontSize=8.2,leading=11.8,textColor=HexColor('#243246')))
styles.add(ParagraphStyle('SmallUA',fontName='BoS',fontSize=8,leading=11,textColor=HexColor('#66758a')))

def inline(s):
 s=html.escape(s).replace('–','-').replace('—','-').replace('\u2011','-')
 s=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
 s=re.sub(r'`([^`]+)`',lambda m:'<font size="7.8">'+m.group(1)+'</font>',s)
 return s

def render(md):
 out=[];lines=md.strip().splitlines();i=0
 while i<len(lines):
  line=lines[i].strip()
  if not line: i+=1;continue
  if line.startswith('|'):
   rows=[]
   while i<len(lines) and lines[i].strip().startswith('|'):
    cells=[c.strip() for c in lines[i].strip().strip('|').split('|')]
    if not all(re.fullmatch(r'[-: ]+',c) for c in cells):rows.append(cells)
    i+=1
   width=A4[0]-80
   budget='Людино-дні' in rows[0][-1]
   widths=[width-85,85] if budget else ([width*.43,width*.57] if len(rows[0])==2 else None)
   data=[[Paragraph(inline(c) if r else '<b>'+inline(c)+'</b>',styles['CellUA']) for c in row] for r,row in enumerate(rows)]
   t=Table(data,colWidths=widths,hAlign='LEFT',repeatRows=1)
   t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e8eff6')),('ROWBACKGROUNDS',(0,1),(-1,-1),[white,HexColor('#f6f8fb')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.5,HexColor('#cbd7e3'))]))
   out.extend([t,Spacer(1,10)]);continue
  if line.startswith('# '):out.append(Paragraph(inline(line[2:]),styles['TitleUA']));i+=1;continue
  if line.startswith('## '):out.append(Paragraph(inline(line[3:]),styles['HeadingUA']));i+=1;continue
  parts=[line];i+=1
  while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|')):parts.append(lines[i].strip());i+=1
  out.append(Paragraph(inline(' '.join(parts)),styles['BodyUA']))
 return out

# Two fixed report pages; preserve all source paragraphs.
start,rest=source.split('## Конкретне розширення A05',1)
scope,rest=rest.split('## Докази й межі перевірки',1)
evidence,decision=rest.split('**Відкрите рішення:**',1)
evidence_table,limits=evidence.split('Звірка робочих даних 0.5',1)
first=start+'\n## Докази перевірки\n'+evidence_table
second='# Рішення щодо A05\n\n'+scope+'\n## Межі перевірки\n\nЗвірка робочих даних 0.5'+limits+'\n**Відкрите рішення:**'+decision
out=root/'output/pdf/BoS_Block0_Report_UA.pdf'
def frame(c,doc):
 w,h=A4
 c.setStrokeColor(HexColor('#bccbdd'));c.setLineWidth(.65);c.line(40,h-28,w-40,h-28)
 c.setFont('BoS-Bold',8);c.setFillColor(HexColor('#174875'));c.drawString(40,h-19,'BoS / КОНТРОЛЬНА ТОЧКА 0.1')
 c.setFont('BoS',8);c.setFillColor(HexColor('#66758a'));c.drawRightString(w-40,h-19,'11.09.2026')
 c.setStrokeColor(HexColor('#d7e0e9'));c.line(40,31,w-40,31)
 c.setFont('BoS',7.5);c.drawString(40,19,'Стоп-умова 8.6 · Очікує рішення · Не реліз');c.drawRightString(w-40,19,f'{doc.page} / 2')
doc=SimpleDocTemplate(str(out),pagesize=A4,rightMargin=40,leftMargin=40,topMargin=45,bottomMargin=42,title='BoS - результат інвентаризації та рішення щодо A05',author='BoS')
doc.build(render(first)+[PageBreak()]+render(second),onFirstPage=frame,onLaterPages=frame)
reader=PdfReader(out)
assert len(reader.pages)==2, len(reader.pages)
print({'pages':len(reader.pages),'bytes':out.stat().st_size,'file':str(out)})
