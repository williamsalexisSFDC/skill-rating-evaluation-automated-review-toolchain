"""Tests for mass_approve_skills.py — targeting ≥90% coverage."""
import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

import mass_approve_skills as mas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path, rows, headers=None):
    """Write a Manager Tracker–shaped CSV to *path*."""
    if headers is None:
        headers = [
            "Record ID", "Employee", "Grade", "Skill or Certification",
            "Self-Rating", "Cert Evidence", "Agentforce Required",
            "Grade Floor Met", "In PSA Catalog", "Validation Notes (Summary)",
            "Pre-Disposition", "Discussion Notes", "Employee Proposed Change",
            "Agreed Rating", "Final Action",
        ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _make_mock_page():
    """Return a MagicMock that behaves like a Playwright page."""
    page = MagicMock()
    page.query_selector_all.return_value = []
    return page


def _make_tr_mock(employee, skill, row_key="REC001", checked=False):
    """Build a mock <tr> element with the expected cell layout."""
    tr = MagicMock()
    tr.get_attribute.return_value = row_key

    # Cells: [checkbox-col, Rating-Id, Resource, Skill, ...]
    cells = []
    for text in ["", "Rating001", employee, skill, "01/01/2025", "", "3-Advanced", "", "Submitted"]:
        cell = MagicMock()
        cell.inner_text.return_value = text
        cells.append(cell)
    tr.query_selector_all.return_value = cells

    checkbox = MagicMock()
    checkbox.is_checked.return_value = checked
    tr.query_selector.return_value = checkbox

    return tr, checkbox


# ---------------------------------------------------------------------------
# load_csv
# ---------------------------------------------------------------------------

class TestLoadCsv:
    def test_separates_approve_and_reject(self, tmp_path):
        csv_file = tmp_path / "tracker.csv"
        _write_csv(csv_file, [
            {"Record ID": "R1", "Employee": "Alice", "Skill or Certification": "Docker",
             "Discussion Notes": "ok", "Final Action": "Approve"},
            {"Record ID": "R2", "Employee": "Bob", "Skill or Certification": "K8s",
             "Discussion Notes": "needs work", "Final Action": "Reject"},
        ])
        approvals, rejections = mas.load_csv(csv_file)
        assert len(approvals) == 1
        assert approvals[0]["employee"] == "Alice"
        assert approvals[0]["skill"] == "Docker"
        assert len(rejections) == 1
        assert rejections[0]["employee"] == "Bob"
        assert rejections[0]["notes"] == "needs work"

    def test_blank_action_excluded(self, tmp_path):
        csv_file = tmp_path / "tracker.csv"
        _write_csv(csv_file, [
            {"Record ID": "R1", "Employee": "Alice", "Skill or Certification": "Docker",
             "Discussion Notes": "", "Final Action": ""},
            {"Record ID": "R2", "Employee": "Bob", "Skill or Certification": "K8s",
             "Discussion Notes": "", "Final Action": "Approve"},
        ])
        approvals, rejections = mas.load_csv(csv_file)
        assert len(approvals) == 1
        assert len(rejections) == 0

    def test_notes_truncated_at_max_chars(self, tmp_path):
        long_note = "x" * 5000
        csv_file = tmp_path / "tracker.csv"
        _write_csv(csv_file, [
            {"Record ID": "R1", "Employee": "Carol", "Skill or Certification": "Flow",
             "Discussion Notes": long_note, "Final Action": "Reject"},
        ])
        _, rejections = mas.load_csv(csv_file)
        assert len(rejections[0]["notes"]) == mas.MAX_COMMENT_CHARS

    def test_record_ids_preserved(self, tmp_path):
        csv_file = tmp_path / "tracker.csv"
        _write_csv(csv_file, [
            {"Record ID": "a9H3y000000DIa5EAG", "Employee": "Dave",
             "Skill or Certification": "CI/CD", "Discussion Notes": "",
             "Final Action": "Approve"},
        ])
        approvals, _ = mas.load_csv(csv_file)
        assert approvals[0]["record_id"] == "a9H3y000000DIa5EAG"

    def test_empty_csv_returns_empty_lists(self, tmp_path):
        csv_file = tmp_path / "tracker.csv"
        _write_csv(csv_file, [])
        approvals, rejections = mas.load_csv(csv_file)
        assert approvals == []
        assert rejections == []

    def test_all_approve(self, tmp_path):
        csv_file = tmp_path / "tracker.csv"
        _write_csv(csv_file, [
            {"Record ID": f"R{i}", "Employee": f"Emp{i}", "Skill or Certification": "S",
             "Discussion Notes": "", "Final Action": "Approve"}
            for i in range(5)
        ])
        approvals, rejections = mas.load_csv(csv_file)
        assert len(approvals) == 5
        assert rejections == []


# ---------------------------------------------------------------------------
# wait_for_table
# ---------------------------------------------------------------------------

class TestWaitForTable:
    def test_delegates_to_page_wait_for_selector(self):
        page = _make_mock_page()
        mas.wait_for_table(page)
        page.wait_for_selector.assert_called_once()
        selector_arg = page.wait_for_selector.call_args[0][0]
        assert "tr[data-row-key-value]" in selector_arg


# ---------------------------------------------------------------------------
# get_all_rows
# ---------------------------------------------------------------------------

class TestGetAllRows:
    def test_parses_employee_and_skill(self):
        page = _make_mock_page()
        tr, _ = _make_tr_mock("Alice", "Docker")
        page.query_selector_all.return_value = [tr]
        rows = mas.get_all_rows(page)
        assert len(rows) == 1
        assert rows[0]["employee"] == "Alice"
        assert rows[0]["skill"] == "Docker"

    def test_skips_rows_with_too_few_cells(self):
        page = _make_mock_page()
        tr = MagicMock()
        tr.get_attribute.return_value = "REC1"
        # Only 2 cells — not enough
        short_cells = [MagicMock(), MagicMock()]
        for c in short_cells:
            c.inner_text.return_value = "x"
        tr.query_selector_all.return_value = short_cells
        page.query_selector_all.return_value = [tr]
        rows = mas.get_all_rows(page)
        assert rows == []

    def test_handles_exception_in_row_gracefully(self):
        page = _make_mock_page()
        bad_tr = MagicMock()
        bad_tr.query_selector_all.side_effect = RuntimeError("DOM error")
        good_tr, _ = _make_tr_mock("Bob", "K8s")
        page.query_selector_all.return_value = [bad_tr, good_tr]
        rows = mas.get_all_rows(page)
        assert len(rows) == 1
        assert rows[0]["employee"] == "Bob"

    def test_returns_empty_when_no_rows(self):
        page = _make_mock_page()
        page.query_selector_all.return_value = []
        assert mas.get_all_rows(page) == []

    def test_row_key_stored(self):
        page = _make_mock_page()
        tr, _ = _make_tr_mock("Alice", "Docker", row_key="a9H3y000000DIa5EAG")
        page.query_selector_all.return_value = [tr]
        rows = mas.get_all_rows(page)
        assert rows[0]["row_key"] == "a9H3y000000DIa5EAG"


# ---------------------------------------------------------------------------
# scroll_to_load_all
# ---------------------------------------------------------------------------

class TestScrollToLoadAll:
    def test_stops_when_row_count_stable(self):
        page = _make_mock_page()
        # Same count each call → stops after first iteration
        page.query_selector_all.return_value = [MagicMock()]
        with patch("mass_approve_skills.time.sleep"):
            mas.scroll_to_load_all(page)
        # evaluate called once then stopped
        assert page.evaluate.call_count == 1

    def test_keeps_scrolling_while_count_grows(self):
        page = _make_mock_page()
        # Returns 1, 2, 2 on successive calls → iterates twice
        page.query_selector_all.side_effect = [
            [MagicMock()],           # iteration 1 prev
            [MagicMock(), MagicMock()],  # iteration 1 new
            [MagicMock(), MagicMock()],  # iteration 2 prev
            [MagicMock(), MagicMock()],  # iteration 2 new → stable → stop
        ]
        with patch("mass_approve_skills.time.sleep"):
            mas.scroll_to_load_all(page)
        assert page.evaluate.call_count == 2


# ---------------------------------------------------------------------------
# find_row_checkbox
# ---------------------------------------------------------------------------

class TestFindRowCheckbox:
    def test_returns_checkbox_when_found(self):
        page = _make_mock_page()
        tr, checkbox = _make_tr_mock("Alice", "Docker")
        page.query_selector_all.return_value = [tr]
        result = mas.find_row_checkbox(page, "Alice", "Docker")
        assert result is checkbox

    def test_returns_none_when_not_found(self):
        page = _make_mock_page()
        tr, _ = _make_tr_mock("Alice", "Docker")
        page.query_selector_all.return_value = [tr]
        result = mas.find_row_checkbox(page, "Bob", "K8s")
        assert result is None

    def test_exact_name_required(self):
        page = _make_mock_page()
        tr, _ = _make_tr_mock("Alice Smith", "Docker")
        page.query_selector_all.return_value = [tr]
        assert mas.find_row_checkbox(page, "Alice", "Docker") is None
        assert mas.find_row_checkbox(page, "Alice Smith", "Docker") is not None


# ---------------------------------------------------------------------------
# click_button_in_header
# ---------------------------------------------------------------------------

class TestClickButtonInHeader:
    def test_clicks_first_matching_button(self):
        page = _make_mock_page()
        mock_btn = MagicMock()
        page.locator.return_value.first = mock_btn
        mas.click_button_in_header(page, "Approve")
        mock_btn.wait_for.assert_called_once_with(state="visible", timeout=15_000)
        mock_btn.click.assert_called_once()

    def test_uses_correct_label_in_selector(self):
        page = _make_mock_page()
        mock_btn = MagicMock()
        page.locator.return_value.first = mock_btn
        mas.click_button_in_header(page, "Reject")
        selector = page.locator.call_args[0][0]
        assert "Reject" in selector


# ---------------------------------------------------------------------------
# fill_dialog_comment_and_confirm
# ---------------------------------------------------------------------------

class TestFillDialogCommentAndConfirm:
    def _setup_page(self):
        page = _make_mock_page()
        textarea = MagicMock()
        modal = MagicMock()
        confirm_btn = MagicMock()

        # page.locator(...).first → textarea (first call), modal (second call)
        loc1 = MagicMock()
        loc1.first = textarea
        loc2 = MagicMock()
        loc2.first = modal
        page.locator.side_effect = [loc1, loc2]

        modal.locator.return_value.first = confirm_btn

        return page, textarea, modal, confirm_btn

    def test_fills_comment_and_clicks_confirm(self):
        page, textarea, modal, confirm_btn = self._setup_page()
        mas.fill_dialog_comment_and_confirm(page, "my comment", "Approve")
        textarea.fill.assert_called_once_with("my comment")
        confirm_btn.click.assert_called_once()

    def test_waits_for_dialog_to_close(self):
        page, textarea, modal, confirm_btn = self._setup_page()
        mas.fill_dialog_comment_and_confirm(page, "comment", "Reject")
        # Should call wait_for_selector twice: once open, once hidden
        assert page.wait_for_selector.call_count == 2
        calls = page.wait_for_selector.call_args_list
        assert calls[1][1]["state"] == "hidden"


# ---------------------------------------------------------------------------
# execute_approval_pass
# ---------------------------------------------------------------------------

class TestExecuteApprovalPass:
    def test_selects_found_rows_and_approves(self):
        page = _make_mock_page()
        tr, cb = _make_tr_mock("Alice", "Docker", checked=False)
        page.query_selector_all.return_value = [tr]

        with patch("mass_approve_skills.click_button_in_header") as mock_click, \
             patch("mass_approve_skills.fill_dialog_comment_and_confirm") as mock_fill, \
             patch("mass_approve_skills.time.sleep"):
            result = mas.execute_approval_pass(
                page, [{"employee": "Alice", "skill": "Docker", "record_id": "R1"}]
            )

        cb.click.assert_called_once()
        mock_click.assert_called_once_with(page, "Approve")
        mock_fill.assert_called_once_with(page, mas.APPROVE_COMMENT, "Approve")
        assert result["succeeded"] == 1
        assert result["failed"] == []

    def test_records_rows_not_found_on_page(self):
        page = _make_mock_page()
        page.query_selector_all.return_value = []  # no rows on page

        with patch("mass_approve_skills.click_button_in_header"), \
             patch("mass_approve_skills.fill_dialog_comment_and_confirm"), \
             patch("mass_approve_skills.time.sleep"):
            result = mas.execute_approval_pass(
                page, [{"employee": "Ghost", "skill": "Flow", "record_id": "R99"}]
            )

        # selected_count stays 0 (never found), so succeeded=0; failed has the missing row
        assert result["succeeded"] == 0
        assert len(result["failed"]) == 1
        assert result["failed"][0] == {"employee": "Ghost", "skill": "Flow"}

    def test_no_approvals_skips_button_click(self):
        page = _make_mock_page()

        with patch("mass_approve_skills.click_button_in_header") as mock_click, \
             patch("mass_approve_skills.fill_dialog_comment_and_confirm") as mock_fill:
            result = mas.execute_approval_pass(page, [])

        mock_click.assert_not_called()
        mock_fill.assert_not_called()
        assert result == {"succeeded": 0, "failed": []}

    def test_already_checked_row_not_clicked_again(self):
        page = _make_mock_page()
        tr, cb = _make_tr_mock("Alice", "Docker", checked=True)
        page.query_selector_all.return_value = [tr]

        with patch("mass_approve_skills.click_button_in_header"), \
             patch("mass_approve_skills.fill_dialog_comment_and_confirm"), \
             patch("mass_approve_skills.time.sleep"):
            mas.execute_approval_pass(
                page, [{"employee": "Alice", "skill": "Docker", "record_id": "R1"}]
            )

        cb.click.assert_not_called()


# ---------------------------------------------------------------------------
# execute_rejection_pass
# ---------------------------------------------------------------------------

class TestExecuteRejectionPass:
    def _rejection_item(self, employee="Alice", skill="Docker",
                        notes="Needs cert", record_id="R1"):
        return {"employee": employee, "skill": skill, "notes": notes, "record_id": record_id}

    def test_success_path(self):
        page = _make_mock_page()
        tr, cb = _make_tr_mock("Alice", "Docker", checked=False)
        page.query_selector_all.side_effect = lambda selector: (
            [tr] if "data-row-key-value]" in selector and "checked" not in selector
            else []
        )

        with patch("mass_approve_skills.scroll_to_load_all"), \
             patch("mass_approve_skills.click_button_in_header"), \
             patch("mass_approve_skills.fill_dialog_comment_and_confirm"), \
             patch("mass_approve_skills.time.sleep"):
            results = mas.execute_rejection_pass(page, [self._rejection_item()])

        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert results[0]["error"] == ""

    def test_skips_row_not_found(self):
        page = _make_mock_page()
        page.query_selector_all.return_value = []

        with patch("mass_approve_skills.scroll_to_load_all"), \
             patch("mass_approve_skills.time.sleep"):
            results = mas.execute_rejection_pass(page, [self._rejection_item()])

        assert results[0]["status"] == "skipped"
        assert "not found" in results[0]["error"]

    def test_records_failure_on_click_exception(self):
        page = _make_mock_page()
        tr, cb = _make_tr_mock("Alice", "Docker")
        page.query_selector_all.side_effect = lambda selector: (
            [tr] if "data-row-key-value]" in selector and "checked" not in selector
            else []
        )

        with patch("mass_approve_skills.scroll_to_load_all"), \
             patch("mass_approve_skills.click_button_in_header",
                   side_effect=RuntimeError("timeout")), \
             patch("mass_approve_skills.time.sleep"):
            results = mas.execute_rejection_pass(page, [self._rejection_item()])

        assert results[0]["status"] == "failed"
        assert "timeout" in results[0]["error"]

    def test_multiple_rejections_processed_in_order(self):
        page = _make_mock_page()
        tr1, _ = _make_tr_mock("Alice", "Docker")
        tr2, _ = _make_tr_mock("Bob", "K8s")
        page.query_selector_all.side_effect = lambda selector: (
            [tr1, tr2] if "data-row-key-value]" in selector and "checked" not in selector
            else []
        )

        with patch("mass_approve_skills.scroll_to_load_all"), \
             patch("mass_approve_skills.click_button_in_header"), \
             patch("mass_approve_skills.fill_dialog_comment_and_confirm"), \
             patch("mass_approve_skills.time.sleep"):
            results = mas.execute_rejection_pass(page, [
                self._rejection_item("Alice", "Docker"),
                self._rejection_item("Bob", "K8s"),
            ])

        assert len(results) == 2
        assert all(r["status"] == "success" for r in results)

    def test_deselects_other_checked_rows_before_selecting(self):
        page = _make_mock_page()
        tr, cb = _make_tr_mock("Alice", "Docker")
        other_cb = MagicMock()

        def qsa(selector):
            if "checked" in selector:
                return [other_cb]
            return [tr]

        page.query_selector_all.side_effect = qsa

        with patch("mass_approve_skills.scroll_to_load_all"), \
             patch("mass_approve_skills.click_button_in_header"), \
             patch("mass_approve_skills.fill_dialog_comment_and_confirm"), \
             patch("mass_approve_skills.time.sleep"):
            mas.execute_rejection_pass(page, [self._rejection_item()])

        other_cb.click.assert_called_once()


# ---------------------------------------------------------------------------
# run() — smoke tests with full mocking
# ---------------------------------------------------------------------------

class TestRun:
    def _build_playwright_mock(self):
        """Build nested Playwright mocks: sync_playwright → pw → browser → context → page."""
        page = _make_mock_page()
        context = MagicMock()
        context.new_page.return_value = page
        browser = MagicMock()
        browser.new_context.return_value = context
        pw = MagicMock()
        pw.chromium.launch.return_value = browser

        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=pw)
        cm.__exit__ = MagicMock(return_value=False)
        return cm, page

    def test_run_happy_path_no_records(self, tmp_path):
        csv_file = tmp_path / "tracker.csv"
        _write_csv(csv_file, [])
        results_file = tmp_path / "results.json"

        cm, page = self._build_playwright_mock()

        with patch("mass_approve_skills.sync_playwright", return_value=cm), \
             patch("mass_approve_skills.load_csv", return_value=([], [])), \
             patch("mass_approve_skills.wait_for_table"), \
             patch("mass_approve_skills.scroll_to_load_all"), \
             patch("mass_approve_skills.get_all_rows", return_value=[]), \
             patch("mass_approve_skills.execute_approval_pass",
                   return_value={"succeeded": 0, "failed": []}), \
             patch("mass_approve_skills.execute_rejection_pass", return_value=[]), \
             patch("mass_approve_skills.time.sleep"), \
             patch("mass_approve_skills.RESULTS_PATH", results_file), \
             patch("builtins.input", return_value=""):
            mas.run()

        assert results_file.exists()
        data = json.loads(results_file.read_text())
        assert data["approvals"]["attempted"] == 0
        assert data["rejections"] == []

    def test_run_with_approvals_and_rejections(self, tmp_path):
        results_file = tmp_path / "results.json"
        approvals = [{"employee": "Alice", "skill": "Docker", "record_id": "R1"}]
        rejections = [{"employee": "Bob", "skill": "K8s", "record_id": "R2", "notes": "No cert"}]

        cm, page = self._build_playwright_mock()

        with patch("mass_approve_skills.sync_playwright", return_value=cm), \
             patch("mass_approve_skills.load_csv", return_value=(approvals, rejections)), \
             patch("mass_approve_skills.wait_for_table"), \
             patch("mass_approve_skills.scroll_to_load_all"), \
             patch("mass_approve_skills.get_all_rows", return_value=[]), \
             patch("mass_approve_skills.execute_approval_pass",
                   return_value={"succeeded": 1, "failed": []}), \
             patch("mass_approve_skills.execute_rejection_pass",
                   return_value=[{"employee": "Bob", "skill": "K8s",
                                  "status": "success", "error": ""}]), \
             patch("mass_approve_skills.time.sleep"), \
             patch("mass_approve_skills.RESULTS_PATH", results_file), \
             patch("builtins.input", return_value=""):
            mas.run()

        data = json.loads(results_file.read_text())
        assert data["approvals"]["succeeded"] == 1
        assert data["rejections"][0]["status"] == "success"

    def test_run_pwtimeout_falls_back_to_input(self, tmp_path):
        results_file = tmp_path / "results.json"
        cm, page = self._build_playwright_mock()

        from playwright.sync_api import TimeoutError as PWTimeout

        with patch("mass_approve_skills.sync_playwright", return_value=cm), \
             patch("mass_approve_skills.load_csv", return_value=([], [])), \
             patch("mass_approve_skills.wait_for_table", side_effect=PWTimeout("timeout")), \
             patch("mass_approve_skills.scroll_to_load_all"), \
             patch("mass_approve_skills.get_all_rows", return_value=[]), \
             patch("mass_approve_skills.execute_approval_pass",
                   return_value={"succeeded": 0, "failed": []}), \
             patch("mass_approve_skills.execute_rejection_pass", return_value=[]), \
             patch("mass_approve_skills.time.sleep"), \
             patch("mass_approve_skills.RESULTS_PATH", results_file), \
             patch("builtins.input", return_value=""):
            mas.run()

        # Should complete without raising despite PWTimeout
        assert results_file.exists()


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_approve_comment_contains_reviewer_name(self):
        assert "Alexis Williams" in mas.APPROVE_COMMENT

    def test_max_comment_chars_is_4000(self):
        assert mas.MAX_COMMENT_CHARS == 4000

    def test_mass_approve_url_is_org62(self):
        assert "org62.lightning.force.com" in mas.MASS_APPROVE_URL

    def test_csv_path_points_to_manager_tracker(self):
        assert "Manager Tracker" in str(mas.CSV_PATH)
