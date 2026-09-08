from pathlib import Path
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

from app.core.config import settings


def _wrap(text: str, font: str, size: int, max_width: float) -> list[str]:
    words = (text or '').split()
    lines, current = [], ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_certificate_pdf(certificate: dict, template: dict | None = None) -> str:
    root = Path(settings.upload_dir) / 'certificates'
    root.mkdir(parents=True, exist_ok=True)
    filename = f"{certificate['certificate_number']}.pdf"
    path = root / filename

    page_w, page_h = landscape(A4)
    c = canvas.Canvas(str(path), pagesize=(page_w, page_h))

    # Professional, print-friendly certificate layout.
    margin = 18 * mm
    c.setStrokeColor(colors.HexColor('#1F5D45'))
    c.setLineWidth(2.2)
    c.rect(margin, margin, page_w - 2 * margin, page_h - 2 * margin)
    c.setStrokeColor(colors.HexColor('#C8A951'))
    c.setLineWidth(0.8)
    c.rect(margin + 6 * mm, margin + 6 * mm, page_w - 2 * margin - 12 * mm, page_h - 2 * margin - 12 * mm)

    issuer = (template or {}).get('issuer_name', 'Sixele LMS')
    title = (template or {}).get('title', 'Certificate of Completion')
    body = (template or {}).get('body_text', 'This certificate is awarded for successful completion of the course.')
    signature_name = (template or {}).get('signature_name', '')
    signature_title = (template or {}).get('signature_title', '')

    c.setFillColor(colors.HexColor('#1F5D45'))
    c.setFont('Helvetica-Bold', 16)
    c.drawCentredString(page_w / 2, page_h - 42 * mm, issuer.upper())

    c.setFillColor(colors.HexColor('#222222'))
    c.setFont('Helvetica-Bold', 30)
    c.drawCentredString(page_w / 2, page_h - 62 * mm, title)

    c.setFont('Helvetica', 12)
    c.setFillColor(colors.HexColor('#555555'))
    c.drawCentredString(page_w / 2, page_h - 78 * mm, 'This is proudly presented to')

    learner = certificate.get('learner_name', 'Learner')
    c.setFillColor(colors.HexColor('#1F5D45'))
    c.setFont('Helvetica-Bold', 25)
    c.drawCentredString(page_w / 2, page_h - 94 * mm, learner)

    c.setStrokeColor(colors.HexColor('#C8A951'))
    c.line(page_w / 2 - 55 * mm, page_h - 98 * mm, page_w / 2 + 55 * mm, page_h - 98 * mm)

    course = certificate.get('course_title', 'Course')
    c.setFillColor(colors.HexColor('#333333'))
    c.setFont('Helvetica', 12)
    y = page_h - 111 * mm
    for line in _wrap(body, 'Helvetica', 12, page_w - 90 * mm)[:3]:
        c.drawCentredString(page_w / 2, y, line)
        y -= 6 * mm
    c.setFont('Helvetica-Bold', 14)
    c.drawCentredString(page_w / 2, y - 1 * mm, course)

    issued_at = certificate.get('issued_at')
    issued_text = issued_at.strftime('%d %B %Y') if hasattr(issued_at, 'strftime') else str(issued_at or '')
    score = certificate.get('completion_score')
    score_text = f'{score:.1f}%' if isinstance(score, (int, float)) else 'Completed'

    footer_y = 39 * mm
    c.setFont('Helvetica', 9)
    c.setFillColor(colors.HexColor('#555555'))
    c.drawString(31 * mm, footer_y, f'Issued: {issued_text}')
    c.drawCentredString(page_w / 2, footer_y, f'Certificate No. {certificate.get("certificate_number", "") }')
    c.drawRightString(page_w - 31 * mm, footer_y, f'Result: {score_text}')

    if signature_name:
        c.setStrokeColor(colors.HexColor('#777777'))
        c.line(page_w - 82 * mm, 57 * mm, page_w - 35 * mm, 57 * mm)
        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(colors.HexColor('#333333'))
        c.drawCentredString(page_w - 58.5 * mm, 51 * mm, signature_name)
        if signature_title:
            c.setFont('Helvetica', 8)
            c.drawCentredString(page_w - 58.5 * mm, 46 * mm, signature_title)

    c.setFont('Helvetica', 8)
    c.setFillColor(colors.HexColor('#666666'))
    c.drawCentredString(page_w / 2, 27 * mm, f'Verify this certificate using certificate number: {certificate.get("certificate_number", "")}')

    c.showPage()
    c.save()
    return str(path)
