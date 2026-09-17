import hashlib,io,zipfile
from .models import Document

MAX_BYTES=10*1024*1024

def parse(file):
    try:
        return _parse(file)
    except (ValueError, UnicodeError):
        raise
    except ImportError as exc:
        raise ValueError('Модуль читання документа відсутній. Повторіть встановлення залежностей.') from exc
    except Exception as exc:
        raise ValueError('Не вдалося прочитати документ. Перевірте формат і цілісність файла.') from exc

def _parse(file):
    data=file.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('Файл перевищує 10 МБ.')
    ext=file.name.rsplit('.',1)[-1].lower();parts=[]
    if ext in ('docx','xlsx'):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(x.file_size for x in z.infolist())>40*1024*1024:raise ValueError('Розпакований документ завеликий.')
    if ext=='pdf':
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data))
        if reader.is_encrypted:raise ValueError('Зніміть пароль із PDF перед завантаженням.')
        if len(reader.pages)>100:raise ValueError('Максимум 100 сторінок.')
        parts=[{'source':f'Сторінка {i+1}','text':page.extract_text() or ''} for i,page in enumerate(reader.pages)]
    elif ext=='docx':
        from docx import Document as Word
        d=Word(io.BytesIO(data));parts=[{'source':f'Абзац {i+1}','text':p.text} for i,p in enumerate(d.paragraphs) if p.text]
        for i,t in enumerate(d.tables):parts.append({'source':f'Таблиця {i+1}','text':'\n'.join(' | '.join(c.text for c in row.cells) for row in t.rows)})
    elif ext=='xlsx':
        from openpyxl import load_workbook
        wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True)
        for ws in wb:
            if ws.max_row>5000 or ws.max_column>100:raise ValueError('Аркуш перевищує 5000 рядків або 100 стовпців.')
            parts.append({'source':f'Аркуш {ws.title}','text':'\n'.join(' | '.join(str(v) if v is not None else '' for v in row) for row in ws.iter_rows(values_only=True))})
        wb.close()
    elif ext in ('txt','md'):parts=[{'source':'Текст','text':data.decode('utf-8-sig')}]
    else:raise ValueError('Підтримуються PDF, DOCX, XLSX, TXT та MD.')
    text='\n'.join(p['text'] for p in parts)
    if len(text)>500000:raise ValueError('Текст документа перевищує ліміт.')
    return {'text':text,'sections':parts,'checksum':hashlib.sha256(data).hexdigest(),'status':'needs_review' if text.strip() else 'ocr_required','content':data}
