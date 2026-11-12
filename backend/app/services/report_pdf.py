"""Branded, printable exports of the same filtered records as CSV reports."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, LongTable, TableStyle, Paragraph, Spacer
from app.services.branding import logo_flowable
from app.services.payslip_pdf import fonts


def render(report):
    fonts()
    buffer = BytesIO()
    size = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=size, leftMargin=15*mm, rightMargin=15*mm,
        topMargin=39*mm, bottomMargin=15*mm, title=report["title"], author=report["company"])
    accent = colors.HexColor(report.get("theme_color") or "#4F46E5")
    style = ParagraphStyle("report", fontName="Payslip", fontSize=7, leading=10)
    heading = ParagraphStyle("report-heading", parent=style, fontName="PayslipBold")
    p = lambda value, text_style=style: Paragraph(escape(str(value if value is not None else "")), text_style)
    logo = logo_flowable(report.get("logo_data_url"), max_width=130, max_height=30)

    def page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(3)
        canvas.line(15*mm, size[1]-12*mm, size[0]-15*mm, size[1]-12*mm)
        if logo:
            logo.drawOn(canvas, 15*mm, size[1]-27*mm)
        canvas.setFillColor(colors.HexColor("#172033"))
        title = p(f"{report['company']} — {report['title']}", heading)
        available = doc.width - (145 if logo else 0)
        _, height = title.wrap(available, 40)
        title.drawOn(canvas, 15*mm + (145 if logo else 0), size[1]-20*mm-height)
        canvas.setFont("Payslip", 7)
        canvas.drawString(15*mm, size[1]-34*mm, f"{report['start_on']} to {report['end_on']} | {report['branch']} | {report['department']}")
        canvas.drawString(15*mm, 9*mm, f"CONFIDENTIAL | Generated {report['generated_at'][:10]}")
        canvas.drawRightString(size[0]-15*mm, 9*mm, f"Page {document.page}")
        canvas.restoreState()

    story = [p(report["note"]), Spacer(1, 9)]
    for metric in report["summary"]:
        story.append(p(f"{metric['label']}: {metric['value']}"))
    story.append(Spacer(1, 10))
    columns = report["columns"]
    rows = [[p(column["label"], heading) for column in columns]]
    rows += [[p(row.get(column["key"])) for column in columns] for row in report["rows"]]
    if len(rows) == 1:
        story.append(p("No matching records."))
    else:
        table = LongTable(rows, colWidths=[doc.width / len(columns)] * len(columns), repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EEF2F6")),
            ("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING", (0,0), (-1,-1), 6), ("LINEBELOW", (0,0), (-1,-1), .3, colors.HexColor("#DCE5EB"))]))
        story.append(table)
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buffer.getvalue()
