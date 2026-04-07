"""
Google Sheets export/import using gspread.

Creates fully functional spreadsheets where every calculation cell is a formula.
Changing an input recalculates the entire model.
"""
from __future__ import annotations

import gspread
from google.oauth2.service_account import Credentials

from engine.inputs import ModelInputs
from store.serialization import model_inputs_to_dict, dict_to_model_inputs
from sheets.field_metadata import (
    FIELD_META, FIELD_TO_ROW, LABEL_TO_FIELD, field_count,
)
from sheets.formula_engine import (
    DAILY_HEADERS, DERIVED_ROWS,
    daily_all_formulas, derived_sheet_data,
    monthly_all_formulas, valuation_sheet_data,
)


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client() -> gspread.Client:
    """Authenticate via service account from Streamlit secrets or local file."""
    try:
        import streamlit as st
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception:
        pass

    # Fallback: local service_account.json
    import os
    sa_path = os.path.join(os.path.dirname(__file__), "..", "service_account.json")
    if os.path.exists(sa_path):
        creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
        return gspread.authorize(creds)

    raise RuntimeError(
        "No Google credentials found. Set st.secrets['gcp_service_account'] "
        "or place service_account.json in the project root."
    )


# ── Inputs sheet ──────────────────────────────────────────────────────

def _inputs_sheet_data(inp: ModelInputs) -> list[list]:
    """Build the Inputs sheet grid: Section | Parameter | Value | Unit | Description."""
    d = model_inputs_to_dict(inp)
    rows = [["Section", "Parameter", "Value", "Unit", "Description"]]
    for field_name, section, label, unit, desc in FIELD_META:
        val = d.get(field_name, "")
        # Booleans: write as TRUE/FALSE for Sheets
        if isinstance(val, bool):
            val = "TRUE" if val else "FALSE"
        rows.append([section, label, val, unit, desc])
    return rows


def _create_named_ranges(spreadsheet, inputs_ws, derived_ws):
    """Create named ranges for every input field and derived calculation."""
    requests = []

    inputs_sheet_id = inputs_ws.id
    derived_sheet_id = derived_ws.id

    # Input fields: each value is in column C (index 2)
    for field_name, row in FIELD_TO_ROW.items():
        requests.append({
            "addNamedRange": {
                "namedRange": {
                    "name": field_name,
                    "range": {
                        "sheetId": inputs_sheet_id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": 2,  # column C
                        "endColumnIndex": 3,
                    }
                }
            }
        })

    # Derived calculations: each value is in column B (index 1)
    for i, (name, _, _) in enumerate(DERIVED_ROWS):
        row = i + 2  # row 1 = header
        requests.append({
            "addNamedRange": {
                "namedRange": {
                    "name": name,
                    "range": {
                        "sheetId": derived_sheet_id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": 1,  # column B
                        "endColumnIndex": 2,
                    }
                }
            }
        })

    if requests:
        spreadsheet.batch_update({"requests": requests})


def _format_inputs_sheet(spreadsheet, inputs_ws):
    """Apply formatting to the Inputs sheet: bold headers, column widths."""
    sheet_id = inputs_ws.id
    requests = [
        # Bold header row
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        },
        # Column widths
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 140}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 250}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 2, "endIndex": 3},
            "properties": {"pixelSize": 120}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5},
            "properties": {"pixelSize": 300}, "fields": "pixelSize",
        }},
        # Freeze header row
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }},
    ]
    spreadsheet.batch_update({"requests": requests})


def _format_daily_sheet(spreadsheet, daily_ws):
    """Freeze header and first column on Daily sheet."""
    sheet_id = daily_ws.id
    requests = [
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold",
        }},
        {"updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1},
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }},
    ]
    spreadsheet.batch_update({"requests": requests})


# ── Export: Model ─────────────────────────────────────────────────────

def export_model_to_sheets(inp: ModelInputs, name: str, folder_id: str | None = None) -> str:
    """
    Create a fully functional spreadsheet from a ModelInputs.

    Returns the spreadsheet URL.
    """
    gc = get_gspread_client()

    # Create spreadsheet
    spreadsheet = gc.create(f"Model: {name}", folder_id=folder_id)

    # ── Inputs sheet (rename default Sheet1) ──
    inputs_ws = spreadsheet.sheet1
    inputs_ws.update_title("Inputs")
    inputs_data = _inputs_sheet_data(inp)
    inputs_ws.update(
        range_name=f"A1:E{len(inputs_data)}",
        values=inputs_data,
        value_input_option="USER_ENTERED",
    )

    # ── Derived sheet ──
    derived_ws = spreadsheet.add_worksheet("Derived", rows=len(DERIVED_ROWS) + 1, cols=3)
    derived_data = derived_sheet_data()
    derived_ws.update(
        range_name=f"A1:C{len(derived_data)}",
        values=derived_data,
        value_input_option="USER_ENTERED",
    )

    # ── Named ranges (must exist before Daily formulas reference them) ──
    _create_named_ranges(spreadsheet, inputs_ws, derived_ws)

    # ── Daily sheet ──
    time_max = inp.time_max
    n_cols = len(DAILY_HEADERS)
    daily_ws = spreadsheet.add_worksheet("Daily", rows=time_max + 1, cols=n_cols)

    # Write in batches to stay within API limits
    all_daily = daily_all_formulas(time_max)
    batch_size = 500
    for start in range(0, len(all_daily), batch_size):
        end = min(start + batch_size, len(all_daily))
        chunk = all_daily[start:end]
        start_row = start + 1  # 1-indexed
        # Determine end column letter
        end_col = _col_letter(n_cols - 1)
        range_name = f"A{start_row}:{end_col}{start_row + len(chunk) - 1}"
        daily_ws.update(
            range_name=range_name,
            values=chunk,
            value_input_option="USER_ENTERED",
        )

    # ── Monthly sheet ──
    monthly_data = monthly_all_formulas(time_max)
    n_monthly_cols = len(monthly_data[0]) if monthly_data else 1
    monthly_ws = spreadsheet.add_worksheet("Monthly", rows=len(monthly_data), cols=n_monthly_cols)
    monthly_ws.update(
        range_name=f"A1:{_col_letter(n_monthly_cols - 1)}{len(monthly_data)}",
        values=monthly_data,
        value_input_option="USER_ENTERED",
    )

    # ── Valuation sheet ──
    val_data = valuation_sheet_data(time_max)
    val_ws = spreadsheet.add_worksheet("Valuation", rows=len(val_data), cols=3)
    val_ws.update(
        range_name=f"A1:C{len(val_data)}",
        values=val_data,
        value_input_option="USER_ENTERED",
    )

    # ── Formatting ──
    _format_inputs_sheet(spreadsheet, inputs_ws)
    _format_daily_sheet(spreadsheet, daily_ws)

    return spreadsheet.url


# ── Export: Deal ──────────────────────────────────────────────────────

def export_deal_to_sheets(
    inp_before: ModelInputs,
    inp_after: ModelInputs,
    comp_dict: dict,
    eng_dict: dict,
    deal_name: str,
    summary: dict | None = None,
    folder_id: str | None = None,
) -> str:
    """
    Create a multi-sheet deal workbook.

    The baseline and target models each get their own full set of formula sheets
    (prefixed Before_/After_). Additional sheets show deltas, compensation, and summary.

    Returns the spreadsheet URL.
    """
    gc = get_gspread_client()
    spreadsheet = gc.create(f"Deal: {deal_name}", folder_id=folder_id)

    # ── Baseline model sheets ──
    _write_model_sheets(spreadsheet, inp_before, prefix="Before", is_first=True)

    # ── Target model sheets ──
    _write_model_sheets(spreadsheet, inp_after, prefix="After", is_first=False)

    # ── Deltas sheet ──
    _write_deltas_sheet(spreadsheet, inp_before, inp_after)

    # ── Compensation sheet ──
    _write_compensation_sheet(spreadsheet, comp_dict)

    # ── Engagement sheet ──
    _write_engagement_sheet(spreadsheet, eng_dict)

    # ── Summary sheet ──
    if summary:
        _write_summary_sheet(spreadsheet, summary)

    return spreadsheet.url


def _write_model_sheets(spreadsheet, inp: ModelInputs, prefix: str, is_first: bool):
    """Write Inputs, Derived, Daily, Monthly, Valuation sheets for one model."""
    time_max = inp.time_max

    # Inputs
    if is_first:
        inputs_ws = spreadsheet.sheet1
        inputs_ws.update_title(f"{prefix}_Inputs")
    else:
        inputs_ws = spreadsheet.add_worksheet(
            f"{prefix}_Inputs", rows=field_count() + 1, cols=5
        )
    inputs_data = _inputs_sheet_data(inp)
    inputs_ws.update(
        range_name=f"A1:E{len(inputs_data)}",
        values=inputs_data,
        value_input_option="USER_ENTERED",
    )

    # Derived
    derived_ws = spreadsheet.add_worksheet(
        f"{prefix}_Derived", rows=len(DERIVED_ROWS) + 1, cols=3
    )
    derived_data = derived_sheet_data()
    # Rewrite formulas to reference prefixed Inputs sheet
    for i in range(1, len(derived_data)):
        derived_data[i][1] = _prefix_sheet_refs(derived_data[i][1], "Inputs", f"{prefix}_Inputs")
    derived_ws.update(
        range_name=f"A1:C{len(derived_data)}",
        values=derived_data,
        value_input_option="USER_ENTERED",
    )

    # Named ranges for this model (prefixed to avoid collisions)
    _create_prefixed_named_ranges(spreadsheet, inputs_ws, derived_ws, prefix)

    # Daily
    n_cols = len(DAILY_HEADERS)
    daily_ws = spreadsheet.add_worksheet(f"{prefix}_Daily", rows=time_max + 1, cols=n_cols)
    all_daily = daily_all_formulas(time_max)
    # Rewrite named range references to prefixed versions
    for r in range(1, len(all_daily)):
        for c in range(len(all_daily[r])):
            formula = all_daily[r][c]
            if isinstance(formula, str) and formula.startswith("="):
                formula = _prefix_named_ranges(formula, prefix)
                formula = _prefix_sheet_refs(formula, "Daily", f"{prefix}_Daily")
                all_daily[r][c] = formula

    batch_size = 500
    for start in range(0, len(all_daily), batch_size):
        end = min(start + batch_size, len(all_daily))
        chunk = all_daily[start:end]
        start_row = start + 1
        end_col = _col_letter(n_cols - 1)
        range_name = f"A{start_row}:{end_col}{start_row + len(chunk) - 1}"
        daily_ws.update(
            range_name=range_name,
            values=chunk,
            value_input_option="USER_ENTERED",
        )

    # Monthly
    monthly_data = monthly_all_formulas(time_max)
    for r in range(1, len(monthly_data)):
        for c in range(len(monthly_data[r])):
            formula = monthly_data[r][c]
            if isinstance(formula, str) and formula.startswith("="):
                formula = _prefix_sheet_refs(formula, "Daily", f"{prefix}_Daily")
                monthly_data[r][c] = formula
    n_monthly_cols = len(monthly_data[0])
    monthly_ws = spreadsheet.add_worksheet(f"{prefix}_Monthly", rows=len(monthly_data), cols=n_monthly_cols)
    monthly_ws.update(
        range_name=f"A1:{_col_letter(n_monthly_cols - 1)}{len(monthly_data)}",
        values=monthly_data,
        value_input_option="USER_ENTERED",
    )

    # Valuation
    val_data = valuation_sheet_data(time_max)
    for r in range(1, len(val_data)):
        for c in range(len(val_data[r])):
            formula = val_data[r][c]
            if isinstance(formula, str) and formula.startswith("="):
                formula = _prefix_named_ranges(formula, prefix)
                formula = _prefix_sheet_refs(formula, "Daily", f"{prefix}_Daily")
                val_data[r][c] = formula
    val_ws = spreadsheet.add_worksheet(f"{prefix}_Valuation", rows=len(val_data), cols=3)
    val_ws.update(
        range_name=f"A1:C{len(val_data)}",
        values=val_data,
        value_input_option="USER_ENTERED",
    )


def _create_prefixed_named_ranges(spreadsheet, inputs_ws, derived_ws, prefix: str):
    """Create named ranges with a prefix to avoid collisions between before/after models."""
    requests = []

    for field_name, row in FIELD_TO_ROW.items():
        requests.append({
            "addNamedRange": {
                "namedRange": {
                    "name": f"{prefix}_{field_name}",
                    "range": {
                        "sheetId": inputs_ws.id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": 2,
                        "endColumnIndex": 3,
                    }
                }
            }
        })

    for i, (name, _, _) in enumerate(DERIVED_ROWS):
        row = i + 2
        requests.append({
            "addNamedRange": {
                "namedRange": {
                    "name": f"{prefix}_{name}",
                    "range": {
                        "sheetId": derived_ws.id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": 1,
                        "endColumnIndex": 2,
                    }
                }
            }
        })

    if requests:
        spreadsheet.batch_update({"requests": requests})


def _prefix_named_ranges(formula: str, prefix: str) -> str:
    """Replace named range references with prefixed versions in a formula."""
    # Replace derived named ranges
    for name, _, _ in DERIVED_ROWS:
        formula = formula.replace(name, f"{prefix}_{name}")
    # Replace input field named ranges (longer names first to avoid partial matches)
    sorted_fields = sorted(FIELD_TO_ROW.keys(), key=len, reverse=True)
    for field_name in sorted_fields:
        # Only replace if it's a standalone reference (not already prefixed)
        import re
        pattern = r'(?<![A-Za-z_])' + re.escape(field_name) + r'(?![A-Za-z_0-9])'
        replacement = f"{prefix}_{field_name}"
        # Don't double-prefix
        if f"{prefix}_{field_name}" not in formula or field_name not in formula:
            formula = re.sub(pattern, replacement, formula)
        else:
            # Only replace non-prefixed occurrences
            neg_lookbehind = r'(?<!' + re.escape(f"{prefix}_") + r')'
            full_pattern = neg_lookbehind + r'(?<![A-Za-z_])' + re.escape(field_name) + r'(?![A-Za-z_0-9])'
            formula = re.sub(full_pattern, replacement, formula)
    return formula


def _prefix_sheet_refs(formula: str, old_sheet: str, new_sheet: str) -> str:
    """Replace sheet references like Daily! with Before_Daily!"""
    return formula.replace(f"{old_sheet}!", f"'{new_sheet}'!")


def _write_deltas_sheet(spreadsheet, inp_before: ModelInputs, inp_after: ModelInputs):
    """Write a sheet showing only the fields that differ between before and after."""
    from store.serialization import compute_overrides
    deltas = compute_overrides(inp_before, inp_after)

    rows = [["Parameter", "Field", "Before", "After", "Delta"]]
    for field_name, section, label, unit, desc in FIELD_META:
        if field_name in deltas:
            before_val = getattr(inp_before, field_name)
            after_val = deltas[field_name]
            if isinstance(before_val, bool) or isinstance(after_val, bool):
                delta = ""
            elif isinstance(before_val, (int, float)) and isinstance(after_val, (int, float)):
                delta = after_val - before_val
            else:
                delta = ""
            rows.append([label, field_name, before_val, after_val, delta])

    ws = spreadsheet.add_worksheet("Deltas", rows=max(len(rows), 2), cols=5)
    ws.update(
        range_name=f"A1:E{len(rows)}",
        values=rows,
        value_input_option="USER_ENTERED",
    )


def _write_compensation_sheet(spreadsheet, comp_dict: dict):
    """Write compensation structure parameters."""
    rows = [["Parameter", "Value"]]
    for key, val in comp_dict.items():
        if isinstance(val, list):
            # Nested list (decay schedule, tiers, etc.) — write as sub-rows
            rows.append([key, f"({len(val)} items)"])
            if val and isinstance(val[0], dict):
                # Write sub-header
                sub_keys = list(val[0].keys())
                rows.append([""] + sub_keys)
                for item in val:
                    rows.append([""] + [item.get(k, "") for k in sub_keys])
        elif isinstance(val, dict):
            rows.append([key, str(val)])
        else:
            rows.append([key, val])

    ws = spreadsheet.add_worksheet("Compensation", rows=max(len(rows), 2), cols=10)
    ws.update(
        range_name=f"A1:{_col_letter(max(2, max(len(r) for r in rows)) - 1)}{len(rows)}",
        values=rows,
        value_input_option="USER_ENTERED",
    )


def _write_engagement_sheet(spreadsheet, eng_dict: dict):
    """Write engagement configuration."""
    rows = [["Parameter", "Value"]]
    for key, val in eng_dict.items():
        rows.append([key, val])

    ws = spreadsheet.add_worksheet("Engagement", rows=max(len(rows), 2), cols=2)
    ws.update(
        range_name=f"A1:B{len(rows)}",
        values=rows,
        value_input_option="USER_ENTERED",
    )


def _write_summary_sheet(spreadsheet, summary: dict):
    """Write deal summary metrics."""
    rows = [["Metric", "Value"]]
    for key, val in summary.items():
        if isinstance(val, float):
            val = round(val, 2)
        rows.append([key, val])

    ws = spreadsheet.add_worksheet("Summary", rows=max(len(rows), 2), cols=2)
    ws.update(
        range_name=f"A1:B{len(rows)}",
        values=rows,
        value_input_option="USER_ENTERED",
    )


# ── Import: Model ────────────────────────────────────────────────────

def import_model_from_sheets(spreadsheet_url: str) -> ModelInputs:
    """
    Read the Inputs sheet from a spreadsheet and parse back to ModelInputs.

    Handles both standalone model sheets (sheet named "Inputs") and
    deal workbooks (tries "Before_Inputs" then first sheet).
    """
    gc = get_gspread_client()
    spreadsheet = gc.open_by_url(spreadsheet_url)

    # Find the inputs sheet
    ws = None
    for name in ["Inputs", "Before_Inputs", "After_Inputs"]:
        try:
            ws = spreadsheet.worksheet(name)
            break
        except gspread.exceptions.WorksheetNotFound:
            continue
    if ws is None:
        ws = spreadsheet.sheet1

    all_values = ws.get_all_values()
    if len(all_values) < 2:
        raise ValueError("Sheet has no data rows")

    # Find the Parameter and Value columns
    header = [h.strip().lower() for h in all_values[0]]
    try:
        param_col = header.index("parameter")
        value_col = header.index("value")
    except ValueError:
        # Fallback: assume columns B and C (indices 1, 2)
        param_col = 1
        value_col = 2

    # Parse rows back to field values
    data = {}
    for row in all_values[1:]:
        if len(row) <= max(param_col, value_col):
            continue
        label = row[param_col].strip()
        value = row[value_col]

        # Reverse lookup: label -> field name
        field_name = LABEL_TO_FIELD.get(label.lower())
        if field_name is None:
            continue

        # Convert value to appropriate type
        if value == "" or value is None:
            continue
        if isinstance(value, str):
            v_lower = value.strip().lower()
            if v_lower in ("true", "false"):
                data[field_name] = v_lower == "true"
                continue
        try:
            # Try int first, then float
            if "." in str(value):
                data[field_name] = float(value)
            else:
                data[field_name] = int(value)
        except (ValueError, TypeError):
            data[field_name] = value

    return dict_to_model_inputs(data)


# ── Utility ───────────────────────────────────────────────────────────

def _col_letter(index: int) -> str:
    """Convert 0-indexed column number to letter(s): 0->A, 25->Z, 26->AA."""
    result = ""
    while True:
        result = chr(65 + index % 26) + result
        index = index // 26 - 1
        if index < 0:
            break
    return result
