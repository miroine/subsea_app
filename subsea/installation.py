"""Installation tagging and costing exports for explicitly listed drawing objects."""
from __future__ import annotations

import copy
import json
from html import escape
from io import BytesIO
import math

import pandas as pd

from .bom import equipment_list
from .catalog import BY_ID
from .connections import CONNECTION_KINDS, CONNECTION_TYPES
from .spec import trains

STATUSES = ("Unspecified", "Existing", "New")
TAG_FIELDS = {
    "Installation status": "installationStatus",
    "Provider": "provider",
    "Installation type": "installationType",
    "Rating": "rating",
    "Installed length (km)": "installedLengthKm",
}
IDENTITY_COLUMNS = ["Reference", "Train", "Id", "Tag", "Equipment", "From", "To",
                    "Size (in)", "Wells", "Qty", "Internal valves (JSON)"]
SUMMARY_COLUMNS = ["Equipment", "Provider", "Installation type", "Rating", "Size (in)"]


def installation_items(spec: dict) -> list[tuple[str, str, dict]]:
    items = []
    for tid, train in trains(spec):
        if train.get("host"):
            items.append((f"{tid}/host", tid, train["host"]))
        for index, item in enumerate(train.get("chain", [])):
            items.append((f"{tid}/chain/{index}", tid, item))
        for reference, _, item in list(items):
            if reference.startswith(f"{tid}/"):
                for index, riser in enumerate(item.get("risers", [])):
                    items.append((f"{reference}/risers/{index}", tid, riser))
    items.extend((f"connections/{index}", "", item)
                 for index, item in enumerate(spec.get("connections", [])))
    return items


def installation_list(spec: dict) -> pd.DataFrame:
    bom = equipment_list(spec).to_dict("records")
    equipment = {(row["Train"], row["Id"]): row for row in bom}
    train_names = {tid: "Main" if tid == "main" else train.get("name", tid)
                   for tid, train in trains(spec)}
    rows = []
    for reference, tid, item in installation_items(spec):
        is_line = reference.startswith("connections/") or "/risers/" in reference
        row = equipment.get((train_names.get(tid), item.get("id")), {})
        kind = "riser" if "/risers/" in reference else item.get("kind", "")
        service = CONNECTION_TYPES.get(item.get("connectionType"), {}).get("label", "")
        name = (CONNECTION_KINDS.get(kind, kind) + (f" - {service}" if service else "")) if is_line else BY_ID.get(item.get("type"), {}).get("name", item.get("type", ""))
        length = item.get("installedLengthKm")
        if length is None and not is_line:
            length = item.get("pKm")
        rows.append({
            "Reference": reference, "Train": train_names.get(tid, ""),
            "Id": item.get("id", reference), "Tag": row.get("Tag", item.get("tag", "")),
            "Equipment": name, "From": item.get("from", ""), "To": item.get("to", ""),
            "Size (in)": item.get("pId", ""), "Wells": row.get("Wells", ""),
            "Qty": 1, "Label": spec.get("overrides", {}).get(item.get("id"), {}).get("label", item.get("label", "")),
            "Internal valves (JSON)": json.dumps(item["internalValves"], sort_keys=True) if "internalValves" in item else "Symbol defaults",
            "Installation status": item.get("installationStatus", "Unspecified"),
            "Provider": item.get("provider", ""), "Installation type": item.get("installationType", ""),
            "Rating": item.get("rating", ""), "Installed length (km)": length,
        })
    return pd.DataFrame(rows, columns=IDENTITY_COLUMNS + ["Label"] + list(TAG_FIELDS))


def apply_installation_rows(spec: dict, rows: list[dict]) -> dict:
    result = copy.deepcopy(spec)
    items = {reference: item for reference, _, item in installation_items(result)}
    original = installation_list(spec).to_dict("records")
    if len(rows) != len(original):
        raise ValueError("Installation rows no longer match the drawing. Refresh and retry.")
    for row, before in zip(rows, original):
        if any(not (pd.isna(row[column]) and pd.isna(before[column])) and row[column] != before[column]
               for column in IDENTITY_COLUMNS + ["Label"]):
            raise ValueError("Installation references and equipment identity cannot be edited.")
        item = items[row["Reference"]]
        for column, key in TAG_FIELDS.items():
            value = row[column]
            if column == "Installed length (km)":
                if value is None or pd.isna(value):
                    item.pop(key, None)
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"{row['Reference']}: installed length must be a non-negative number.")
            elif column != "Installation status" and (value is None or pd.isna(value)):
                value = ""
            elif not isinstance(value, str):
                raise ValueError(f"{row['Reference']}: {column} must be text.")
            elif column == "Installation status" and value not in STATUSES:
                raise ValueError(f"{row['Reference']}: choose New, Existing or Unspecified.")
            item[key] = value
    return result


def new_installation_summary(df: pd.DataFrame) -> pd.DataFrame:
    new = df.loc[df["Installation status"] == "New"].copy()
    new["Size (in)"] = new["Size (in)"].fillna("").astype(str)
    return new.groupby(SUMMARY_COLUMNS, as_index=False, dropna=False).agg(
        Qty=("Qty", "sum"),
        **{"Installed length (km)": ("Installed length (km)", lambda values: values.sum(min_count=1)),
           "Unknown lengths": ("Installed length (km)", lambda values: int(values.isna().sum()))},
    )


def costing_notes(df: pd.DataFrame) -> list[str]:
    notes = [
        "Quantities count explicitly listed drawing objects, including hosts and preset risers. "
        "Internal template wells, hubs, valves and implicit piping are not separate procurement items. Customized valve metadata is included in each parent's details. "
        "A flowline symbol and a connector are separate objects: avoid representing the same installed segment twice.",
        "Lengths are entered engineering values, never measured from schematic geometry. Unknown lengths are not zero.",
    ]
    unspecified = int((df["Installation status"] == "Unspecified").sum())
    if unspecified:
        notes.append(f"{unspecified} Unspecified item(s) excluded from the new-installation export; classify them before final costing.")
    new = df.loc[df["Installation status"] == "New"]
    for column in ("Provider", "Installation type", "Rating"):
        missing = int(new[column].str.strip().eq("").sum())
        if missing:
            notes.append(f"{missing} New item(s) missing {column}.")
    return notes


def costing_excel(df: pd.DataFrame) -> bytes:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.remove(workbook.active)
    new = df.loc[df["Installation status"] == "New"]
    sheets = {
        "New equipment": new,
        "Quantities": new_installation_summary(df),
        "Export notes": pd.DataFrame({"Notes": costing_notes(df)}),
    }
    for title, frame in sheets.items():
        sheet = workbook.create_sheet(title)
        sheet.append(list(frame.columns))
        for values in frame.itertuples(index=False, name=None):
            sheet.append([None if pd.isna(value) else value for value in values])
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for index, column in enumerate(frame.columns, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = min(60, max(18, len(column) + 2))
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def costing_pdf(df: pd.DataFrame) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = BytesIO()
    styles = getSampleStyleSheet()
    new = df.loc[df["Installation status"] == "New"]
    def paragraph(value):
        text = "" if pd.isna(value) else str(value)
        return Paragraph(escape(text).replace("\n", "<br/>"), styles["BodyText"])

    story = [Paragraph("New installation - costing list", styles["Title"]),
             paragraph(f"Total new drawing objects: {int(new['Qty'].sum())}")]
    for note in costing_notes(df):
        story.extend([Spacer(1, 6), paragraph(note)])
    story.extend([Spacer(1, 12), Paragraph("Quantities by specification", styles["Heading2"])])
    summary = new_installation_summary(df)
    data = [[paragraph(column) for column in summary.columns]]
    data.extend([[paragraph(value) for value in values] for values in summary.itertuples(index=False, name=None)])
    table = Table(data, repeatRows=1, colWidths=[86, 86, 105, 78, 55, 40, 112, 80])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EDFA")),
                              ("GRID", (0, 0), (-1, -1), .3, colors.lightgrey)]))
    story.append(table)
    story.append(Paragraph("Exact item list", styles["Heading2"]))
    for row in new.to_dict("records"):
        story.append(Paragraph(escape(f"{row['Reference']} - {row['Equipment']}"), styles["Heading3"]))
        details = Table([[paragraph(column), paragraph(value)] for column, value in row.items()
                         if column != "Internal valves (JSON)"],
                        colWidths=[150, 592])
        details.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("LINEBELOW", (0, 0), (-1, -1), .2, colors.lightgrey)]))
        story.append(details)
        story.append(Paragraph("Internal valves (JSON)", styles["Heading3"]))
        story.append(paragraph(row["Internal valves (JSON)"]))
    SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=50, rightMargin=50).build(story)
    return output.getvalue()
