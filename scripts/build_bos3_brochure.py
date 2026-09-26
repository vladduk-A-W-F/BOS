"""Build the local prerelease guide from the same registry used by the UI."""
import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--font-dir', type=Path, default=Path('C:/Windows/Fonts'))
    args = parser.parse_args()
    raw = args.registry.read_bytes()
    content = json.loads(raw)
    if content['schema'] != 'bos.training.content.v1' or len(content['cases']) != 3:
        raise ValueError('A reviewed three-case registry is required.')
    pdfmetrics.registerFont(TTFont('BoS', str(args.font_dir / 'arial.ttf')))
    pdfmetrics.registerFont(TTFont('BoSBold', str(args.font_dir / 'arialbd.ttf')))
    pdfmetrics.registerFontFamily('BoS', normal='BoS', bold='BoSBold')
    styles = {
        'title': ParagraphStyle('title', fontName='BoSBold', fontSize=32, leading=38, textColor=colors.HexColor('#19312d'), spaceAfter=12),
        'h': ParagraphStyle('h', fontName='BoSBold', fontSize=16, leading=21, spaceAfter=10, textColor=colors.HexColor('#19312d')),
        'body': ParagraphStyle('body', fontName='BoS', fontSize=10, leading=15, spaceAfter=8, textColor=colors.HexColor('#283937')),
        'small': ParagraphStyle('small', fontName='BoS', fontSize=8.5, leading=12, spaceAfter=5, textColor=colors.HexColor('#566460')),
    }
    def p(text, style='body'):
        return Paragraph(escape(text), styles[style])
    flow = [p(content['brand'], 'title'), p(content['summary'], 'h'),
            p(content['company']), p('Локальна навчальна передверсія · ' + args.version, 'small'),
            p('Вигадані компанії, люди та операції. Гроші не переказуються. Підтвердження змінює лише окрему навчальну базу.'),
            Spacer(1, 5 * mm), p('Відділи та робочі питання', 'h')]
    rows = [[p('Область', 'small'), p('Що перевіряємо', 'small')]]
    rows.extend([[p(area['label']), p(area['question'])] for area in content['areas']])
    table = Table(rows, colWidths=[56 * mm, 110 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5eeeb')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, -1), .4, colors.HexColor('#d7dfdc')),
    ]))
    flow += [table, PageBreak(), p('Три робочі історії', 'title')]
    for index, case in enumerate(content['cases'], 1):
        flow.extend([p(f'{index:02d} · ' + case['title'], 'h'), p(case['story_intro']),
                     p('Результат навчання: ' + case['goal']),
                     p('Участь: ' + ', '.join(case['departments']), 'small'),
                     p('Окремий маршрут: ?training=' + case['slug'], 'small'), Spacer(1, 6 * mm)])
    flow += [p('Числа та статуси беріть із поточної навчальної сесії. Сервер перевіряє відповідь або факт операції; сам перехід на інший екран не завершує крок.', 'small'),
             PageBreak(), p('Початок роботи', 'title'),
             p('Увійдіть своїм локальним логіном і паролем. Відкрийте один із трьох кейсів. Перевірте джерела, виконайте навчальну дію та поверніться до перевірки результату.'),
             p('Для запису в CRM відкрийте чернетку з кейсу, перевірте клієнта, замовлення, відповідального та наступну дію. Запис з’являється лише після окремого підтвердження. Нотатка CRM не проводить оплату й не змінює склад.'),
             p('Короткий огляд системи', 'h')]
    for index, item in enumerate(content['tour'], 1):
        flow.append(p(str(index) + '. ' + item['title'] + ': ' + item['description']))
    flow += [Spacer(1, 4 * mm), p('Огляд можна пропустити. Ви можете повернутися до навчання або самостійно переглядати доступні розділи.'),
             p('Межі цієї передверсії', 'h'),
             p('Сервер працює тільки на вашому ПК. Зовнішня публікація, доступ запрошених тестувальників та production-перенесення ще не виконані. Облік ведеться на синтетичних даних; старі обмеження перевірок залишаються чинними.'),
             p('Для відгуку запишіть версію, кейс, крок, очікуваний і фактичний результат. Не додавайте паролі або реальні дані клієнтів.', 'small')]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def frame(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#15826b'))
        canvas.setLineWidth(2)
        canvas.line(22 * mm, 282 * mm, 188 * mm, 282 * mm)
        canvas.setFont('BoS', 8)
        canvas.setFillColor(colors.HexColor('#566460'))
        canvas.drawString(22 * mm, 13 * mm, content['brand'] + ' · ' + args.version + ' · Навчальні дані')
        canvas.drawRightString(188 * mm, 13 * mm, str(doc.page))
    SimpleDocTemplate(str(args.output), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                      topMargin=24 * mm, bottomMargin=23 * mm,
                      title='BoS 3.0 - стартова брошура', author='BoS').build(flow, onFirstPage=frame, onLaterPages=frame)
    manifest = {'schema': 1, 'version': args.version, 'fixture_id': content['fixture_id'],
                'registry_sha256': hashlib.sha256(raw).hexdigest(),
                'pdf_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}
    args.output.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
