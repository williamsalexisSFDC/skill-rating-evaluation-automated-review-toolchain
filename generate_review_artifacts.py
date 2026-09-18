#!/usr/bin/env python3
"""
Generate Google Drive review artifacts from skill validation output.

Produces one XLSX file with:
  - Tab 1: Manager Tracker  — all 148 records, disposition pre-filled, columns for
                              agreed rating and final action (Approve / Change To X)
  - Tab 2-N: One tab per employee — their skills, flags, cert evidence,
                              and blank Response / Proposed Change columns

Upload the XLSX to Google Drive as a Google Sheet (File → Save as Google Sheets)
then share each tab link with the relevant employee.

Usage:
    python3 generate_review_artifacts.py
"""

import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    _GDRIVE_API_AVAILABLE = True
except ImportError:  # pragma: no cover
    _GDRIVE_API_AVAILABLE = False

try:
    import openpyxl
    from openpyxl.styles import (
        PatternFill, Font, Alignment, Border, Side
    )
    from openpyxl.utils import get_column_letter
    from openpyxl.formatting.rule import FormulaRule
except ImportError:  # pragma: no cover
    sys.exit("openpyxl not found.  Run: pip3 install openpyxl --break-system-packages")

DOWNLOADS = Path(__file__).parent


# ── Colour palette ──────────────────────────────────────────────────────────────────────────────

RED    = PatternFill("solid", fgColor="FFCCCC")
YELLOW = PatternFill("solid", fgColor="FFF2CC")
GREEN  = PatternFill("solid", fgColor="D9EAD3")
BLUE   = PatternFill("solid", fgColor="CFE2F3")
GREY   = PatternFill("solid", fgColor="F3F3F3")
WHITE  = PatternFill("solid", fgColor="FFFFFF")
HEADER = PatternFill("solid", fgColor="1C4587")

HEADER_FONT    = Font(name="Arial", bold=True, color="FFFFFF", size=10)
BODY_FONT      = Font(name="Arial", size=10)
BOLD_FONT      = Font(name="Arial", bold=True, size=10)
SUBHEADER_FONT = Font(name="Arial", bold=True, size=10, color="1C4587")

THIN = Side(border_style="thin", color="CCCCCC")
CELL_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _border(ws, row, col):
    ws.cell(row=row, column=col).border = CELL_BORDER


def _calc_row_height(text_col_pairs: list, min_height: int = 15, max_height: int = 600) -> int:
    """
    Estimate row height in Excel points from wrapped text content.

    text_col_pairs: [(text, col_width_in_chars), ...]
    Each column's text is split on newlines and each paragraph's character count
    is divided by the column width to estimate wrapped line count.
    Line height is 13.5pt (Excel/Sheets default at Arial 10pt).

    Returns a clamped integer point value suitable for RowDimension.height.
    """
    LINE_HEIGHT_PTS  = 13.5   # points per line at Arial 10pt
    CHARS_PER_UNIT   = 0.88   # empirical: col width 52 ≈ 46 usable chars per line

    max_lines = 1
    for text, col_width in text_col_pairs:
        if not text:
            continue
        chars_per_line = max(int(col_width * CHARS_PER_UNIT), 8)
        total = 0.0
        for paragraph in str(text).split("\n"):
            total += max(1.0, len(paragraph) / chars_per_line)
        max_lines = max(max_lines, total)

    return max(min_height, min(int(max_lines * LINE_HEIGHT_PTS) + 6, max_height))


def _set_col_widths(ws, widths: dict):
    for col_letter, width in widths.items():
        ws.column_dimensions[col_letter].width = width


def _header_row(ws, row_num, cols, fill=HEADER, font=HEADER_FONT):
    for i, label in enumerate(cols, start=1):
        cell = ws.cell(row=row_num, column=i, value=label)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = CELL_BORDER


def _body_cell(ws, row, col, value, fill=WHITE, font=BODY_FONT, wrap=False, bold=False):
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill = fill
    cell.font = bold and BOLD_FONT or font
    cell.alignment = Alignment(wrap_text=wrap, vertical="top")
    cell.border = CELL_BORDER
    return cell


def _disposition_fill(status, cert_met):
    """Red = change required, Yellow = discuss, Green = approve."""
    if status == "NEEDS REVIEW":
        return RED
    return GREEN


def _row_fill(status):
    return YELLOW if status == "NEEDS REVIEW" else WHITE


# ── Pre-determine dispositions ────────────────────────────────────────────────────────────────

def _pre_disposition(notes: str) -> str:
    """
    Classify each record for the manager tracker:
      Approve        — no issues found
      Discuss        — flagged for cert or catalog mismatch only (low stakes)
      Change Required — below Agentforce minimum, below grade floor, Tier 1 cert missing,
                        or Tier 2 grade ceiling exceeded
    """
    if not notes:
        return "Approve"
    if "AGENTFORCE:" in notes or "DEVOPS:" in notes or "TIER2:" in notes:
        return "Change Required"
    return "Discuss"


# ── Manager Tracker tab ───────────────────────────────────────────────────────────────

TRACKER_COLS = [
    "Record ID",
    "Employee",
    "Grade",
    "Skill or Certification",
    "Self-Rating",
    "Cert Evidence",
    "Agentforce Required",
    "Grade Floor Met",
    "In PSA Catalog",
    "Validation Notes (Summary)",
    "Pre-Disposition",              # col K — auto-filled
    "Discussion Notes",             # col L — manager fills in post-conversation
    "Employee Proposed Change",     # col M — VLOOKUP from employee tab
    "Agreed Rating",                # col N — manager fills in
    "Final Action",                 # col O — Approve / Change To X / Reject
]

def build_manager_tracker(ws, records: list):
    ws.title = "Manager Tracker"
    ws.freeze_panes = "A2"

    _header_row(ws, 1, TRACKER_COLS)
    ws.row_dimensions[1].height = 30

    for i, r in enumerate(records, start=2):
        notes = r.get("Validation Notes", "")
        disp  = _pre_disposition(notes)
        fill  = RED if disp == "Change Required" else (YELLOW if disp == "Discuss" else GREEN)

        # VLOOKUP into the employee's tab (col A = Record ID, col M = Proposed Change)
        # INDIRECT("'"&LEFT(B{i},30)&"'!$A:$M") handles sheet names with spaces.
        proposed_formula = (
            f'=IFERROR(VLOOKUP(A{i},INDIRECT("\'"&LEFT(B{i},30)&"\'!$A:$M"),13,FALSE),"")'
        )

        vals = [
            r.get("Record ID", ""),
            r.get("Resource", ""),
            r.get("Employee Grade", ""),
            r.get("Skill or Certification", ""),
            r.get("Rating", ""),
            r.get("Supporting Cert", "") or "—",
            r.get("Is Agentforce Required", ""),
            r.get("Grade Floor Met", "") or "—",
            r.get("In PSA Catalog", ""),
            _summarize_notes(notes),
            disp,
            "",                  # col L — Discussion Notes (manager fills in)
            proposed_formula,    # col M — Employee Proposed Change (VLOOKUP)
            "",                  # col N — Agreed Rating (manager fills in)
            "",                  # col O — Final Action (manager fills in)
        ]
        for col, val in enumerate(vals, start=1):
            cell_fill = fill if col == 11 else WHITE  # colour only the Pre-Disposition col (K)
            _body_cell(ws, i, col, val, fill=cell_fill, wrap=(col in (4, 10)))

    _set_col_widths(ws, {
        "A": 20, "B": 18, "C": 9, "D": 34, "E": 16, "F": 36,
        "G": 12, "H": 13, "I": 12, "J": 50, "K": 18, "L": 26,
        "M": 22, "N": 16, "O": 18,
    })

    from openpyxl.worksheet.datavalidation import DataValidation

    # Agreed Rating dropdown (col N) — same 4 values as employee self-rating
    dv_rating = DataValidation(
        type="list",
        formula1=f'"{RATING_OPTIONS}"',
        allow_blank=True,
    )
    dv_rating.sqref = f"N2:N{len(records)+1}"
    ws.add_data_validation(dv_rating)

    # Final Action dropdown (col O)
    dv_action = DataValidation(
        type="list",
        formula1='"Approve,Change To — See Notes,Reject,Pending Discussion"',
        allow_blank=True,
    )
    dv_action.sqref = f"O2:O{len(records)+1}"
    ws.add_data_validation(dv_action)

    # Add colour legend below data
    legend_row = len(records) + 3
    ws.cell(row=legend_row, column=1, value="Colour Legend:").font = BOLD_FONT
    for offset, (label, fill) in enumerate([
        ("Change Required — below Agentforce/grade minimum", RED),
        ("Discuss — cert or catalog flag only", YELLOW),
        ("Approve — no issues found", GREEN),
    ], start=1):
        c = ws.cell(row=legend_row + offset, column=1, value=label)
        c.fill = fill
        c.font = BODY_FONT


def _summarize_notes(notes: str, full_justification: bool = False) -> str:
    """Collapse pipe-delimited notes to concise flags.

    full_justification=True: JUSTIFICATION REQUIRED entries are returned in full
    (for the employee tab where the employee needs to read the complete criteria).
    full_justification=False (default): a short pointer is used instead
    (for the manager tracker summary column).
    """
    if not notes:
        return ""
    parts = [n.strip() for n in notes.split("|")]
    short = []
    for p in parts:
        if p.startswith("AGENTFORCE:") and "delivery evidence" in p.lower():
            parts_d = []
            if "specialist certification not on file" in p.lower():
                parts_d.append("no AF Specialist cert")
            m = re.search(r"(\d+) qualifying.*?need (\d+)\+", p, re.IGNORECASE)
            if m:
                parts_d.append(f"{m.group(1)} RRs on file, need {m.group(2)}+")
            short.append("AF delivery: " + ("; ".join(parts_d) if parts_d else "evidence missing"))
        elif p.startswith("AGENTFORCE:") and "data 360" in p.lower():
            short.append("AF: Data Cloud cert required (Agentforce Specialist not sufficient)")
        elif p.startswith("AGENTFORCE:"):
            # Extract just the rating vs. required
            m = re.search(r"minimum rating of (\d)-\w+.*?rating: ([^.]+)", p)
            if m:
                short.append(f"AF: needs {m.group(1)}+, currently {m.group(2).strip()}")
            else:
                short.append("AF: evidence gap")
        elif p.startswith("DEVOPS:"):
            m = re.search(r"below the (.+?) minimum of (\d+)", p)
            if m:
                short.append(f"DevOps: {m.group(1)} needs {m.group(2)}+")
            else:
                short.append("DevOps: below grade floor")
        elif p.startswith("TIER2:"):
            m = re.search(r"exceeds the grade ceiling for (.+?)\.", p)
            if m:
                short.append(f"Tier 2 grade ceiling exceeded for {m.group(1).strip()}")
            else:
                short.append("Tier 2: rating exceeds grade ceiling (see employee tab)")
        elif p.startswith("CERT:"):
            short.append("No cert evidence for 4-Specialist claim")
        elif "not found in PSA catalog" in p:
            short.append("Not in PSA catalog (new skill — verify name)")
        elif p.startswith("AF NOT ENABLED:"):
            if full_justification:
                short.append(p)
            else:
                short.append(
                    "AF Not Enabled — complete Champion/Innovator/Legend Trailhead badges "
                    "+ Data Cloud/Data 360 Consultant cert first"
                )
        elif p.startswith("JUSTIFICATION REQUIRED:"):
            if full_justification:
                # Employee tab: show the complete criteria so the employee knows
                # exactly what delivery evidence to provide.
                short.append(p)
            else:
                # Manager tracker: brief pointer; full text is on the employee tab.
                short.append("Justification required — employee must provide delivery evidence (see employee tab for full criteria)")
        else:
            short.append(p[:80])
    return " | ".join(short)


# ── Per-employee tab ─────────────────────────────────────────────────────────────────────

EMP_COLS = [
    "Record ID",                       # hidden — VLOOKUP key for Manager Tracker linkage
    "Skill or Certification",
    "Skill Category",                  # Transferable / Group-Specific / Path-Specific
    "Your Self-Rating",
    "Evaluation Date",
    "Agentforce Required (min 3+)",
    "Your Grade Minimum",
    "Cert Evidence",
    "What This Level Requires",        # AF criteria for claimed/required level
    "Flags",
    "Suggested Cert Path",             # recommended cert when no corroboration exists
    "Your Response / Justification",   # employee fills in
    "Proposed Change",                 # employee fills in — leave blank or enter new rating (col M = 13)
]

RATING_OPTIONS = "1- Entry,2- Intermediate,3- Advanced,4- Specialist"


def build_employee_tab(ws, employee: str, grade: str, records: list, certs: list):
    ws.title = employee[:30]  # Sheet name limit
    ws.freeze_panes = "B3"   # freeze at B so the hidden Record ID col doesn't offset view

    # Row 1 — employee banner (spans all 13 columns)
    ws.merge_cells("A1:M1")
    banner = ws.cell(row=1, column=1,
                     value=f"{employee}  |  Grade: {grade}  |  Skill Rating Review — FY26")
    banner.fill = HEADER
    banner.font = Font(name="Arial", bold=True, color="FFFFFF", size=12)
    banner.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    # Row 2 — cert summary
    ws.merge_cells("A2:M2")
    cert_text = "Certifications on file: " + (
        "  |  ".join(
            f"{name}" + (f" ({date})" if date else "")
            for name, date in sorted(certs, key=lambda x: x[1] or "", reverse=True)
        ) if certs else "None on file"
    )
    cert_cell = ws.cell(row=2, column=1, value=cert_text)
    cert_cell.fill = BLUE
    cert_cell.font = Font(name="Arial", size=9, italic=True)
    cert_cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[2].height = 32

    # Row 3 — column headers
    _header_row(ws, 3, EMP_COLS)
    ws.row_dimensions[3].height = 30

    from openpyxl.worksheet.datavalidation import DataValidation
    dv = DataValidation(type="list", formula1=f'"{RATING_OPTIONS}"', allow_blank=True)
    ws.add_data_validation(dv)

    for i, r in enumerate(records, start=4):
        notes     = r.get("Validation Notes", "")
        disp      = _pre_disposition(notes)
        row_fill  = RED if disp == "Change Required" else (YELLOW if disp == "Discuss" else WHITE)

        grade_req   = _extract_grade_req(r.get("DevOps Grade Requirements", ""), grade)
        af_req      = "Yes — min 3+" if r.get("Is Agentforce Required") == "Yes" else ""
        cert_ev     = r.get("Supporting Cert", "") or "—"
        level_def   = r.get("AF Level Definition", "")
        flags       = _summarize_notes(notes, full_justification=True)
        cert_path   = r.get("Suggested Cert Path", "")
        skill_cat   = r.get("DevOps Skill Category", "")

        vals = [
            r.get("Record ID", ""),   # col 1 (A) — hidden VLOOKUP key
            r.get("Skill or Certification", ""),
            skill_cat,
            r.get("Rating", ""),
            r.get("Evaluation Date", ""),
            af_req,
            grade_req,
            cert_ev,
            level_def,   # What This Level Requires (col I)
            flags,       # col J
            cert_path,   # Suggested Cert Path (col K)
            "",          # employee response (col L)
            "",          # proposed change (col M = 13)
        ]
        for col, val in enumerate(vals, start=1):
            # wrap: skill(2), level def(9), flags(10), cert path(11), response(12)
            cell = _body_cell(ws, i, col, val, fill=row_fill, wrap=(col in (2, 9, 10, 11, 12)))
            if col == 13:  # Proposed Change — dropdown
                dv.add(cell)
        # Dynamically size the row based on the actual text in the three tall columns.
        # Col widths match _set_col_widths below: I=52, J=44, K=44.
        ws.row_dimensions[i].height = _calc_row_height([
            (level_def, 52),   # col I — What This Level Requires
            (flags,     44),   # col J — Flags
            (cert_path, 44),   # col K — Suggested Cert Path
        ])

    _set_col_widths(ws, {
        "A": 2,   # Record ID — visually hidden (keep narrow; column hidden below)
        "B": 34, "C": 20, "D": 16, "E": 15, "F": 20, "G": 20,
        "H": 32, "I": 52, "J": 44, "K": 44, "L": 36, "M": 20,
    })
    ws.column_dimensions["A"].hidden = True

    # Conditional format: when Proposed Change (col M) is filled in, flip the whole
    # visible row to green — signals the item has been discussed and agreed upon.
    # $M keeps the column anchor fixed; the row number is relative so it shifts per row.
    last_data_row = len(records) + 3
    ws.conditional_formatting.add(
        f"B4:M{last_data_row}",
        FormulaRule(formula=["NOT(ISBLANK($M4))"], fill=GREEN),
    )

    # Instructions note at bottom
    note_row = len(records) + 5
    ws.merge_cells(f"A{note_row}:M{note_row}")
    note = ws.cell(
        row=note_row, column=1,
        value=(
            "Instructions: Review flagged rows (red = change required, yellow = discuss). "
            "Column C shows skill category (Transferable / Group-Specific / Path-Specific). "
            "Column I shows the full criteria for the level in question. "
            "Column K shows a suggested certification path where no cert evidence exists. "
            "In column L add your justification or evidence. "
            "In column M select a proposed rating from the dropdown if you believe a change is warranted. "
            "Leave blank to accept the current rating."
        )
    )
    note.fill = GREY
    note.font = Font(name="Arial", size=9, italic=True, color="555555")
    note.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[note_row].height = 40


def _extract_grade_req(grade_reqs_str: str, emp_grade: str) -> str:
    """Pull just the employee's grade requirement from the full requirements string."""
    if not grade_reqs_str or not emp_grade:
        return ""
    for segment in grade_reqs_str.split(";"):
        if emp_grade.replace(" ", " ") in segment:
            m = re.search(r"(\d+)\+", segment)
            if m:
                return f"Min {m.group(1)}+ for {emp_grade}"
    return ""


# ── Summary / Cover tab ───────────────────────────────────────────────────────────────────

def build_cover(ws, records: list, certifications: dict, ts: str):
    ws.title = "Overview"
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 9
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 14
    ws.column_dimensions["E"].width = 20
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 50

    # Title
    ws.merge_cells("A1:G1")
    title = ws.cell(row=1, column=1, value="FY26 Skill Rating Review — Team Overview")
    title.fill = HEADER
    title.font = Font(name="Arial", bold=True, color="FFFFFF", size=14)
    title.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:G2")
    sub = ws.cell(row=2, column=1, value=f"Generated: {ts}  |  Total ratings under review: {len(records)}")
    sub.fill = BLUE
    sub.font = Font(name="Arial", size=10, italic=True)
    sub.alignment = Alignment(horizontal="center")
    ws.row_dimensions[2].height = 18

    # Per-employee summary
    _header_row(ws, 4, [
        "Employee", "Grade", "Total Skills", "Needs Review",
        "Cert-Corroborated", "Total Certs", "Key Flags"
    ])

    by_emp = defaultdict(lambda: {
        "grade": "", "total": 0, "review": 0, "cert_corr": 0, "flags": []
    })
    for r in records:
        emp = r["Resource"]
        by_emp[emp]["grade"]  = r.get("Employee Grade", "")
        by_emp[emp]["total"] += 1
        if r["Validation Status"] == "NEEDS REVIEW":
            by_emp[emp]["review"] += 1
        if r.get("Cert Corroborates Skill") == "Yes":
            by_emp[emp]["cert_corr"] += 1
        d = _pre_disposition(r.get("Validation Notes", ""))
        if d == "Change Required":
            by_emp[emp]["flags"].append(r["Skill or Certification"])

    for row_i, (emp, d) in enumerate(sorted(by_emp.items()), start=5):
        pct = round(d["review"] / d["total"] * 100) if d["total"] else 0
        flag_fill = RED if pct >= 30 else (YELLOW if pct > 0 else GREEN)
        vals = [
            emp,
            d["grade"],
            d["total"],
            f"{d['review']} ({pct}%)",
            d["cert_corr"],
            len(certifications.get(emp, [])),
            "; ".join(d["flags"][:5]) + (" …" if len(d["flags"]) > 5 else ""),
        ]
        for col, val in enumerate(vals, start=1):
            cell_fill = flag_fill if col == 4 else WHITE
            _body_cell(ws, row_i, col, val, fill=cell_fill, wrap=(col == 7))

    # Disposition legend
    leg_row = len(by_emp) + 7
    ws.cell(row=leg_row, column=1, value="Action Required Summary").font = BOLD_FONT
    disp_counts = defaultdict(int)
    for r in records:
        disp_counts[_pre_disposition(r.get("Validation Notes", ""))] += 1

    for off, (label, fill) in enumerate([
        (f"Approve ({disp_counts['Approve']} records) — no action needed", GREEN),
        (f"Discuss ({disp_counts['Discuss']} records) — cert/catalog flag, low stakes", YELLOW),
        (f"Change Required ({disp_counts['Change Required']} records) — below Agentforce or grade minimum", RED),
    ], start=1):
        c = ws.cell(row=leg_row + off, column=1, value=label)
        c.fill = fill
        c.font = BODY_FONT

    # Process instructions
    inst_row = leg_row + 6
    ws.merge_cells(f"A{inst_row}:G{inst_row}")
    ws.cell(row=inst_row, column=1, value="PROCESS").font = SUBHEADER_FONT
    steps = [
        "1. Share each employee's tab with them via Google Drive.  They fill in columns H (justification) and I (proposed change).",
        "2. Hold 1:1 discussions for all red rows.  Update 'Manager Tracker' tab with agreed rating and discussion notes.",
        "3. In org62 Mass Approve UI, use the Manager Tracker as your reference.  Approve green rows in bulk; update or reject red rows individually.",
        "4. After all approvals, re-run validate_skill_ratings.py to confirm the final state.",
    ]
    for s_off, step in enumerate(steps, start=1):
        ws.cell(row=inst_row + s_off, column=1, value=step).font = Font(name="Arial", size=10)
        ws.merge_cells(f"A{inst_row+s_off}:G{inst_row+s_off}")
        ws.row_dimensions[inst_row + s_off].height = 18


# ── Google Drive upload ───────────────────────────────────────────────────────────────

_GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_PATH    = Path.home() / ".gdrive_token.json"
_CREDS_PATH    = Path.home() / ".gdrive_credentials.json"

_SETUP_INSTRUCTIONS = """
  One-time setup to enable automated upload:

  1. Go to https://console.cloud.google.com/ and create a project (or select one).
  2. Enable the Google Drive API:
       APIs & Services → Library → "Google Drive API" → Enable
  3. Create OAuth credentials:
       APIs & Services → Credentials → + Create Credentials → OAuth client ID
       Application type: Desktop app  →  Create  →  Download JSON
  4. Save the downloaded file as:
       ~/.gdrive_credentials.json
  5. Re-run this script — your browser will open once for consent, then
     all future runs upload silently.
"""


def _get_drive_service():
    creds = None
    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _GDRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(_CREDS_PATH), _GDRIVE_SCOPES
            )
            creds = flow.run_local_server(port=0, open_browser=True)
        _TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


def upload_to_google_drive(xlsx_path: Path) -> None:
    """Upload xlsx_path to Google Drive via the Drive API.

    Requires a one-time OAuth credentials setup (see _SETUP_INSTRUCTIONS).
    Subsequent runs reuse the saved token silently.
    If skill_rating_review.xlsx already exists it is updated in-place.
    """
    import subprocess, shutil

    file_name = xlsx_path.name

    if not _GDRIVE_API_AVAILABLE:
        print("\ngoogle-api-python-client not installed.")
        print("  Run: pip3 install google-api-python-client google-auth-oauthlib")
        _open_drive_for_manual_upload(xlsx_path)
        return

    if not _CREDS_PATH.exists():
        print(f"\n  ~/.gdrive_credentials.json not found.{_SETUP_INSTRUCTIONS}")
        _open_drive_for_manual_upload(xlsx_path)
        return

    print(f"\nUploading {file_name} to Google Drive...")
    try:
        service = _get_drive_service()
    except Exception as exc:
        print(f"  OAuth failed: {exc}")
        _open_drive_for_manual_upload(xlsx_path)
        return

    mime  = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    media = MediaFileUpload(str(xlsx_path), mimetype=mime, resumable=True)

    existing = service.files().list(
        q=f"name='{file_name}' and trashed=false",
        spaces="drive",
        fields="files(id,name)",
    ).execute().get("files", [])

    if existing:
        file_id = existing[0]["id"]
        service.files().update(fileId=file_id, media_body=media).execute()
        print(f"  Updated existing file (ID {file_id}).")
    else:
        f = service.files().create(
            body={"name": file_name}, media_body=media, fields="id"
        ).execute()
        print(f"  Uploaded new file (ID {f['id']}).")

    print("  Google Drive upload complete.")


def _open_drive_for_manual_upload(xlsx_path: Path) -> None:
    """Open Google Drive in Chrome and reveal the file in Finder so it's easy to drag in."""
    import subprocess
    print(f"\n  Opening Google Drive in Chrome for manual upload.")
    print(f"  File to upload: {xlsx_path}")
    print(f"  Drag it into the Drive window, or use New → File upload.\n")
    try:
        subprocess.run(
            ["osascript", "-e",
             'tell application "Google Chrome" to open location "https://drive.google.com/drive/my-drive"'],
            check=False,
        )
        subprocess.run(["open", "-R", str(xlsx_path)], check=False)
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────────────

def find_latest_detail() -> Path:
    candidates = sorted(DOWNLOADS.glob("skill_validation_detail_*.csv"),
                        key=lambda p: p.stat().st_mtime)
    if not candidates:
        sys.exit("No skill_validation_detail_*.csv found. Run validate_skill_ratings.py first.")
    return candidates[-1]


def load_certifications() -> dict:
    path = DOWNLOADS / "employee_certifications.csv"
    certs = defaultdict(list)
    if path.exists():
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                certs[row["Employee"].strip()].append(
                    (row["Certification"].strip(), row.get("Earned Date", "").strip())
                )
    return dict(certs)


def main():
    detail_path = find_latest_detail()
    print(f"Loading: {detail_path.name}")

    with open(detail_path, encoding="utf-8") as f:
        records = list(csv.DictReader(f))

    certifications = load_certifications()

    # Group by employee
    by_emp = defaultdict(list)
    for r in records:
        by_emp[r["Resource"]].append(r)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    ts_file = datetime.now().strftime("%Y%m%d_%H%M%S")

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default sheet

    # Cover / overview tab first
    cover_ws = wb.create_sheet("Overview")
    build_cover(cover_ws, records, certifications, ts)

    # Manager tracker tab
    tracker_ws = wb.create_sheet("Manager Tracker")
    build_manager_tracker(tracker_ws, records)

    # One tab per employee (alphabetical)
    for emp in sorted(by_emp.keys()):
        emp_records = by_emp[emp]
        grade = emp_records[0].get("Employee Grade", "Unknown")
        certs = certifications.get(emp, [])
        ws = wb.create_sheet()
        build_employee_tab(ws, emp, grade, emp_records, certs)
        print(f"  → {emp}: {len(emp_records)} skills, "
              f"{sum(1 for r in emp_records if r['Validation Status']=='NEEDS REVIEW')} flagged")

    out_path = DOWNLOADS / "skill_rating_review.xlsx"
    wb.save(out_path)
    print(f"\nSaved: {out_path}")

    upload_to_google_drive(out_path)

    print(f"\nNext step: open the file in Google Drive → File → Save as Google Sheets")
    print(f"Then share individual tabs with each employee.")


if __name__ == "__main__":  # pragma: no cover
    main()
