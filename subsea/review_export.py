"""PDF and Excel checklists from the complete concept-design review."""
from datetime import datetime, timezone
from html import escape
from io import BytesIO

import pandas as pd

STATUSES = ("Action required", "Not assessed", "Screened")
NOTES = (
    "Concept-design screening only: not engineering approval, certification or an exhaustive standards-compliance assessment.",
    "No project standards/editions or acceptance criteria have been specified. Missing evidence is Not assessed, never passed.",
    "Screened means only the stated data comparison or declared-connectivity check completed.",
    "Layout defaults, free-text ratings and equipment/valve symbols do not establish certified capacity or functioning safety barriers.",
    "Schematic coordinates, distance labels and procedural terrain are not engineering clearances or survey data.",
    "All review results are included regardless of the on-screen filters. Resolve open actions and assessment gaps with discipline evidence and sign-off.",
)


def _coverage(report: pd.DataFrame) -> pd.DataFrame:
    return report.groupby("Area")["Status"].value_counts().unstack(fill_value=0).reindex(
        columns=STATUSES, fill_value=0).reset_index()


def review_excel(report: pd.DataFrame) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    checklist = report.copy()
    checklist.insert(0, "Check #", range(1, len(checklist) + 1))
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = {
        "Open checklist": checklist.loc[checklist["Status"].isin(STATUSES[:2])],
        "Full review": checklist,
        "Coverage": _coverage(report),
        "Read me": pd.DataFrame({"Notes": [
            "Generated (UTC): " + datetime.now(timezone.utc).isoformat(timespec="seconds"), *NOTES]}),
    }
    widths = {"Check #": 10, "Design": 30, "Area": 32, "Status": 20, "Severity": 12,
              "Rule": 30, "Reference": 30, "Finding": 65, "Required follow-up": 65,
              "Evidence / limitations": 65, "Notes": 100}
    for title, frame in sheets.items():
        sheet = workbook.create_sheet(title)
        sheet.append(list(frame.columns))
        for values in frame.itertuples(index=False, name=None):
            sheet.append(list(values))
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="17364D")
        for index, column in enumerate(frame.columns, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = widths.get(column, 20)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def review_pdf(report: pd.DataFrame) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Review body", parent=styles["BodyText"], fontSize=9, leading=12)

    def paragraph(value):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), body)

    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42,
                                 topMargin=42, bottomMargin=42)
    story = [Paragraph("Concept-design review checklist", styles["Title"]),
             paragraph("Generated (UTC): " + datetime.now(timezone.utc).isoformat(timespec="seconds"))]
    for title in report["Design"].drop_duplicates():
        story.append(paragraph("Design: " + title))
    for note in NOTES:
        story.extend([Spacer(1, 5), paragraph(note)])
    counts = report["Status"].value_counts()
    story.extend([Spacer(1, 10), paragraph(" | ".join(
        f"{status}: {counts.get(status, 0)}" for status in STATUSES)),
        Paragraph("Discipline coverage", styles["Heading2"])])
    coverage = _coverage(report)
    table = Table([[paragraph(column) for column in coverage.columns]] + [
        [paragraph(value) for value in row] for row in coverage.itertuples(index=False, name=None)],
        colWidths=[document.width * .46] + [document.width * .18] * 3, repeatRows=1)
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EDFA")),
                              ("GRID", (0, 0), (-1, -1), .3, colors.lightgrey)]))
    story.extend([table, Paragraph("Complete review checklist", styles["Heading2"])])
    numbered = report.copy()
    numbered.insert(0, "Check #", range(1, len(numbered) + 1))
    for area, group in numbered.groupby("Area", sort=True):
        story.append(Paragraph(escape(area), styles["Heading2"]))
        for status in STATUSES:
            for row in group.loc[group["Status"] == status].to_dict("records"):
                heading = f"Check {row['Check #']} - {row['Status']} - {row['Rule']}"
                story.append(Paragraph(escape(heading), styles["Heading3"]))
                for label in ("Reference", "Severity", "Finding", "Required follow-up", "Evidence / limitations"):
                    story.append(paragraph(f"{label}: {row[label]}"))
                story.append(Spacer(1, 8))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(doc.leftMargin, 22, "Concept screening only - not engineering approval")
        canvas.drawRightString(A4[0] - doc.rightMargin, 22, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
