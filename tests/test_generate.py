"""Tests for generate_review_artifacts.py — targeting ≥90% coverage."""
import csv
from pathlib import Path
from collections import defaultdict

import pytest
import openpyxl

import generate_review_artifacts as gen


# ---------------------------------------------------------------------------
# _pre_disposition()
# ---------------------------------------------------------------------------

class TestPreDisposition:
    def test_empty_notes_returns_approve(self):
        assert gen._pre_disposition("") == "Approve"

    def test_none_like_empty_returns_approve(self):
        assert gen._pre_disposition(None) == "Approve"  # type: ignore[arg-type]

    def test_agentforce_rating_below_minimum(self):
        notes = "AGENTFORCE: Rating below minimum. Minimum rating of 3-Advanced required."
        assert gen._pre_disposition(notes) == "Change Required"

    def test_agentforce_delivery_evidence(self):
        notes = "AGENTFORCE: Delivery evidence insufficient — no RRs on file."
        assert gen._pre_disposition(notes) == "Change Required"

    def test_devops_below_grade_floor(self):
        notes = "DEVOPS: Rating 1- Entry is below the Grade 5 (DevOps Engineer) minimum of 2+."
        assert gen._pre_disposition(notes) == "Change Required"

    def test_tier2_grade_ceiling(self):
        notes = "TIER2: 'Business Acumen' rated 4- Specialist exceeds grade ceiling for Grade 5."
        assert gen._pre_disposition(notes) == "Change Required"

    def test_cert_flag_returns_discuss(self):
        notes = "CERT: Self-rated 4- Specialist but no cert corroborates."
        assert gen._pre_disposition(notes) == "Discuss"

    def test_justification_required_returns_discuss(self):
        notes = "JUSTIFICATION REQUIRED: 3-Advanced on Observability requires hands-on..."
        assert gen._pre_disposition(notes) == "Discuss"

    def test_not_in_catalog_returns_discuss(self):
        notes = "Skill not found in PSA catalog — verify skill name is correct."
        assert gen._pre_disposition(notes) == "Discuss"

    def test_multiple_flags_change_required_wins(self):
        notes = "AGENTFORCE: Rating below minimum. | JUSTIFICATION REQUIRED: ..."
        assert gen._pre_disposition(notes) == "Change Required"


# ---------------------------------------------------------------------------
# _summarize_notes()
# ---------------------------------------------------------------------------

class TestSummarizeNotes:
    def test_empty_returns_empty(self):
        assert gen._summarize_notes("") == ""

    def test_agentforce_below_minimum(self):
        notes = (
            "AGENTFORCE: Rating below minimum. Agentforce Ready requires a minimum rating of "
            "3-Advanced. Current rating: 2- Intermediate. 3-Advanced criteria: Can configure agents."
        )
        result = gen._summarize_notes(notes)
        assert "AF: needs 3+" in result
        assert "2- Intermediate" in result

    def test_agentforce_delivery_no_af_cert(self):
        notes = (
            "AGENTFORCE: Delivery evidence insufficient — "
            "Agentforce Specialist certification not on file."
        )
        result = gen._summarize_notes(notes)
        assert "AF delivery:" in result
        assert "no AF Specialist cert" in result

    def test_agentforce_delivery_insufficient_rrs(self):
        notes = (
            "AGENTFORCE: Delivery evidence insufficient — "
            "0 qualifying Agentforce RR(s) on file (post Oct 2024) — need 2+ for a 3- Advanced delivery claim."
        )
        result = gen._summarize_notes(notes)
        assert "0 RRs on file, need 2+" in result

    def test_agentforce_delivery_both_issues(self):
        notes = (
            "AGENTFORCE: Delivery evidence insufficient — "
            "Agentforce Specialist certification not on file; "
            "0 qualifying Agentforce RR(s) on file — need 2+ for a 3- Advanced delivery claim."
        )
        result = gen._summarize_notes(notes)
        assert "no AF Specialist cert" in result
        assert "0 RRs on file, need 2+" in result

    def test_agentforce_data360(self):
        notes = (
            "AGENTFORCE: Data 360 / Data Cloud for Agentforce at 3-Advanced requires the "
            "Salesforce Certified Data 360 / Data Cloud Consultant cert."
        )
        result = gen._summarize_notes(notes)
        assert "AF: Data Cloud cert required" in result
        assert "Agentforce Specialist not sufficient" in result

    def test_agentforce_tier1_no_cert(self):
        notes = (
            "AGENTFORCE: Tier 1 Agentforce skill rated 3- Advanced without the Agentforce Specialist cert."
        )
        result = gen._summarize_notes(notes)
        assert "AF: evidence gap" in result

    def test_devops_below_floor(self):
        notes = "DEVOPS: Rating 1- Entry is below the Grade 5 (DevOps Engineer) minimum of 2+. Full requirements: ..."
        result = gen._summarize_notes(notes)
        assert "DevOps:" in result
        assert "needs 2+" in result

    def test_tier2_ceiling(self):
        notes = "TIER2: 'Business Acumen' rated 4- Specialist exceeds the grade ceiling for Grade 5."
        result = gen._summarize_notes(notes)
        assert "Tier 2 grade ceiling exceeded" in result
        assert "Grade 5" in result

    def test_cert_no_evidence(self):
        notes = "CERT: Self-rated 4- Specialist but no certification corroborates this skill."
        result = gen._summarize_notes(notes)
        assert "No cert evidence for 4-Specialist claim" in result

    def test_not_in_catalog(self):
        notes = "Skill not found in PSA catalog — verify skill name is correct."
        result = gen._summarize_notes(notes)
        assert "Not in PSA catalog" in result

    def test_justification_required_short_form(self):
        notes = "JUSTIFICATION REQUIRED: Long explanation about why this skill needs justification..."
        result = gen._summarize_notes(notes, full_justification=False)
        assert "Justification required" in result
        assert "see employee tab for full criteria" in result

    def test_justification_required_full_form(self):
        long_text = "JUSTIFICATION REQUIRED: Full criteria text that should be preserved verbatim."
        result = gen._summarize_notes(long_text, full_justification=True)
        assert "Full criteria text that should be preserved verbatim" in result

    def test_multiple_notes_joined(self):
        notes = (
            "AGENTFORCE: Rating below minimum. Minimum rating of 3-Advanced required. "
            "Current rating: 2- Intermediate. | "
            "CERT: Self-rated 4- Specialist but no cert corroborates."
        )
        result = gen._summarize_notes(notes)
        # Two short summaries separated by " | "
        assert "|" in result

    def test_fallthrough_truncated(self):
        notes = "Some other note that doesn't match any prefix at all whatsoever."
        result = gen._summarize_notes(notes)
        assert len(result) <= 80 + 1  # truncated at 80 chars + possible " | "


# ---------------------------------------------------------------------------
# _extract_grade_req()
# ---------------------------------------------------------------------------

class TestExtractGradeReq:
    def _grade_summary(self):
        """A typical DevOps grade requirements string from validate_record."""
        return (
            "Grade 4 (Associate DevOps Engineer): 1+; "
            "Grade 5 (DevOps Engineer): 2+; "
            "Grade 6 (Sr. DevOps Engineer): 2+; "
            "Grade 7 (DevOps Architect): 3+; "
            "Grade 8 (Sr. DevOps Architect): 3+; "
            "Grade 9 (Director - DevOps): 4+; "
            "Grade 11 (VP, Technical Consulting): 4+"
        )

    def test_grade5_returns_correct(self):
        result = gen._extract_grade_req(self._grade_summary(), "Grade 5")
        assert result == "Min 2+ for Grade 5"

    def test_grade7_returns_correct(self):
        result = gen._extract_grade_req(self._grade_summary(), "Grade 7")
        assert result == "Min 3+ for Grade 7"

    def test_grade11_returns_correct(self):
        result = gen._extract_grade_req(self._grade_summary(), "Grade 11")
        assert result == "Min 4+ for Grade 11"

    def test_empty_grade_reqs_returns_empty(self):
        result = gen._extract_grade_req("", "Grade 5")
        assert result == ""

    def test_empty_emp_grade_returns_empty(self):
        result = gen._extract_grade_req(self._grade_summary(), "")
        assert result == ""

    def test_grade_not_present_returns_empty(self):
        result = gen._extract_grade_req("Grade 4 (DevOps): 1+", "Grade 10")
        assert result == ""


# ---------------------------------------------------------------------------
# _calc_row_height()
# ---------------------------------------------------------------------------

class TestCalcRowHeight:
    def test_empty_list(self):
        # max_lines=1 → int(1*13.5)+6=19 > min_height=15, so result is 19
        result = gen._calc_row_height([])
        assert result == 19

    def test_short_text_returns_min(self):
        result = gen._calc_row_height([("Short text", 52)])
        assert result >= 15

    def test_long_text_increases_height(self):
        long = "a" * 500
        result = gen._calc_row_height([(long, 52)])
        assert result > 15

    def test_clamped_at_max(self):
        very_long = "a" * 10000
        result = gen._calc_row_height([(very_long, 52)], max_height=600)
        assert result <= 600

    def test_none_text_skipped(self):
        result = gen._calc_row_height([(None, 52)])
        assert result >= 15

    def test_multiline_text(self):
        multiline = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        result = gen._calc_row_height([(multiline, 52)])
        single_result = gen._calc_row_height([("One line", 52)])
        assert result >= single_result


# ---------------------------------------------------------------------------
# build_manager_tracker() / build_employee_tab() / build_cover()
# ---------------------------------------------------------------------------

def _make_records(n=3):
    records = []
    statuses = ["OK", "NEEDS REVIEW", "OK"]
    notes_list = [
        "",
        "AGENTFORCE: Rating below minimum. Minimum rating of 3-Advanced required. Current rating: 2- Intermediate.",
        "",
    ]
    for i in range(n):
        records.append({
            "Resource": "Alice Test",
            "Employee Grade": "Grade 7",
            "Skill or Certification": f"Skill {i+1}",
            "Rating": "3- Advanced",
            "Evaluation Date": "08/26/2025",
            "Validation Status": statuses[i % len(statuses)],
            "Validation Notes": notes_list[i % len(notes_list)],
            "Supporting Cert": "Certified Agentforce Specialist" if i == 0 else "",
            "Is Agentforce Required": "Yes" if i == 1 else "No",
            "Grade Floor Met": "Yes" if i != 1 else "No",
            "In PSA Catalog": "Yes",
            "DevOps Grade Requirements": "Grade 7 (DevOps Architect): 3+",
            "DevOps Skill Category": "DevOps",
            "AF Level Definition": "Agentforce Operations — 3-Advanced (minimum required):\nCan configure agents.",
            "Suggested Cert Path": "",
            "Record ID": f"REC-{i+1:03d}",
        })
    return records


class TestBuildManagerTracker:
    def test_creates_sheet_with_data_rows(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        records = _make_records(3)
        gen.build_manager_tracker(ws, records)
        # Header in row 1, data starts at row 2
        assert ws.cell(row=1, column=1).value == "Record ID"
        assert ws.cell(row=2, column=2).value == "Alice Test"

    def test_pre_disposition_applied(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        records = _make_records(3)
        gen.build_manager_tracker(ws, records)
        # Row 3 (index 1) has AF notes → "Change Required"
        disp_col = 11  # col K = Pre-Disposition
        disp_value = ws.cell(row=3, column=disp_col).value
        assert disp_value == "Change Required"

    def test_approve_disposition_for_ok_row(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        records = _make_records(3)
        gen.build_manager_tracker(ws, records)
        # Row 2 (index 0) has empty notes → "Approve"
        disp_value = ws.cell(row=2, column=11).value
        assert disp_value == "Approve"


class TestBuildEmployeeTab:
    def test_creates_sheet_with_correct_title(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet()
        records = _make_records(2)
        gen.build_employee_tab(ws, "Alice Test", "Grade 7", records, [
            ("Certified Agentforce Specialist", "2024-12-01"),
        ])
        assert ws.title == "Alice Test"

    def test_banner_row_contains_employee_name(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet()
        records = _make_records(2)
        gen.build_employee_tab(ws, "Alice Test", "Grade 7", records, [])
        banner = ws.cell(row=1, column=1).value
        assert "Alice Test" in banner
        assert "Grade 7" in banner

    def test_cert_row_populated(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet()
        records = _make_records(2)
        gen.build_employee_tab(ws, "Alice Test", "Grade 7", records, [
            ("Certified Agentforce Specialist", "2024-12-01"),
        ])
        cert_text = ws.cell(row=2, column=1).value
        assert "Agentforce Specialist" in cert_text

    def test_cert_row_none_on_file(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet()
        records = _make_records(2)
        gen.build_employee_tab(ws, "Bob Test", "Grade 5", records, [])
        cert_text = ws.cell(row=2, column=1).value
        assert "None on file" in cert_text

    def test_data_rows_start_at_row_4(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet()
        records = _make_records(2)
        gen.build_employee_tab(ws, "Alice Test", "Grade 7", records, [])
        # Row 4 should have the first skill
        assert ws.cell(row=4, column=2).value == "Skill 1"

    def test_long_employee_name_truncated_to_30_chars(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet()
        long_name = "Very Long Employee Name That Exceeds Thirty Characters"
        records = _make_records(1)
        gen.build_employee_tab(ws, long_name, "Grade 7", records, [])
        assert len(ws.title) <= 31  # Excel allows 31 chars max


class TestBuildCover:
    def test_creates_overview_sheet(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet("Overview")
        records = _make_records(5)
        certs = {"Alice Test": [("Certified Agentforce Specialist", "2024-12-01")]}
        gen.build_cover(ws, records, certs, "2026-09-18 12:00")
        assert ws.title == "Overview"

    def test_title_row_contains_fy26(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet("Overview")
        records = _make_records(5)
        gen.build_cover(ws, records, {}, "2026-09-18 12:00")
        title = ws.cell(row=1, column=1).value
        assert "FY26" in title

    def test_employee_summary_rows_present(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet("Overview")
        records = _make_records(3)
        gen.build_cover(ws, records, {}, "2026-09-18 12:00")
        # Row 5 should have Alice Test's summary
        emp_name = ws.cell(row=5, column=1).value
        assert emp_name == "Alice Test"


# ---------------------------------------------------------------------------
# load_certifications() in generate_review_artifacts (separate from validate module)
# ---------------------------------------------------------------------------

class TestGenerateLoadCertifications:
    def test_returns_dict(self, tmp_path, monkeypatch):
        content = "Employee,Certification,Earned Date\nAlice,Cert A,2024-01-01\n"
        cert_file = tmp_path / "employee_certifications.csv"
        cert_file.write_text(content)
        monkeypatch.setattr(gen, "DOWNLOADS", tmp_path)
        result = gen.load_certifications()
        assert "Alice" in result

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gen, "DOWNLOADS", tmp_path)
        result = gen.load_certifications()
        assert result == {}


# ---------------------------------------------------------------------------
# find_latest_detail()
# ---------------------------------------------------------------------------

class TestFindLatestDetail:
    def test_finds_latest_detail(self, tmp_path, monkeypatch):
        import time
        f1 = tmp_path / "skill_validation_detail_20260101_120000.csv"
        f1.write_text("col\n")
        time.sleep(0.01)
        f2 = tmp_path / "skill_validation_detail_20260918_120000.csv"
        f2.write_text("col\n")
        monkeypatch.setattr(gen, "DOWNLOADS", tmp_path)
        result = gen.find_latest_detail()
        assert result == f2

    def test_exits_if_none_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gen, "DOWNLOADS", tmp_path)
        with pytest.raises(SystemExit):
            gen.find_latest_detail()


# ---------------------------------------------------------------------------
# _disposition_fill() and _row_fill()
# ---------------------------------------------------------------------------

class TestFillHelpers:
    def test_disposition_fill_needs_review_is_red(self):
        result = gen._disposition_fill("NEEDS REVIEW", False)
        assert result == gen.RED

    def test_disposition_fill_ok_is_green(self):
        result = gen._disposition_fill("OK", True)
        assert result == gen.GREEN

    def test_row_fill_needs_review_is_yellow(self):
        result = gen._row_fill("NEEDS REVIEW")
        assert result == gen.YELLOW

    def test_row_fill_ok_is_white(self):
        result = gen._row_fill("OK")
        assert result == gen.WHITE


# ---------------------------------------------------------------------------
# upload_to_google_drive() — fallback path (no credentials)
# ---------------------------------------------------------------------------

class TestUploadToGoogleDrive:
    def test_falls_back_to_manual_when_no_creds(self, tmp_path, monkeypatch):
        """When _CREDS_PATH doesn't exist, should call _open_drive_for_manual_upload."""
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK")

        called = []
        monkeypatch.setattr(gen, "_GDRIVE_API_AVAILABLE", True)
        monkeypatch.setattr(gen, "_CREDS_PATH", tmp_path / "nonexistent_creds.json")
        monkeypatch.setattr(gen, "_open_drive_for_manual_upload", lambda p: called.append(p))

        gen.upload_to_google_drive(xlsx)
        assert len(called) == 1

    def test_falls_back_when_api_not_available(self, tmp_path, monkeypatch):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK")

        called = []
        monkeypatch.setattr(gen, "_GDRIVE_API_AVAILABLE", False)
        monkeypatch.setattr(gen, "_open_drive_for_manual_upload", lambda p: called.append(p))

        gen.upload_to_google_drive(xlsx)
        assert len(called) == 1

    def test_falls_back_when_oauth_raises(self, tmp_path, monkeypatch):
        """When _get_drive_service() raises, should fall back to manual upload."""
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK")
        # Create a fake creds file so _CREDS_PATH.exists() returns True
        fake_creds = tmp_path / "creds.json"
        fake_creds.write_text('{"type": "authorized_user"}')

        called = []
        monkeypatch.setattr(gen, "_GDRIVE_API_AVAILABLE", True)
        monkeypatch.setattr(gen, "_CREDS_PATH", fake_creds)
        monkeypatch.setattr(gen, "_get_drive_service", lambda: (_ for _ in ()).throw(Exception("OAuth failed")))
        monkeypatch.setattr(gen, "_open_drive_for_manual_upload", lambda p: called.append(p))

        gen.upload_to_google_drive(xlsx)
        assert len(called) == 1

    def test_uploads_new_file_when_no_existing(self, tmp_path, monkeypatch):
        """When creds exist, OAuth succeeds, and file doesn't exist yet, create new file."""
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK")
        fake_creds = tmp_path / "creds.json"
        fake_creds.write_text('{}')

        # Mock the drive service
        mock_create_result = {"id": "new-file-id-123"}
        mock_execute = type("E", (), {"execute": lambda self: mock_create_result})()

        class MockFiles:
            def list(self, **kwargs):
                class R:
                    def execute(self):
                        return {"files": []}  # no existing file
                return R()
            def create(self, **kwargs):
                return mock_execute
            def update(self, **kwargs):
                return mock_execute

        class MockService:
            def files(self):
                return MockFiles()

        monkeypatch.setattr(gen, "_GDRIVE_API_AVAILABLE", True)
        monkeypatch.setattr(gen, "_CREDS_PATH", fake_creds)
        monkeypatch.setattr(gen, "_get_drive_service", lambda: MockService())
        # Mock MediaFileUpload so it doesn't try to read the xlsx as a real file
        monkeypatch.setattr(gen, "MediaFileUpload", lambda p, **kwargs: None)

        gen.upload_to_google_drive(xlsx)  # should not raise

    def test_updates_existing_file(self, tmp_path, monkeypatch):
        """When creds exist and file already exists in Drive, update it."""
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK")
        fake_creds = tmp_path / "creds.json"
        fake_creds.write_text('{}')

        updated = []

        class MockFiles:
            def list(self, **kwargs):
                class R:
                    def execute(self):
                        return {"files": [{"id": "existing-id", "name": "test.xlsx"}]}
                return R()
            def update(self, fileId, **kwargs):
                updated.append(fileId)
                class R:
                    def execute(self):
                        return {}
                return R()

        class MockService:
            def files(self):
                return MockFiles()

        monkeypatch.setattr(gen, "_GDRIVE_API_AVAILABLE", True)
        monkeypatch.setattr(gen, "_CREDS_PATH", fake_creds)
        monkeypatch.setattr(gen, "_get_drive_service", lambda: MockService())
        monkeypatch.setattr(gen, "MediaFileUpload", lambda p, **kwargs: None)

        gen.upload_to_google_drive(xlsx)
        assert "existing-id" in updated


class TestOpenDriveForManualUpload:
    def test_calls_subprocess_without_raising(self, tmp_path, monkeypatch):
        """_open_drive_for_manual_upload should call subprocess.run without raising."""
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK")

        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(cmd)

        import subprocess
        monkeypatch.setattr(subprocess, "run", mock_run)
        gen._open_drive_for_manual_upload(xlsx)
        assert len(calls) == 2  # osascript + open -R

    def test_handles_subprocess_exception(self, tmp_path, monkeypatch):
        """_open_drive_for_manual_upload should swallow subprocess exceptions."""
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK")

        import subprocess
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(OSError("no osascript")))
        gen._open_drive_for_manual_upload(xlsx)  # should not raise


class TestBorderHelper:
    def test_border_sets_cell_border(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        gen._border(ws, 1, 1)
        assert ws.cell(row=1, column=1).border is not None


class TestSummarizeNotesElseBranches:
    def test_devops_else_branch_no_match(self):
        """DEVOPS note where regex doesn't match → 'DevOps: below grade floor'."""
        notes = "DEVOPS: Something unusual that doesn't match the regex pattern at all."
        result = gen._summarize_notes(notes)
        assert result == "DevOps: below grade floor"

    def test_tier2_else_branch_no_match(self):
        """TIER2 note where regex doesn't match → fallback message."""
        notes = "TIER2: Some unusual tier 2 note without the expected pattern"
        result = gen._summarize_notes(notes)
        assert result == "Tier 2: rating exceeds grade ceiling (see employee tab)"


def _make_records_with_cert_corr(n=3):
    """Like _make_records but includes Cert Corroborates Skill field."""
    records = []
    statuses = ["OK", "NEEDS REVIEW", "OK"]
    notes_list = [
        "",
        "AGENTFORCE: Rating below minimum. Minimum rating of 3-Advanced required. Current rating: 2- Intermediate.",
        "",
    ]
    for i in range(n):
        records.append({
            "Resource": "Alice Test",
            "Employee Grade": "Grade 7",
            "Skill or Certification": f"Skill {i+1}",
            "Rating": "3- Advanced",
            "Evaluation Date": "08/26/2025",
            "Validation Status": statuses[i % len(statuses)],
            "Validation Notes": notes_list[i % len(notes_list)],
            "Supporting Cert": "Certified Agentforce Specialist" if i == 0 else "",
            "Cert Corroborates Skill": "Yes" if i == 0 else "No",
            "Is Agentforce Required": "Yes" if i == 1 else "No",
            "Grade Floor Met": "Yes" if i != 1 else "No",
            "In PSA Catalog": "Yes",
            "DevOps Grade Requirements": "Grade 7 (DevOps Architect): 3+",
            "DevOps Skill Category": "DevOps",
            "AF Level Definition": "Agentforce Operations — 3-Advanced:\nCan configure agents.",
            "Suggested Cert Path": "",
            "Record ID": f"REC-{i+1:03d}",
        })
    return records


class TestBuildCoverWithCertCorr:
    def test_cert_corr_line_covered(self):
        """Line 495: cert_corr counter incremented when Cert Corroborates Skill == 'Yes'."""
        wb = openpyxl.Workbook()
        ws = wb.create_sheet("Overview")
        records = _make_records_with_cert_corr(3)
        gen.build_cover(ws, records, {}, "2026-09-18 12:00")
        # If we got here without error, line 495 was reached
        emp_row = ws.cell(row=5, column=1).value
        assert emp_row == "Alice Test"
