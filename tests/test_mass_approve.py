"""Tests for mass_approve_skills.py — targeting ≥90% coverage."""
import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import mass_approve_skills as mas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path, rows, headers=None):
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


def _mock_page(evaluate_return=None):
    page = MagicMock()
    page.evaluate.return_value = evaluate_return or {"rows": []}
    return page


def _row(employee, skill, record_id="R1"):
    return {
        "id": record_id,
        mas._COL_EMPLOYEE: employee,
        mas._COL_SKILL: skill,
    }


# ---------------------------------------------------------------------------
# load_csv
# ---------------------------------------------------------------------------

class TestLoadCsv:
    def test_separates_approve_and_reject(self, tmp_path):
        csv_file = tmp_path / "t.csv"
        _write_csv(csv_file, [
            {"Record ID": "R1", "Employee": "Alice", "Skill or Certification": "Docker",
             "Discussion Notes": "ok", "Final Action": "Approve"},
            {"Record ID": "R2", "Employee": "Bob", "Skill or Certification": "K8s",
             "Discussion Notes": "needs work", "Final Action": "Reject"},
        ])
        approvals, rejections = mas.load_csv(csv_file)
        assert len(approvals) == 1 and approvals[0]["employee"] == "Alice"
        assert len(rejections) == 1 and rejections[0]["notes"] == "needs work"

    def test_blank_action_excluded(self, tmp_path):
        csv_file = tmp_path / "t.csv"
        _write_csv(csv_file, [
            {"Record ID": "R1", "Employee": "Alice", "Skill or Certification": "Docker",
             "Discussion Notes": "", "Final Action": ""},
            {"Record ID": "R2", "Employee": "Bob", "Skill or Certification": "K8s",
             "Discussion Notes": "", "Final Action": "Approve"},
        ])
        approvals, rejections = mas.load_csv(csv_file)
        assert len(approvals) == 1 and len(rejections) == 0

    def test_notes_truncated_at_max_chars(self, tmp_path):
        csv_file = tmp_path / "t.csv"
        _write_csv(csv_file, [
            {"Record ID": "R1", "Employee": "Carol", "Skill or Certification": "Flow",
             "Discussion Notes": "x" * 5000, "Final Action": "Reject"},
        ])
        _, rejections = mas.load_csv(csv_file)
        assert len(rejections[0]["notes"]) == mas.MAX_COMMENT_CHARS

    def test_record_ids_preserved(self, tmp_path):
        csv_file = tmp_path / "t.csv"
        _write_csv(csv_file, [
            {"Record ID": "a9H3y000000DIa5EAG", "Employee": "Dave",
             "Skill or Certification": "CI/CD", "Discussion Notes": "",
             "Final Action": "Approve"},
        ])
        approvals, _ = mas.load_csv(csv_file)
        assert approvals[0]["record_id"] == "a9H3y000000DIa5EAG"

    def test_empty_csv_returns_empty_lists(self, tmp_path):
        csv_file = tmp_path / "t.csv"
        _write_csv(csv_file, [])
        approvals, rejections = mas.load_csv(csv_file)
        assert approvals == [] and rejections == []

    def test_all_reject(self, tmp_path):
        csv_file = tmp_path / "t.csv"
        _write_csv(csv_file, [
            {"Record ID": f"R{i}", "Employee": f"E{i}", "Skill or Certification": "S",
             "Discussion Notes": f"note{i}", "Final Action": "Reject"}
            for i in range(3)
        ])
        approvals, rejections = mas.load_csv(csv_file)
        assert len(approvals) == 0 and len(rejections) == 3


# ---------------------------------------------------------------------------
# wait_for_grid
# ---------------------------------------------------------------------------

class TestWaitForGrid:
    def test_calls_wait_for_function_then_wait_for_timeout(self):
        page = _mock_page()
        mas.wait_for_grid(page)
        page.wait_for_function.assert_called_once()
        page.wait_for_timeout.assert_called_once_with(2_000)

    def test_passes_grid_js_to_wait_for_function(self):
        page = _mock_page()
        mas.wait_for_grid(page)
        js_arg = page.wait_for_function.call_args[0][0]
        assert "c-bryntum-widget-host" in js_arg


# ---------------------------------------------------------------------------
# get_all_rows
# ---------------------------------------------------------------------------

class TestGetAllRows:
    def test_returns_rows_from_evaluate(self):
        page = _mock_page(evaluate_return={"rows": [_row("Alice", "Docker")]})
        rows = mas.get_all_rows(page)
        assert len(rows) == 1
        assert rows[0][mas._COL_EMPLOYEE] == "Alice"

    def test_returns_empty_list_when_no_rows(self):
        page = _mock_page(evaluate_return={"rows": []})
        assert mas.get_all_rows(page) == []

    def test_raises_on_evaluate_error(self):
        page = _mock_page(evaluate_return={"error": "no-host"})
        with pytest.raises(RuntimeError, match="no-host"):
            mas.get_all_rows(page)

    def test_passes_correct_js(self):
        page = _mock_page(evaluate_return={"rows": []})
        mas.get_all_rows(page)
        js_arg = page.evaluate.call_args[0][0]
        assert "b-grid-row" in js_arg


# ---------------------------------------------------------------------------
# select_rows_by_ids
# ---------------------------------------------------------------------------

class TestSelectRowsById:
    def test_returns_selected_count_and_missing(self):
        page = _mock_page(evaluate_return={"selected": 3, "missing": ["X1"]})
        result = mas.select_rows_by_ids(page, ["R1", "R2", "R3", "X1"])
        assert result["selected"] == 3
        assert result["missing"] == ["X1"]

    def test_raises_on_error(self):
        page = _mock_page(evaluate_return={"error": "no-host"})
        with pytest.raises(RuntimeError):
            mas.select_rows_by_ids(page, ["R1"])

    def test_passes_record_ids_to_evaluate(self):
        page = _mock_page(evaluate_return={"selected": 1, "missing": []})
        mas.select_rows_by_ids(page, ["ABC"])
        call_args = page.evaluate.call_args
        assert call_args[0][1] == ["ABC"]


# ---------------------------------------------------------------------------
# clear_selection
# ---------------------------------------------------------------------------

class TestClearSelection:
    def test_calls_evaluate_with_clear_js(self):
        page = _mock_page()
        mas.clear_selection(page)
        page.evaluate.assert_called_once()
        js_arg = page.evaluate.call_args[0][0]
        assert "b-selected" in js_arg


# ---------------------------------------------------------------------------
# match_row_id
# ---------------------------------------------------------------------------

class TestMatchRowId:
    def test_found(self):
        rows = [_row("Alice", "Docker", "R1"), _row("Bob", "K8s", "R2")]
        assert mas.match_row_id(rows, "Alice", "Docker") == "R1"

    def test_not_found_returns_none(self):
        rows = [_row("Alice", "Docker", "R1")]
        assert mas.match_row_id(rows, "Bob", "K8s") is None

    def test_exact_match_required(self):
        rows = [_row("Alice Smith", "Docker", "R1")]
        assert mas.match_row_id(rows, "Alice", "Docker") is None

    def test_empty_rows_returns_none(self):
        assert mas.match_row_id([], "Alice", "Docker") is None


# ---------------------------------------------------------------------------
# click_page_button
# ---------------------------------------------------------------------------

class TestClickPageButton:
    def test_clicks_first_matching_button(self):
        page = _mock_page()
        mock_btn = MagicMock()
        page.get_by_role.return_value.first = mock_btn
        mas.click_page_button(page, "Approve")
        mock_btn.wait_for.assert_called_once_with(state="visible", timeout=15_000)
        mock_btn.click.assert_called_once()

    def test_uses_correct_role_and_name(self):
        page = _mock_page()
        mock_btn = MagicMock()
        page.get_by_role.return_value.first = mock_btn
        mas.click_page_button(page, "Reject")
        page.get_by_role.assert_called_once_with("button", name="Reject")


# ---------------------------------------------------------------------------
# fill_and_confirm_modal
# ---------------------------------------------------------------------------

class TestFillAndConfirmModal:
    def _setup(self):
        """
        page.locator("textarea.slds-textarea") → textarea locator
        page.locator("button[title=...]")      → confirm_btn locator
        No [role='dialog'] lookup — we skip that to avoid the hidden Aura error dialog.
        """
        page = _mock_page()
        textarea = MagicMock()
        confirm_btn = MagicMock()

        def locator_side_effect(selector, **kwargs):
            lc = MagicMock()
            if "slds-textarea" in selector:
                # textarea locator — .fill() and .wait_for() called on it directly
                lc.fill = textarea.fill
                lc.wait_for = textarea.wait_for
                return lc
            elif "button[title=" in selector:
                lc.wait_for = confirm_btn.wait_for
                lc.click = confirm_btn.click
                return lc
            return lc

        page.locator.side_effect = locator_side_effect
        return page, textarea, confirm_btn

    def test_fills_textarea_and_clicks_confirm(self):
        page, textarea, confirm_btn = self._setup()
        mas.fill_and_confirm_modal(page, "my comment", "Approve")
        textarea.fill.assert_called_once_with("my comment")
        confirm_btn.click.assert_called_once()

    def test_waits_for_textarea_to_open_and_close(self):
        page, textarea, confirm_btn = self._setup()
        mas.fill_and_confirm_modal(page, "comment", "Reject")
        # wait_for called at least twice: visible (open) + hidden (closed)
        assert textarea.wait_for.call_count >= 2
        states = [c[1].get("state") for c in textarea.wait_for.call_args_list]
        assert "visible" in states
        assert "hidden" in states

    def test_textarea_selected_by_slds_class(self):
        page, textarea, confirm_btn = self._setup()
        mas.fill_and_confirm_modal(page, "x", "Approve")
        selectors = [c[0][0] for c in page.locator.call_args_list]
        assert any("slds-textarea" in s for s in selectors)

    def test_confirm_button_selected_by_title(self):
        page, textarea, confirm_btn = self._setup()
        mas.fill_and_confirm_modal(page, "x", "Reject")
        title_selectors = [
            c[0][0] for c in page.locator.call_args_list
            if "button[title=" in c[0][0]
        ]
        assert len(title_selectors) == 1
        assert "Reject Skill or Certification Rating" in title_selectors[0]

    def test_no_role_dialog_lookup(self):
        """Regression: must not wait on [role='dialog'] — matches hidden Aura error box."""
        page, textarea, confirm_btn = self._setup()
        mas.fill_and_confirm_modal(page, "x", "Approve")
        selectors = [c[0][0] for c in page.locator.call_args_list]
        assert not any("role='dialog'" in s or 'role="dialog"' in s for s in selectors)


# ---------------------------------------------------------------------------
# execute_approval_pass
# ---------------------------------------------------------------------------

class TestExecuteApprovalPass:
    def test_selects_and_approves_when_rows_found(self):
        page = _mock_page(evaluate_return={"selected": 2, "missing": []})
        approvals = [
            {"employee": "Alice", "skill": "Docker", "record_id": "R1"},
            {"employee": "Bob", "skill": "K8s", "record_id": "R2"},
        ]
        with patch("mass_approve_skills.click_page_button") as mock_click, \
             patch("mass_approve_skills.fill_and_confirm_modal") as mock_fill:
            result = mas.execute_approval_pass(page, approvals)

        mock_click.assert_called_once_with(page, "Approve")
        mock_fill.assert_called_once_with(page, mas.APPROVE_COMMENT, "Approve")
        assert result["succeeded"] == 2
        assert result["missing"] == []

    def test_records_missing_rows(self):
        page = _mock_page(evaluate_return={"selected": 1, "missing": ["R2"]})
        approvals = [
            {"employee": "Alice", "skill": "Docker", "record_id": "R1"},
            {"employee": "Ghost", "skill": "Flow", "record_id": "R2"},
        ]
        with patch("mass_approve_skills.click_page_button"), \
             patch("mass_approve_skills.fill_and_confirm_modal"):
            result = mas.execute_approval_pass(page, approvals)

        assert result["succeeded"] == 1
        assert "R2" in result["missing"]

    def test_no_approvals_skips_button_click(self):
        page = _mock_page()
        with patch("mass_approve_skills.click_page_button") as mock_click, \
             patch("mass_approve_skills.fill_and_confirm_modal") as mock_fill:
            result = mas.execute_approval_pass(page, [])

        mock_click.assert_not_called()
        mock_fill.assert_not_called()
        assert result == {"attempted": 0, "succeeded": 0, "missing": []}

    def test_no_button_click_when_zero_selected(self):
        page = _mock_page(evaluate_return={"selected": 0, "missing": ["R1"]})
        with patch("mass_approve_skills.click_page_button") as mock_click, \
             patch("mass_approve_skills.fill_and_confirm_modal") as mock_fill:
            mas.execute_approval_pass(page, [{"employee": "X", "skill": "Y", "record_id": "R1"}])

        mock_click.assert_not_called()


# ---------------------------------------------------------------------------
# execute_rejection_pass
# ---------------------------------------------------------------------------

class TestExecuteRejectionPass:
    def _item(self, employee="Alice", skill="Docker", notes="No cert", record_id="R1"):
        return {"employee": employee, "skill": skill, "notes": notes, "record_id": record_id}

    def test_success_path(self):
        page = _mock_page()
        page.evaluate.return_value = {"selected": 1, "missing": []}

        with patch("mass_approve_skills.clear_selection"), \
             patch("mass_approve_skills.click_page_button"), \
             patch("mass_approve_skills.fill_and_confirm_modal"):
            results = mas.execute_rejection_pass(page, [self._item()], [])

        assert results[0]["status"] == "success"

    def test_skips_when_no_record_id_and_not_in_rows(self):
        page = _mock_page()
        with patch("mass_approve_skills.clear_selection"):
            results = mas.execute_rejection_pass(
                page, [self._item(record_id="")], []
            )
        assert results[0]["status"] == "skipped"
        assert "not found" in results[0]["error"]

    def test_skips_when_row_not_on_page(self):
        page = _mock_page(evaluate_return={"selected": 0, "missing": ["R1"]})

        with patch("mass_approve_skills.clear_selection"):
            results = mas.execute_rejection_pass(page, [self._item()], [])

        assert results[0]["status"] == "skipped"
        assert "not found on page" in results[0]["error"]

    def test_records_failure_on_exception(self):
        page = _mock_page(evaluate_return={"selected": 1, "missing": []})

        with patch("mass_approve_skills.clear_selection"), \
             patch("mass_approve_skills.click_page_button",
                   side_effect=RuntimeError("timeout")), \
             patch("mass_approve_skills.take_debug_screenshot"):
            results = mas.execute_rejection_pass(page, [self._item()], [])

        assert results[0]["status"] == "failed"
        assert "timeout" in results[0]["error"]

    def test_falls_back_to_name_match_when_no_csv_id(self):
        page = _mock_page(evaluate_return={"selected": 1, "missing": []})
        live_rows = [_row("Alice", "Docker", "R_LIVE")]

        with patch("mass_approve_skills.clear_selection"), \
             patch("mass_approve_skills.click_page_button"), \
             patch("mass_approve_skills.fill_and_confirm_modal"):
            results = mas.execute_rejection_pass(
                page, [self._item(record_id="")], live_rows
            )

        # Verify select_rows_by_ids was called with the live-matched ID
        eval_call = page.evaluate.call_args_list[-1]
        assert "R_LIVE" in str(eval_call)

    def test_multiple_rejections_all_succeed(self):
        page = _mock_page(evaluate_return={"selected": 1, "missing": []})

        with patch("mass_approve_skills.clear_selection"), \
             patch("mass_approve_skills.click_page_button"), \
             patch("mass_approve_skills.fill_and_confirm_modal"):
            results = mas.execute_rejection_pass(page, [
                self._item("Alice", "Docker"),
                self._item("Bob", "K8s", record_id="R2"),
            ], [])

        assert all(r["status"] == "success" for r in results)


# ---------------------------------------------------------------------------
# take_debug_screenshot
# ---------------------------------------------------------------------------

class TestTakeDebugScreenshot:
    def test_calls_page_screenshot(self):
        page = _mock_page()
        mas.take_debug_screenshot(page, "test_tag")
        page.screenshot.assert_called_once()
        call_kwargs = page.screenshot.call_args[1]
        assert "test_tag" in call_kwargs["path"]
        assert call_kwargs["full_page"] is True


# ---------------------------------------------------------------------------
# run() — smoke tests with full mocking
# ---------------------------------------------------------------------------

class TestRun:
    def _pw_mock(self):
        page = _mock_page(evaluate_return={"rows": []})
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

    def test_happy_path_no_records(self, tmp_path):
        results_file = tmp_path / "results.json"
        cm, page = self._pw_mock()
        # At least one live row so the no-rows early-exit guard is skipped
        live_rows = [{"id": "R0", mas._COL_EMPLOYEE: "X", mas._COL_SKILL: "Y"}]

        with patch("mass_approve_skills.sync_playwright", return_value=cm), \
             patch("mass_approve_skills.load_csv", return_value=([], [])), \
             patch("mass_approve_skills.wait_for_grid"), \
             patch("mass_approve_skills.get_all_rows", return_value=live_rows), \
             patch("mass_approve_skills.execute_approval_pass",
                   return_value={"attempted": 0, "succeeded": 0, "missing": []}), \
             patch("mass_approve_skills.execute_rejection_pass", return_value=[]), \
             patch("mass_approve_skills.RESULTS_PATH", results_file), \
             patch("builtins.input", return_value=""):
            mas.run()

        assert results_file.exists()
        data = json.loads(results_file.read_text())
        assert data["approvals"]["attempted"] == 0

    def test_with_records_calls_both_passes(self, tmp_path):
        results_file = tmp_path / "results.json"
        cm, page = self._pw_mock()
        approvals = [{"employee": "A", "skill": "S", "record_id": "R1"}]
        rejections = [{"employee": "B", "skill": "T", "record_id": "R2", "notes": "x"}]
        live_rows = [{"id": "R1", mas._COL_EMPLOYEE: "A", mas._COL_SKILL: "S"}]

        with patch("mass_approve_skills.sync_playwright", return_value=cm), \
             patch("mass_approve_skills.load_csv", return_value=(approvals, rejections)), \
             patch("mass_approve_skills.wait_for_grid"), \
             patch("mass_approve_skills.get_all_rows", return_value=live_rows), \
             patch("mass_approve_skills.execute_approval_pass",
                   return_value={"attempted": 1, "succeeded": 1, "missing": []}) as mock_ap, \
             patch("mass_approve_skills.execute_rejection_pass",
                   return_value=[{"employee": "B", "skill": "T",
                                  "status": "success", "error": ""}]) as mock_rj, \
             patch("mass_approve_skills.RESULTS_PATH", results_file), \
             patch("builtins.input", return_value=""):
            mas.run()

        mock_ap.assert_called_once()
        mock_rj.assert_called_once()

    def test_pwtimeout_on_grid_recovers(self, tmp_path):
        results_file = tmp_path / "results.json"
        cm, page = self._pw_mock()
        from playwright.sync_api import TimeoutError as PWTimeout

        call_count = {"n": 0}

        def wait_grid_side_effect(p):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise PWTimeout("timeout")

        with patch("mass_approve_skills.sync_playwright", return_value=cm), \
             patch("mass_approve_skills.load_csv", return_value=([], [])), \
             patch("mass_approve_skills.wait_for_grid",
                   side_effect=wait_grid_side_effect), \
             patch("mass_approve_skills.get_all_rows", return_value=[]), \
             patch("mass_approve_skills.execute_approval_pass",
                   return_value={"attempted": 0, "succeeded": 0, "missing": []}), \
             patch("mass_approve_skills.execute_rejection_pass", return_value=[]), \
             patch("mass_approve_skills.take_debug_screenshot"), \
             patch("mass_approve_skills.RESULTS_PATH", results_file), \
             patch("builtins.input", return_value=""):
            mas.run()

        assert call_count["n"] == 2  # retried after timeout

    def test_no_rows_found_exits_early(self, tmp_path):
        results_file = tmp_path / "results.json"
        cm, page = self._pw_mock()

        with patch("mass_approve_skills.sync_playwright", return_value=cm), \
             patch("mass_approve_skills.load_csv", return_value=([], [])), \
             patch("mass_approve_skills.wait_for_grid"), \
             patch("mass_approve_skills.get_all_rows", return_value=[]), \
             patch("mass_approve_skills.execute_approval_pass") as mock_ap, \
             patch("mass_approve_skills.take_debug_screenshot"), \
             patch("mass_approve_skills.RESULTS_PATH", results_file), \
             patch("builtins.input", return_value=""):
            mas.run()

        # Should exit before calling approval pass when no rows found
        mock_ap.assert_not_called()


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_approve_comment_contains_reviewer(self):
        assert "Alexis Williams" in mas.APPROVE_COMMENT

    def test_max_comment_chars_is_4000(self):
        assert mas.MAX_COMMENT_CHARS == 4000

    def test_url_is_org62(self):
        assert "org62.lightning.force.com" in mas.MASS_APPROVE_URL

    def test_col_employee_is_expected_id(self):
        assert mas._COL_EMPLOYEE == "col-pse__resource__r_name"

    def test_col_skill_is_expected_id(self):
        assert mas._COL_SKILL == "col-pse__skill_certification__r_name"
