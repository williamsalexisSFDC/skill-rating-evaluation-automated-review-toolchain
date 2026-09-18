"""Tests for validate_skill_ratings.py — targeting ≥90% coverage."""
import csv
import sys
import textwrap
from pathlib import Path

import pytest

import validate_skill_ratings as vsr


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_lowercase(self):
        assert vsr.normalize("Business Acumen") == "business acumen"

    def test_strips_leading_stars(self):
        assert vsr.normalize("***Environment/Sandbox Management") == "environment/sandbox management"

    def test_strips_whitespace(self):
        assert vsr.normalize("  Agentforce Operations  ") == "agentforce operations"

    def test_single_star(self):
        assert vsr.normalize("*Data Cloud") == "data cloud"

    def test_no_op_already_lower(self):
        assert vsr.normalize("already normalized") == "already normalized"

    def test_empty_string(self):
        assert vsr.normalize("") == ""


# ---------------------------------------------------------------------------
# rating_int()
# ---------------------------------------------------------------------------

class TestRatingInt:
    def test_entry(self):
        assert vsr.rating_int("1- Entry") == 1

    def test_intermediate(self):
        assert vsr.rating_int("2- Intermediate") == 2

    def test_advanced(self):
        assert vsr.rating_int("3- Advanced") == 3

    def test_specialist(self):
        assert vsr.rating_int("4- Specialist") == 4

    def test_unknown_returns_zero(self):
        assert vsr.rating_int("not a rating") == 0

    def test_empty_returns_zero(self):
        assert vsr.rating_int("") == 0

    def test_strips_whitespace(self):
        assert vsr.rating_int("  3- Advanced  ") == 3


# ---------------------------------------------------------------------------
# _is_af_tier2_skill()
# ---------------------------------------------------------------------------

class TestIsAfTier2Skill:
    def test_business_acumen(self):
        assert vsr._is_af_tier2_skill("Business Acumen") is True

    def test_ai_consulting(self):
        assert vsr._is_af_tier2_skill("AI Consulting") is True

    def test_executive_alignment(self):
        assert vsr._is_af_tier2_skill("Executive Alignment") is True

    def test_agility(self):
        assert vsr._is_af_tier2_skill("Agility") is True

    def test_demonstrate_business_acumen(self):
        assert vsr._is_af_tier2_skill("Demonstrate Business Acumen") is True

    def test_non_tier2(self):
        assert vsr._is_af_tier2_skill("Agentforce Operations") is False

    def test_environment_sandbox_not_tier2(self):
        assert vsr._is_af_tier2_skill("Environment/Sandbox Management") is False


# ---------------------------------------------------------------------------
# _is_af_delivery_skill()
# ---------------------------------------------------------------------------

class TestIsAfDeliverySkill:
    def test_delivery_keyword(self):
        assert vsr._is_af_delivery_skill("Agentforce Delivery") is True

    def test_testing_keyword(self):
        assert vsr._is_af_delivery_skill("Agentforce Testing") is True

    def test_conversation_design(self):
        assert vsr._is_af_delivery_skill("Conversation Design for Agents") is True

    def test_performance_tracking(self):
        assert vsr._is_af_delivery_skill("Performance Tracking") is True

    def test_field_service(self):
        assert vsr._is_af_delivery_skill("Field Service Automation") is True

    def test_ai_ecosystem_in_af_name(self):
        assert vsr._is_af_delivery_skill("Some Skill", "AI Ecosystem and Frameworks") is True

    def test_rag_in_af_name(self):
        assert vsr._is_af_delivery_skill("Some Skill", "Retrieval Augmented Generation") is True

    def test_non_delivery(self):
        assert vsr._is_af_delivery_skill("Agentforce Operations", "Agentforce Operations") is False

    def test_data_cloud_not_delivery(self):
        assert vsr._is_af_delivery_skill("Data 360 (aka: Data Cloud) for Agentforce") is False


# ---------------------------------------------------------------------------
# _has_agentforce_specialist_cert()
# ---------------------------------------------------------------------------

class TestHasAgentforceSpecialistCert:
    def test_has_specialist(self):
        assert vsr._has_agentforce_specialist_cert([("Certified Agentforce Specialist", "2024")]) is True

    def test_has_expert(self):
        assert vsr._has_agentforce_specialist_cert([("Certified Agentforce Expert", "2024")]) is True

    def test_agentforce_without_specialist(self):
        # Agentforce AI Associate doesn't have "specialist" or "expert"
        assert vsr._has_agentforce_specialist_cert([("Certified Agentforce AI Associate", "2024")]) is False

    def test_empty_list(self):
        assert vsr._has_agentforce_specialist_cert([]) is False

    def test_other_certs_only(self):
        assert vsr._has_agentforce_specialist_cert([
            ("Certified Platform Administrator", "2023"),
            ("Foundations of Git - Certified", "2024"),
        ]) is False


# ---------------------------------------------------------------------------
# _find_cert_recommendation()
# ---------------------------------------------------------------------------

class TestFindCertRecommendation:
    def test_data_cloud_keyword(self):
        result = vsr._find_cert_recommendation("Data Cloud Operations")
        assert "data cloud" in result.lower() or "data 360" in result.lower()

    def test_agentforce_keyword(self):
        result = vsr._find_cert_recommendation("Agentforce Operations")
        assert "agentforce" in result.lower()

    def test_containerization_keyword(self):
        result = vsr._find_cert_recommendation("Containerization frameworks and tools")
        assert "ckad" in result.lower() or "cka" in result.lower()

    def test_no_match_returns_empty(self):
        result = vsr._find_cert_recommendation("Completely Unknown Skill XYZ")
        assert result == ""

    def test_environment_keyword(self):
        result = vsr._find_cert_recommendation("Environment/Sandbox Management")
        assert result != ""


# ---------------------------------------------------------------------------
# match()
# ---------------------------------------------------------------------------

class TestMatch:
    def test_exact_match(self):
        index = {"environment/sandbox management": {"val": "yes"}}
        key, val = vsr.match("environment/sandbox management", index)
        assert key == "environment/sandbox management"
        assert val == {"val": "yes"}

    def test_substring_match(self):
        index = {"environment/sandbox management": {"val": "yes"}}
        key, val = vsr.match("environment", index)
        assert key == "environment/sandbox management"
        assert val is not None

    def test_no_match_returns_none_pair(self):
        index = {"agentforce operations": {"val": "yes"}}
        key, val = vsr.match("completely unrelated skill", index)
        assert key is None
        assert val is None

    def test_empty_index(self):
        key, val = vsr.match("anything", {})
        assert key is None
        assert val is None


# ---------------------------------------------------------------------------
# _find_catalog_file()
# ---------------------------------------------------------------------------

class TestFindCatalogFile:
    def test_finds_csv(self, tmp_path):
        f = tmp_path / "All Skills and Certifications-2026-01-01.csv"
        f.write_text("name\n")
        result = vsr._find_catalog_file(tmp_path)
        assert result == f

    def test_finds_most_recent_of_multiple(self, tmp_path):
        f1 = tmp_path / "All Skills and Certifications-2025-01-01.csv"
        f2 = tmp_path / "All Skills and Certifications-2026-06-01.csv"
        f1.write_text("name\n")
        import time; time.sleep(0.01)
        f2.write_text("name\n")
        result = vsr._find_catalog_file(tmp_path)
        assert result == f2

    def test_raises_if_none_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            vsr._find_catalog_file(tmp_path)

    def test_finds_psa_prefix(self, tmp_path):
        f = tmp_path / "PSA Skills and Certifications Report-2026.csv"
        f.write_text("name\n")
        result = vsr._find_catalog_file(tmp_path)
        assert result == f


# ---------------------------------------------------------------------------
# _parse_html_xls()
# ---------------------------------------------------------------------------

class TestParseHtmlXls:
    def test_basic_table(self, tmp_path):
        html = textwrap.dedent("""\
            <table>
            <tr><th>Name</th><th>Type</th></tr>
            <tr><td>Environment/Sandbox Management</td><td>Technical</td></tr>
            <tr><td>Agentforce Operations</td><td>Technical</td></tr>
            </table>
        """)
        f = tmp_path / "test.xls"
        f.write_text(html)
        rows = vsr._parse_html_xls(f)
        assert len(rows) == 2
        assert rows[0]["Name"] == "Environment/Sandbox Management"
        assert rows[0]["Type"] == "Technical"
        assert rows[1]["Name"] == "Agentforce Operations"

    def test_html_entities(self, tmp_path):
        html = "<table><tr><th>Name</th></tr><tr><td>Skills &amp; Certs &lt;2026&gt;</td></tr></table>"
        f = tmp_path / "test.xls"
        f.write_text(html)
        rows = vsr._parse_html_xls(f)
        assert rows[0]["Name"] == "Skills & Certs <2026>"

    def test_nbsp_stripped(self, tmp_path):
        html = "<table><tr><th>Name</th></tr><tr><td>&nbsp;Test Skill&nbsp;</td></tr></table>"
        f = tmp_path / "test.xls"
        f.write_text(html)
        rows = vsr._parse_html_xls(f)
        assert "Test Skill" in rows[0]["Name"]

    def test_empty_table(self, tmp_path):
        f = tmp_path / "empty.xls"
        f.write_text("<table></table>")
        rows = vsr._parse_html_xls(f)
        assert rows == []


# ---------------------------------------------------------------------------
# load_catalog()
# ---------------------------------------------------------------------------

class TestLoadCatalog:
    def test_csv_format(self, tmp_path):
        csv_content = (
            "Skill or Certification: Skill or Certification Name,Skill or Certification: ID,"
            "Description,Type,Category,Parent Category\n"
            "Environment/Sandbox Management,SKL-001,Manage sandbox environments,Technical,DevOps,Delivery\n"
        )
        f = tmp_path / "catalog.csv"
        f.write_text(csv_content)
        catalog = vsr.load_catalog(f)
        assert "environment/sandbox management" in catalog
        entry = catalog["environment/sandbox management"]
        assert entry["catalog_name"] == "Environment/Sandbox Management"
        assert entry["catalog_id"] == "SKL-001"
        assert entry["catalog_type"] == "Technical"

    def test_html_xls_format(self, tmp_path):
        html = textwrap.dedent("""\
            <table>
            <tr>
              <th>Skill or Certification: Skill or Certification Name</th>
              <th>Skill or Certification: ID</th>
              <th>Description</th>
              <th>Type</th>
              <th>Category</th>
              <th>Parent Category</th>
            </tr>
            <tr>
              <td>Agentforce Operations</td>
              <td>SKL-002</td>
              <td>Operate agents</td>
              <td>Technical</td>
              <td>Agentforce</td>
              <td>AI</td>
            </tr>
            </table>
        """)
        f = tmp_path / "catalog.xls"
        f.write_bytes(b"<" + html[1:].encode())  # ensures it starts with '<'
        catalog = vsr.load_catalog(f)
        assert "agentforce operations" in catalog

    def test_skips_empty_names(self, tmp_path):
        csv_content = (
            "Skill or Certification: Skill or Certification Name,Skill or Certification: ID,"
            "Description,Type,Category,Parent Category\n"
            ",SKL-001,Empty name,Technical,DevOps,Delivery\n"
            "Real Skill,SKL-002,Real,Technical,DevOps,Delivery\n"
        )
        f = tmp_path / "catalog.csv"
        f.write_text(csv_content)
        catalog = vsr.load_catalog(f)
        assert "" not in catalog
        assert "real skill" in catalog


# ---------------------------------------------------------------------------
# load_certifications()
# ---------------------------------------------------------------------------

class TestLoadCertifications:
    def test_basic_load(self, tmp_path):
        content = "Employee,Certification,Earned Date\nAlice,Certified Agentforce Specialist,2024-12-01\n"
        f = tmp_path / "certs.csv"
        f.write_text(content)
        result = vsr.load_certifications(f)
        assert "Alice" in result
        assert result["Alice"] == [("Certified Agentforce Specialist", "2024-12-01")]

    def test_multiple_certs_per_employee(self, tmp_path):
        content = (
            "Employee,Certification,Earned Date\n"
            "Alice,Cert A,2024-01-01\n"
            "Alice,Cert B,2024-06-01\n"
        )
        f = tmp_path / "certs.csv"
        f.write_text(content)
        result = vsr.load_certifications(f)
        assert len(result["Alice"]) == 2

    def test_missing_file_returns_empty(self, tmp_path):
        result = vsr.load_certifications(tmp_path / "nonexistent.csv")
        assert result == {}

    def test_multiple_employees(self, tmp_path):
        content = (
            "Employee,Certification,Earned Date\n"
            "Alice,Cert A,2024-01-01\n"
            "Bob,Cert B,2024-06-01\n"
        )
        f = tmp_path / "certs.csv"
        f.write_text(content)
        result = vsr.load_certifications(f)
        assert "Alice" in result and "Bob" in result


# ---------------------------------------------------------------------------
# load_agentforce_rrs()
# ---------------------------------------------------------------------------

class TestLoadAgentforceRrs:
    def test_basic_load(self, tmp_path):
        content = "Employee,Qualifying\nAlice,Yes\nAlice,Yes\nBob,No\n"
        f = tmp_path / "rrs.csv"
        f.write_text(content)
        result = vsr.load_agentforce_rrs(f)
        assert result["Alice"] == 2
        assert "Bob" not in result

    def test_missing_file_returns_none(self, tmp_path):
        result = vsr.load_agentforce_rrs(tmp_path / "nonexistent.csv")
        assert result is None

    def test_all_qualifying_no(self, tmp_path):
        content = "Employee,Qualifying\nAlice,No\nBob,No\n"
        f = tmp_path / "rrs.csv"
        f.write_text(content)
        result = vsr.load_agentforce_rrs(f)
        assert result == {}


# ---------------------------------------------------------------------------
# load_employee_grades()
# ---------------------------------------------------------------------------

class TestLoadEmployeeGrades:
    def test_loads_from_csv(self, tmp_path):
        content = "Employee,Grade\nAlice Test,Grade 7\nBob Test,Grade 5\n"
        f = tmp_path / "team_roster.csv"
        f.write_text(content)
        result = vsr.load_employee_grades(f)
        assert result["Alice Test"] == "Grade 7"
        assert result["Bob Test"] == "Grade 5"

    def test_falls_back_to_hardcoded(self, tmp_path, monkeypatch):
        # Patch DOWNLOADS so the secondary lookup (DOWNLOADS / "team_roster.csv")
        # also misses — otherwise the real team_roster.csv in the repo is found.
        monkeypatch.setattr(vsr, "DOWNLOADS", tmp_path)
        result = vsr.load_employee_grades(tmp_path / "nonexistent.csv")
        assert "Craig Scott" in result
        assert result["Craig Scott"] == "Grade 7"


# ---------------------------------------------------------------------------
# cert_corroborates_skill() — critical bug-regression tests
# ---------------------------------------------------------------------------

class TestCertCorroboratesSkill:
    def test_pdlda_matches_env_sandbox_via_domain_map(self):
        """PDLDA cert corroborates Environment/Sandbox Management via domain map."""
        matched, certs = vsr.cert_corroborates_skill(
            "Environment/Sandbox Management",
            [("Certified Platform Development Lifecycle and Deployment Architect", "")],
        )
        assert matched is True
        assert "Certified Platform Development Lifecycle and Deployment Architect" in certs

    def test_both_certs_shown_not_just_first(self):
        """Bug regression: both Platform Admin AND PDLDA should appear, not just first."""
        matched, certs = vsr.cert_corroborates_skill(
            "Environment/Sandbox Management",
            [
                ("Certified Platform Administrator", ""),
                ("Certified Platform Development Lifecycle and Deployment Architect", ""),
            ],
        )
        assert matched is True
        assert "Certified Platform Administrator" in certs
        assert "Certified Platform Development Lifecycle and Deployment Architect" in certs
        assert "|" in certs  # joined by " | "

    def test_copado_matches_env_sandbox(self):
        """Copado cert matches Environment/Sandbox Management via domain map."""
        matched, certs = vsr.cert_corroborates_skill(
            "Environment/Sandbox Management",
            [("Certified Copado Fundamentals I Source Format Pipeline", "")],
        )
        assert matched is True
        assert "Copado" in certs

    def test_agentforce_specialist_matches_data360(self):
        """Bug regression: Agentforce Specialist should NOT be excluded from Data 360."""
        matched, certs = vsr.cert_corroborates_skill(
            "Data 360 (aka: Data Cloud) for Agentforce",
            [("Certified Agentforce Specialist", "")],
        )
        assert matched is True
        assert "Agentforce Specialist" in certs

    def test_data_cloud_consultant_matches_data360(self):
        matched, certs = vsr.cert_corroborates_skill(
            "Data 360 (aka: Data Cloud) for Agentforce",
            [("Salesforce Certified Data Cloud Consultant", "")],
        )
        assert matched is True

    def test_pdlda_excluded_for_org_platform_strategy(self):
        """Bug regression: PDLDA must NOT corroborate org/platform strategy skills."""
        matched, _ = vsr.cert_corroborates_skill(
            "Org or Platform Strategy",
            [("Certified Platform Development Lifecycle and Deployment Architect", "")],
        )
        assert matched is False

    def test_cka_does_not_match_containerization(self):
        """CKA short name doesn't match 'containerization' domain map or word list."""
        matched, _ = vsr.cert_corroborates_skill(
            "Containerization frameworks & tools",
            [("CKA", "")],
        )
        assert matched is False

    def test_agentforce_specialist_matches_agentforce_operations(self):
        matched, certs = vsr.cert_corroborates_skill(
            "Agentforce Operations",
            [("Certified Agentforce Specialist", "")],
        )
        assert matched is True
        assert "Agentforce" in certs

    def test_empty_skill_name_does_not_crash(self):
        matched, _ = vsr.cert_corroborates_skill("", [("Cert A", "")])
        # empty skill → no skill_words, domain map won't match most certs; just no crash
        assert isinstance(matched, bool)

    def test_empty_cert_list_returns_false(self):
        matched, text = vsr.cert_corroborates_skill("Agentforce Operations", [])
        assert matched is False
        assert text == ""

    def test_three_certs_all_returned(self):
        """All three matching certs must be in the output string."""
        matched, certs = vsr.cert_corroborates_skill(
            "Environment/Sandbox Management",
            [
                ("Certified Platform Administrator", ""),
                ("Certified Platform Development Lifecycle and Deployment Architect", ""),
                ("Certified Copado Fundamentals I Source Format Pipeline", ""),
            ],
        )
        assert matched is True
        assert "Platform Administrator" in certs
        assert "Lifecycle and Deployment Architect" in certs
        assert "Copado" in certs

    def test_shield_cert_excluded_for_observability(self):
        """Salesforce Shield should not corroborate Observability."""
        matched, _ = vsr.cert_corroborates_skill(
            "Observability Frameworks and Tools",
            [("Salesforce Shield", "")],
        )
        assert matched is False


# ---------------------------------------------------------------------------
# validate_record() — core logic scenarios
# ---------------------------------------------------------------------------

class TestValidateRecord:
    """validate_record integration tests using fixture catalog/af/devops dicts."""

    def _row(self, skill, rating, employee="Alice Test", date="08/26/2025"):
        return {
            "Resource": employee,
            "Skill or Certification": skill,
            "Rating": rating,
            "Evaluation Date": date,
        }

    # ── Catalog lookup ──────────────────────────────────────────────────

    def test_skill_in_catalog(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Operations", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, {})
        assert result["In PSA Catalog"] == "Yes"

    def test_skill_not_in_catalog(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Completely Unknown Skill XYZ12345", "2- Intermediate")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, {})
        assert result["In PSA Catalog"] == "No"
        assert "not found in PSA catalog" in result["Validation Notes"]

    # ── AF rating checks ────────────────────────────────────────────────

    def test_af_rating_below_minimum(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Operations", "2- Intermediate")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, {})
        assert result["AF Rating Met"] == "No"
        assert "AGENTFORCE: Rating below minimum" in result["Validation Notes"]

    def test_af_rating_at_minimum(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Operations", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist)
        assert result["AF Rating Met"] == "Yes"
        assert "Rating below minimum" not in result.get("Validation Notes", "")

    def test_af_rating_above_minimum(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Operations", "4- Specialist")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist)
        assert result["AF Rating Met"] == "Yes"

    # ── Data 360 cert checks ────────────────────────────────────────────

    def test_data360_missing_cert_note_added(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Data 360 (aka: Data Cloud) for Agentforce", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops,
                                     {"Alice Test": [("Certified Platform Administrator", "")]})
        assert "AGENTFORCE: Data 360" in result["Validation Notes"]
        assert result["Suggested Cert Path"] != ""
        assert "Data Cloud" in result["Suggested Cert Path"]

    def test_data360_with_agentforce_specialist_shows_cert(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Data 360 (aka: Data Cloud) for Agentforce", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist)
        assert result["Cert Corroborates Skill"] == "Yes"
        assert "Agentforce Specialist" in result["Supporting Cert"]

    def test_data360_with_data_cloud_cert_no_note(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_data_cloud):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Carol Test": "Grade 7"})
        row = self._row("Data 360 (aka: Data Cloud) for Agentforce", "3- Advanced", employee="Carol Test")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_data_cloud)
        assert "AGENTFORCE: Data 360" not in result.get("Validation Notes", "")

    # ── Tier 1 AF cert requirement ──────────────────────────────────────

    def test_tier1_af_without_specialist_cert_flagged(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_without_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Bob Test": "Grade 7"})
        row = self._row("Agentforce Operations", "3- Advanced", employee="Bob Test")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, certs_without_af_specialist)
        assert "AGENTFORCE: Tier 1 Agentforce skill" in result["Validation Notes"]

    def test_tier1_af_with_specialist_cert_no_flag(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Operations", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist)
        assert "Tier 1 Agentforce skill" not in result.get("Validation Notes", "")

    def test_tier1_af_below_minimum_no_tier1_flag(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        """If rating < 3, tier1 check doesn't fire."""
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Operations", "2- Intermediate")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, {})
        assert "Tier 1 Agentforce skill" not in result.get("Validation Notes", "")

    # ── Tier 2 grade ceiling ────────────────────────────────────────────

    def test_tier2_above_grade_ceiling(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        # Grade 5 ceiling = 3; rated 4-Specialist → exceeds ceiling
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Bob Test": "Grade 5"})
        row = self._row("Business Acumen", "4- Specialist", employee="Bob Test")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops,
                                     {"Bob Test": [("Certified Agentforce Specialist", "")]})
        assert "TIER2:" in result["Validation Notes"]

    def test_tier2_within_grade_ceiling(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        # Grade 7 ceiling = 4; rated 4-Specialist → OK
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Business Acumen", "4- Specialist")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist)
        assert "TIER2:" not in result.get("Validation Notes", "")

    # ── Justification required ──────────────────────────────────────────

    def test_justification_required_at_3plus(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Bob Test": "Grade 7"})
        row = self._row("Environment/Sandbox Management", "3- Advanced", employee="Bob Test")
        result = vsr.validate_record(
            row, minimal_catalog, minimal_agentforce, minimal_devops,
            {"Bob Test": [("Certified Platform Development Lifecycle and Deployment Architect", "")]},
        )
        assert "JUSTIFICATION REQUIRED:" in result["Validation Notes"]

    def test_justification_not_required_below_3(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Bob Test": "Grade 7"})
        row = self._row("Environment/Sandbox Management", "2- Intermediate", employee="Bob Test")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops,
                                     {"Bob Test": []})
        assert "JUSTIFICATION REQUIRED:" not in result.get("Validation Notes", "")

    # ── DevOps grade floor ──────────────────────────────────────────────

    def test_devops_below_grade_floor(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        # Grade 5 requires ≥2; rated 1-Entry → below floor
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Bob Test": "Grade 5"})
        row = self._row("Environment/Sandbox Management", "1- Entry", employee="Bob Test")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, {})
        assert result["Grade Floor Met"] == "No"
        assert "DEVOPS:" in result["Validation Notes"]

    def test_devops_at_grade_floor(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        # Grade 5 requires ≥2; rated 2-Intermediate → meets floor
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Bob Test": "Grade 5"})
        row = self._row("Environment/Sandbox Management", "2- Intermediate", employee="Bob Test")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, {})
        assert result["Grade Floor Met"] == "Yes"

    def test_devops_grade_reqs_populated(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Environment/Sandbox Management", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, {})
        assert result["Is DevOps Skill"] == "Yes"
        assert "Grade" in result["DevOps Grade Requirements"]

    # ── Cert corroboration at 4-Specialist ─────────────────────────────

    def test_cert_note_at_4specialist_no_cert(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Bob Test": "Grade 7"})
        # Bob has a cert on file (so the condition fires) but it doesn't corroborate this skill
        row = self._row("Org or Platform Strategy", "4- Specialist", employee="Bob Test")
        # Use PDLDA which is EXCLUDED for org/platform strategy
        result = vsr.validate_record(
            row, minimal_catalog, minimal_agentforce, minimal_devops,
            {"Bob Test": [("Certified Platform Development Lifecycle and Deployment Architect", "")]},
        )
        assert "CERT:" in result["Validation Notes"]

    # ── AF delivery skill checks ────────────────────────────────────────

    def test_delivery_skill_no_rr_data_no_delivery_note(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        """When rr_counts is None (not loaded), no delivery RR note is added."""
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Testing", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops,
                                     certs_with_af_specialist, rr_counts=None)
        assert "Delivery evidence insufficient" not in result.get("Validation Notes", "")

    def test_delivery_skill_insufficient_rrs(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Testing", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops,
                                     certs_with_af_specialist, rr_counts={"Alice Test": 0})
        assert "AGENTFORCE: Delivery evidence insufficient" in result["Validation Notes"]
        assert "0 qualifying" in result["Validation Notes"]

    def test_delivery_skill_sufficient_rrs_no_flag(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Testing", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops,
                                     certs_with_af_specialist, rr_counts={"Alice Test": 2})
        assert "Delivery evidence insufficient" not in result.get("Validation Notes", "")

    def test_delivery_skill_no_af_cert_flagged(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_without_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Bob Test": "Grade 7"})
        row = self._row("Agentforce Testing", "3- Advanced", employee="Bob Test")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops,
                                     certs_without_af_specialist, rr_counts={"Bob Test": 3})
        assert "AGENTFORCE: Delivery evidence insufficient" in result["Validation Notes"]
        assert "specialist certification not on file" in result["Validation Notes"].lower()

    # ── Result structure ────────────────────────────────────────────────

    def test_ok_result_when_no_issues(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Operations", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops,
                                     certs_with_af_specialist, rr_counts={"Alice Test": 3})
        assert result["Validation Status"] == "OK"
        assert result["Validation Notes"] == ""

    def test_result_contains_employee_grade(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Operations", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops, {})
        assert result["Employee Grade"] == "Grade 7"

    def test_cert_corroborates_populated(self, monkeypatch, minimal_catalog, minimal_agentforce, minimal_devops, certs_with_af_specialist):
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        row = self._row("Agentforce Operations", "3- Advanced")
        result = vsr.validate_record(row, minimal_catalog, minimal_agentforce, minimal_devops,
                                     certs_with_af_specialist)
        assert result["Cert Corroborates Skill"] == "Yes"
        assert "Agentforce Specialist" in result["Supporting Cert"]


# ---------------------------------------------------------------------------
# write_detail() / write_summary() / write_feedback()
# ---------------------------------------------------------------------------

class TestWriteFunctions:
    def _make_record(self, employee, skill, status, notes=""):
        return {
            "Resource": employee,
            "Skill or Certification": skill,
            "Rating": "3- Advanced",
            "Evaluation Date": "08/26/2025",
            "Employee Grade": "Grade 7",
            "Validation Status": status,
            "Validation Notes": notes,
            "Cert Corroborates Skill": "Yes",
            "Supporting Cert": "Certified Agentforce Specialist",
        }

    def test_write_detail_creates_file(self, tmp_path):
        records = [self._make_record("Alice", "Agentforce Operations", "OK")]
        out = tmp_path / "detail.csv"
        vsr.write_detail(records, out)
        assert out.exists()
        rows = list(csv.DictReader(out.open()))
        assert len(rows) == 1
        assert rows[0]["Resource"] == "Alice"

    def test_write_detail_empty_no_file_written(self, tmp_path):
        out = tmp_path / "detail.csv"
        vsr.write_detail([], out)
        assert not out.exists()

    def test_write_summary_creates_file(self, tmp_path):
        records = [
            self._make_record("Alice", "Skill A", "OK"),
            self._make_record("Alice", "Skill B", "NEEDS REVIEW", "AGENTFORCE: issue"),
        ]
        out = tmp_path / "summary.csv"
        vsr.write_summary(records, out, {"Alice": [("Cert A", "2024")]})
        assert out.exists()
        rows = list(csv.DictReader(out.open()))
        assert rows[0]["Resource"] == "Alice"
        assert rows[0]["Total Skills"] == "2"
        assert rows[0]["Needs Review"] == "1"

    def test_write_feedback_creates_file(self, tmp_path):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice": "Grade 7"})
        records = [self._make_record("Alice", "Skill A", "NEEDS REVIEW", "AGENTFORCE: issue")]
        out = tmp_path / "feedback.txt"
        vsr.write_feedback(records, out, {"Alice": [("Cert A", "2024")]})
        assert out.exists()
        content = out.read_text()
        assert "Alice" in content
        assert "Skill A" in content
        monkeypatch.undo()

    def test_write_feedback_ok_employee(self, tmp_path):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice": "Grade 7"})
        records = [self._make_record("Alice", "Skill A", "OK")]
        out = tmp_path / "feedback.txt"
        vsr.write_feedback(records, out, {})
        content = out.read_text()
        assert "All skill ratings passed" in content
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# load_agentforce() and load_devops_guide() integration tests
# ---------------------------------------------------------------------------

class TestLoadAgentforce:
    def test_skips_first_3_rows(self, tmp_path):
        content = "header1,header2,header3,header4,header5\nrow2,,,,\nrow3,,,,\nAgentforce Operations,Definition text,Criteria 3,Criteria 4,\n"
        f = tmp_path / "af.csv"
        f.write_text(content)
        result = vsr.load_agentforce(f)
        assert "agentforce operations" in result
        entry = result["agentforce operations"]
        assert entry["af_skill_name"] == "Agentforce Operations"
        assert entry["af_criteria_3"] == "Criteria 3"
        assert entry["af_min_rating"] == 3

    def test_skips_empty_rows(self, tmp_path):
        content = "h1,h2,h3,h4,h5\nrow2,,,,\nrow3,,,,\nSkill One,def,c3,c4,\n,,,,\nSkill Two,def2,c3b,c4b,\n"
        f = tmp_path / "af.csv"
        f.write_text(content)
        result = vsr.load_agentforce(f)
        assert "skill one" in result
        assert "skill two" in result
        assert "" not in result


class TestLoadDevopsGuide:
    def test_loads_skills_with_grade_reqs(self, tmp_path):
        # row[0]=category, row[1]=skill_name, row[2]=description, row[3..9]=grade reqs
        content = "Category,Skill Name,Description,1,2,2,3,3,4,4\n,Environment/Sandbox Management,Sandbox mgmt,1,2,2,3,3,4,4\n"
        f = tmp_path / "devops.csv"
        f.write_text(content)
        result = vsr.load_devops_guide(f)
        assert "environment/sandbox management" in result
        entry = result["environment/sandbox management"]
        assert entry["devops_grade_reqs"]["Grade 4"] == 1
        assert entry["devops_grade_reqs"]["Grade 7"] == 3

    def test_skips_rows_with_too_few_numeric_values(self, tmp_path):
        # Header row has non-numeric grade values → should be skipped
        content = "Category,Skill,Description,G4,G5,G6,G7,G8,G9,G11\nCat,Header Row,desc,minG4,minG5,minG6,minG7,minG8,minG9,minG11\n"
        f = tmp_path / "devops.csv"
        f.write_text(content)
        result = vsr.load_devops_guide(f)
        assert "header row" not in result

    def test_skips_rows_with_empty_skill_name(self, tmp_path):
        # Row with empty row[1] should hit the continue branch (line 200)
        # Use a non-numeric header so the header row gets skipped via len(numeric_vals) < 4
        content = (
            "Category,Skill Name,Description,Grade4,Grade5,Grade6,Grade7,Grade8,Grade9,Grade11\n"
            "DevOps,,Empty skill name,1,2,2,3,3,4,4\n"
        )
        f = tmp_path / "devops.csv"
        f.write_text(content)
        result = vsr.load_devops_guide(f)
        # The header row has non-numeric grades (skipped), the data row has empty skill name (skipped)
        assert result == {}

    def test_category_tracked_across_rows(self, tmp_path):
        # First data row sets category from row[0]; second row inherits it (row[0] empty)
        content = (
            "Category,Skill Name,Description,1,2,2,3,3,4,4\n"
            "DevOps,Skill A,desc A,1,2,2,3,3,4,4\n"
            ",Skill B,desc B,1,2,2,3,3,4,4\n"
        )
        f = tmp_path / "devops.csv"
        f.write_text(content)
        result = vsr.load_devops_guide(f)
        assert result["skill b"]["devops_category"] == "DevOps"

    def test_non_numeric_grade_col_skipped_gracefully(self, tmp_path):
        # Mix of numeric and non-numeric grade cols: ValueError case covered
        content = "Category,Skill Name,Description,1,2,2,3,N/A,4,4\nDevOps,Skill C,desc,1,2,2,3,N/A,4,4\n"
        f = tmp_path / "devops.csv"
        f.write_text(content)
        result = vsr.load_devops_guide(f)
        # Should load despite one non-numeric grade column
        assert "skill c" in result


class TestFindMostRecentRatings:
    def test_finds_most_recent_csv(self, tmp_path, monkeypatch):
        import time
        f1 = tmp_path / "skill_certification_ratings_old.csv"
        f1.write_text("col\n")
        time.sleep(0.01)
        f2 = tmp_path / "skill_certification_ratings_new.csv"
        f2.write_text("col\n")
        monkeypatch.setattr(vsr, "DOWNLOADS", tmp_path)
        result = vsr.find_most_recent_ratings()
        assert result == f2

    def test_exits_if_none_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vsr, "DOWNLOADS", tmp_path)
        with pytest.raises(SystemExit):
            vsr.find_most_recent_ratings()


class TestValidateRecordEdgeCases:
    def _row(self, skill, rating, employee="Alice Test", date="08/26/2025"):
        return {
            "Resource": employee,
            "Skill or Certification": skill,
            "Rating": rating,
            "Evaluation Date": date,
        }

    def test_devops_grade_label_fallback_for_nonstandard_grade(self, monkeypatch):
        """Line 880: grade_label = check_grade when check_grade not in DEVOPS_GRADES."""
        # Create a devops fixture where grade_reqs has a non-standard grade
        custom_devops = {
            "environment/sandbox management": {
                "devops_skill_name":  "Environment/Sandbox Management",
                "devops_category":    "DevOps",
                "devops_description": "Sandbox management",
                "devops_grade_reqs":  {"Grade 10": 3},  # Grade 10 not in DEVOPS_GRADES
            }
        }
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 10"})
        catalog = {
            "environment/sandbox management": {
                "catalog_name": "Environment/Sandbox Management",
                "catalog_id": "SKL-001",
                "catalog_description": "Sandbox",
                "catalog_type": "Technical",
                "catalog_category": "DevOps",
                "catalog_parent_cat": "Delivery",
            }
        }
        row = self._row("Environment/Sandbox Management", "1- Entry")
        result = vsr.validate_record(row, catalog, {}, custom_devops, {})
        assert result["Grade Floor Met"] == "No"
        # grade_label should be "Grade 10" (the else branch)
        assert "Grade 10" in result["Validation Notes"]

    def test_af_level_definition_uses_criteria4_at_rating4(self, monkeypatch):
        """AF level def should show criteria_4 when rating >= 4."""
        af = {
            "agentforce operations": {
                "af_skill_name":  "Agentforce Operations",
                "af_definition":  "Definition",
                "af_criteria_3":  "Criteria 3 text",
                "af_criteria_4":  "Criteria 4 text",
                "af_criteria_5":  "",
                "af_min_rating":  3,
            }
        }
        monkeypatch.setattr(vsr, "EMPLOYEE_GRADES", {"Alice Test": "Grade 7"})
        catalog = {
            "agentforce operations": {
                "catalog_name": "Agentforce Operations", "catalog_id": "SKL-002",
                "catalog_description": "", "catalog_type": "Technical",
                "catalog_category": "Agentforce", "catalog_parent_cat": "AI",
            }
        }
        row = self._row("Agentforce Operations", "4- Specialist")
        result = vsr.validate_record(
            row, catalog, af, {},
            {"Alice Test": [("Certified Agentforce Specialist", "")]},
        )
        assert "4-Specialist" in result.get("AF Level Definition", "")
        assert "Criteria 4 text" in result.get("AF Level Definition", "")
