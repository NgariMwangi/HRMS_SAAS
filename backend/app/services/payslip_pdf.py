"""A4, selectable-text payslips with repeated table headings and draft marking."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle

NAVY = colors.HexColor("#152b3c")
TEAL = colors.HexColor("#087e8b")
MUTED = colors.HexColor("#627382")
LINE = colors.HexColor("#dce5eb")
PALE = colors.HexColor("#f3f7f9")
_font_lock = Lock()


def fonts():
    with _font_lock:
        if "Payslip" not in pdfmetrics.getRegisteredFontNames():
            directory = Path(reportlab.__file__).parent / "fonts"
            pdfmetrics.registerFont(TTFont("Payslip", str(directory / "Vera.ttf")))
            pdfmetrics.registerFont(TTFont("PayslipBold", str(directory / "VeraBd.ttf")))
            pdfmetrics.registerFontFamily("Payslip", normal="Payslip", bold="PayslipBold")


def render(data):
    fonts()
    from app.services.branding import logo_flowable
    accent = colors.HexColor(data.get("theme_color") or "#087e8b")
    output = BytesIO()
    width = A4[0] - 34 * mm
    styles = {
        "body": ParagraphStyle("body", fontName="Payslip", fontSize=9, leading=12, textColor=NAVY, splitLongWords=True),
        "small": ParagraphStyle("small", fontName="Payslip", fontSize=7.5, leading=10, textColor=MUTED),
        "company": ParagraphStyle("company", fontName="PayslipBold", fontSize=18, leading=22, textColor=NAVY),
        "title": ParagraphStyle("title", fontName="PayslipBold", fontSize=22, leading=26, textColor=NAVY, alignment=TA_RIGHT),
        "right": ParagraphStyle("right", fontName="Payslip", fontSize=9, leading=12, alignment=TA_RIGHT, textColor=NAVY),
        "smallRight": ParagraphStyle("smallRight", fontName="Payslip", fontSize=7.5, leading=10, alignment=TA_RIGHT, textColor=MUTED),
        "total": ParagraphStyle("total", fontName="PayslipBold", fontSize=9, leading=12, textColor=NAVY),
        "totalRight": ParagraphStyle("totalRight", fontName="PayslipBold", fontSize=9, leading=12, alignment=TA_RIGHT, textColor=NAVY),
        "section": ParagraphStyle("section", fontName="PayslipBold", fontSize=10, leading=14, textColor=NAVY, spaceBefore=10, spaceAfter=5, keepWithNext=True),
    }
    def p(value, style="body"):
        # All names/contact fields are text, never ReportLab markup or external assets.
        return Paragraph(escape(str(value if value is not None else "")).replace("\n", "<br/>"), styles[style])
    def cash(value):
        return f"{Decimal(value):,.{int(data['decimal_places'])}f}"
    def day(value):
        return date.fromisoformat(value).strftime("%d %b %Y")
    def cell(label, value):
        return [p(label.upper(), "small"), Spacer(1, 3), p(value)]
    def amount_table(title, lines, total_label, total):
        rows = [[p("DESCRIPTION", "small"), p(data["currency_code"], "smallRight")]]
        rows += [[p(line["name"]), p(cash(line["amount"]), "right")] for line in lines]
        if not lines:
            rows.append([p("None recorded", "small"), p(cash(0), "right")])
        rows.append([p(total_label, "total"), p(cash(total), "totalRight")])
        table = Table(rows, colWidths=[width * .70, width * .30], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("LINEBELOW", (0, 0), (-1, 0), .6, LINE), ("LINEABOVE", (0, -1), (-1, -1), .8, LINE),
            ("LINEBELOW", (0, 1), (-1, -2), .3, LINE),
            ("BACKGROUND", (0, -1), (-1, -1), PALE),
        ]))
        # Keep the section title with at least the first table rows, while allowing long tables to paginate.
        return [Paragraph(escape(title), styles["section"]), table]

    doc = BaseDocTemplate(output, pagesize=A4, leftMargin=17*mm, rightMargin=17*mm,
        topMargin=20*mm, bottomMargin=20*mm, title=f"Payslip {data['reference']}", author=data["company_name"],
        subject=f"{data['employee_name']} | {data['period_start']} to {data['period_end']}", pageCompression=1)
    company = []
    logo = logo_flowable(data.get("logo_data_url"), max_width=175, max_height=38)
    if logo:
        company = [logo]
    for key in ("company_phone",):
        if data.get(key):
            company += [Spacer(1, 3), p(data[key], "small")]
    initials = "".join(word[0] for word in data["company_name"].split()[:2])
    monogram_style = ParagraphStyle("monogram", parent=styles["total"], textColor=accent, fontSize=12, leading=16)
    monogram = Table([[Paragraph(escape(initials), monogram_style)]], colWidths=[32], rowHeights=[32])
    monogram.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,-1), colors.HexColor("#e9f5f5")), ("VALIGN",(0,0),(-1,-1),"MIDDLE"), ("LEFTPADDING",(0,0),(-1,-1),5)]))
    brand = Table([[company]] if logo else [[monogram, company]], colWidths=[width*.65] if logo else [42, width*.65-42], hAlign="LEFT")
    brand.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0), ("TOPPADDING",(0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    title = [p("PAYSLIP", "title"), Spacer(1, 5), p(data["reference"], "right")]
    header = Table([[brand, title]], colWidths=[width*.65, width*.35], hAlign="LEFT")
    header.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0)]))
    period = f"{day(data['period_start'])} - {day(data['period_end'])}"
    details = Table([
        [cell("Employee", data["employee_name"]), cell("Employee number", data["employee_number"])],
        [cell("Pay period", period), cell("Branch", data["branch_name"])],
        [cell("Currency", data["currency_code"]), cell("PIN number", data.get("pin_number"))],
        [cell("SHIF no.", data.get("shif_no")), cell("NSSF no.", data.get("nssf_no"))],
    ], colWidths=[width*.6, width*.4], hAlign="LEFT")
    details.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"), ("BACKGROUND",(0,0),(-1,-1),PALE),
        ("TOPPADDING",(0,0),(-1,-1),6), ("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LEFTPADDING",(0,0),(-1,-1),12), ("RIGHTPADDING",(0,0),(-1,-1),12)]))
    story = [header, Spacer(1, 16), details]
    story += amount_table("01  EARNINGS", data["earnings"], "Gross pay", data["gross"])
    story += amount_table("02  EMPLOYEE DEDUCTIONS", data["deductions"], "Total deductions", data["employee_deductions"])
    if data["taxable"] is not None:
        taxable = Table([[p("Taxable pay", "small"), p(f"{data['currency_code']} {cash(data['taxable'])}", "smallRight")]], colWidths=[width*.6, width*.4], hAlign="LEFT")
        taxable.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0), ("TOPPADDING",(0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,-1),0)]))
        story += [Spacer(1, 9), taxable]
    def luminance(channel):
        return channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4
    light = .2126*luminance(accent.red) + .7152*luminance(accent.green) + .0722*luminance(accent.blue)
    ink = colors.white if light < .179 else colors.black
    net_style = ParagraphStyle("net", parent=styles["title"], textColor=ink, fontSize=17, leading=22)
    net_label = ParagraphStyle("netLabel", parent=styles["body"], textColor=ink, fontName="PayslipBold")
    net = Table([[Paragraph("NET PAY", net_label), Paragraph(escape(f"{data['currency_code']} {cash(data['net'])}"), net_style)]], colWidths=[width*.43, width*.57], hAlign="LEFT")
    net.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),accent), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),11), ("BOTTOMPADDING",(0,0),(-1,-1),11),
        ("LEFTPADDING",(0,0),(-1,-1),14), ("RIGHTPADDING",(0,0),(-1,-1),14)]))
    story += [Spacer(1, 16), KeepTogether([net])]
    def page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(accent); canvas.setLineWidth(3)
        canvas.line(17*mm, A4[1]-12*mm, A4[0]-17*mm, A4[1]-12*mm)
        if document.page > 1:
            canvas.setFont("Payslip", 7); canvas.setFillColor(MUTED)
            canvas.drawString(17*mm, A4[1]-17*mm, f"PAYSLIP | {data['reference']} | continued")
        if data["status"] != "APPROVED":
            canvas.saveState(); canvas.setFillColor(colors.HexColor("#edf0f2"))
            canvas.translate(A4[0]/2, A4[1]/2); canvas.rotate(35)
            canvas.setFont("PayslipBold", 70); canvas.drawCentredString(0, 0, "DRAFT"); canvas.restoreState()
        canvas.setStrokeColor(LINE); canvas.setLineWidth(.5)
        canvas.line(17*mm, 16*mm, A4[0]-17*mm, 16*mm)
        canvas.setFont("Payslip", 7); canvas.setFillColor(MUTED)
        canvas.drawString(17*mm, 11*mm, "CONFIDENTIAL | Computer-generated payslip")
        canvas.drawRightString(A4[0]-17*mm, 11*mm, f"{data['reference']} | Page {document.page}")
        canvas.restoreState()
    # A zero-padding frame keeps every section on the same left/right edges.
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id="payslip", frames=[frame], onPage=page))
    doc.build(story)
    return output.getvalue()
