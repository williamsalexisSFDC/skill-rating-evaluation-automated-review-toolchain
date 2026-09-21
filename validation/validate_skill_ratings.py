#!/usr/bin/env python3
"""
Skill & Certification Rating Validator

Joins scraped employee ratings against:
  1. PSA Skills Catalog        — verifies the skill exists
  2. Agentforce Required Skills — minimum rating of 3+ required on all listed skills
  3. DevOps Leveling Guide      — minimum required rating per grade level (Grades 4-11)

Outputs three files:
  - skill_validation_detail_<timestamp>.csv  — one row per employee rating with validation results
  - skill_validation_summary_<timestamp>.csv — one row per employee with pass/fail counts
  - skill_validation_feedback_<timestamp>.txt — human-readable feedback per employee

Usage:
    python3 validate_skill_ratings.py

    By default uses the most recently modified skill_certification_ratings*.csv in Downloads.
    Override with:
        python3 validate_skill_ratings.py --ratings path/to/ratings.csv
        python3 validate_skill_ratings.py --roster path/to/team_roster.csv
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def _find_catalog_file(base: Path) -> Path:
    """Return the most recently modified PSA catalog file in base dir.

    Accepts both CSV (old PSA report format) and XLS/HTML (new Salesforce
    'All Skills and Certifications' export format).
    """
    candidates = (
        list(base.glob("PSA Skills and Certifications Report*.csv"))
        + list(base.glob("All Skills and Certifications*.xls"))
        + list(base.glob("All Skills and Certifications*.csv"))
    )
    if not candidates:
        raise FileNotFoundError(
            "No PSA catalog file found in the project folder.\n"
            "Export 'All Skills and Certifications' from org62 Reports and copy it here."
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ── File paths ──────────────────────────────────────────────────────────────────────────────────────
DOWNLOADS = Path(__file__).parent.parent

CATALOG_FILE     = _find_catalog_file(DOWNLOADS)
AGENTFORCE_FILE  = DOWNLOADS / "Agentforce Ready and Expert Skills Ratings  - Agentforce Skills .csv"
DEVOPS_FILE      = DOWNLOADS / "FY26 DevOps Leveling Guide (Working Copy) - Current DevOps .csv"
CERT_FILE        = DOWNLOADS / "employee_certifications.csv"
RR_FILE          = DOWNLOADS / "agentforce_resource_requests.csv"

DEVOPS_GRADES    = ["Grade 4", "Grade 5", "Grade 6", "Grade 7", "Grade 8", "Grade 9", "Grade 11"]
DEVOPS_TITLES    = [
    "Associate DevOps Engineer", "DevOps Engineer", "Sr. DevOps Engineer",
    "DevOps Architect", "Sr. DevOps Architect", "Director - DevOps", "VP, Technical Consulting"
]
RATING_ORDER     = {"1- Entry": 1, "2- Intermediate": 2, "3- Advanced": 3, "4- Specialist": 4}

_FALLBACK_EMPLOYEE_GRADES = {
    "Keith Johnson":  "Grade 6",
    "Craig Scott":    "Grade 7",
    "Kalisaran M B":  "Grade 8",
    "Ramandeep Kaur": "Grade 5",
    "Jordan Tetzel":  "Grade 5",
    "Justin Powall":  "Grade 6",
}


def load_employee_grades(roster_path: Path | None = None) -> dict[str, str]:
    candidates: list[Path] = []
    if roster_path:
        candidates.append(Path(roster_path))
    candidates.append(DOWNLOADS / "team_roster.csv")

    for path in candidates:
        if path.exists():
            grades: dict[str, str] = {}
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    name  = (row.get("Employee") or "").strip()
                    grade = (row.get("Grade") or "").strip()
                    if name:
                        grades[name] = grade
            if grades:
                print(f"Loaded {len(grades)} employee grades from {path.name}")
                return grades

    print("team_roster.csv not found — using hardcoded fallback grades.")
    return _FALLBACK_EMPLOYEE_GRADES.copy()


def load_af_enabled(roster_path: Path | None = None) -> frozenset[str]:
    candidates: list[Path] = []
    if roster_path:
        candidates.append(Path(roster_path))
    candidates.append(DOWNLOADS / "team_roster.csv")
    for path in candidates:
        if path.exists():
            enabled: set[str] = set()
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    name = (row.get("Employee") or "").strip()
                    af   = (row.get("AF Enabled") or "").strip().lower()
                    if name and af == "yes":
                        enabled.add(name)
            return frozenset(enabled)
    return frozenset()


EMPLOYEE_GRADES: dict[str, str] = {}
AF_ENABLED_EMPLOYEES: frozenset[str] = frozenset()


def normalize(name: str) -> str:
    return re.sub(r"^\*+", "", name).strip().lower()


def find_most_recent_ratings() -> Path:
    candidates = sorted(DOWNLOADS.glob("skill_certification_ratings*.csv"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        sys.exit("No skill_certification_ratings*.csv found. Run the scraper first.")
    return candidates[-1]


def rating_int(rating_str: str) -> int:
    return RATING_ORDER.get(rating_str.strip(), 0)


def _parse_html_xls(path: Path) -> list[dict]:
    """Parse a Salesforce HTML-as-XLS export into a list of row dicts."""
    text = path.read_bytes().decode("utf-8", errors="replace")
    rows_raw = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.DOTALL | re.IGNORECASE)

    def strip_tags(s: str) -> str:
        s = re.sub(r"<[^>]+>", "", s).strip()
        return (s.replace("&gt;", ">").replace("&lt;", "<")
                 .replace("&amp;", "&").replace("&nbsp;", " "))

    def cells(row_html: str) -> list[str]:
        return [strip_tags(c) for c in
                re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.DOTALL | re.IGNORECASE)]

    if not rows_raw:
        return []
    headers = cells(rows_raw[0])
    result = []
    for raw in rows_raw[1:]:
        vals = cells(raw)
        if vals:
            result.append(dict(zip(headers, vals)))
    return result


def load_catalog(path: Path) -> dict:
    index = {}
    content_start = path.read_bytes()[:512].lstrip(b"\xff\xfe").lstrip(b"\xef\xbb\xbf")
    is_html = content_start.lstrip().lower().startswith(b"<")

    rows: list[dict]
    if is_html:
        rows = _parse_html_xls(path)
    else:
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

    for row in rows:
        name = row.get("Skill or Certification: Skill or Certification Name", "").strip()
        if not name:
            continue
        index[normalize(name)] = {
            "catalog_name":        name,
            "catalog_id":          row.get("Skill or Certification: ID", "").strip(),
            "catalog_description": row.get("Description", "").strip(),
            "catalog_type":        row.get("Type", "").strip(),
            "catalog_category":    row.get("Category", "").strip(),
            "catalog_parent_cat":  row.get("Parent Category", "").strip(),
        }
    return index


def load_agentforce(path: Path) -> dict:
    skills = {}
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    for row in rows[3:]:
        if not row or not row[0].strip():
            continue
        name = row[0].strip()
        skills[normalize(name)] = {
            "af_skill_name":  name,
            "af_definition":  row[1].strip() if len(row) > 1 else "",
            "af_criteria_3":  row[2].strip() if len(row) > 2 else "",
            "af_criteria_4":  row[3].strip() if len(row) > 3 else "",
            "af_criteria_5":  row[4].strip() if len(row) > 4 else "",
            "af_min_rating":  3,
        }
    return skills


def load_devops_guide(path: Path) -> dict:
    skills = {}
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    grade_cols = list(range(3, 10))
    current_category = ""

    for row in rows:
        if len(row) < 7 or not row[1].strip():
            continue

        if row[0].strip():
            current_category = row[0].strip()

        numeric_vals = []
        for col in grade_cols:
            try:
                v = int(row[col].strip())
                if 1 <= v <= 5:
                    numeric_vals.append(v)
            except (ValueError, IndexError):
                pass
        if len(numeric_vals) < 4:
            continue

        name = row[1].strip().lstrip("*")
        description = row[2].strip() if len(row) > 2 else ""

        grade_reqs = {}
        for i, grade in enumerate(DEVOPS_GRADES):
            col = grade_cols[i]
            if col < len(row):
                try:
                    grade_reqs[grade] = int(row[col].strip())
                except ValueError:
                    pass

        skills[normalize(name)] = {
            "devops_skill_name":  name,
            "devops_category":    current_category,
            "devops_description": description,
            "devops_grade_reqs":  grade_reqs,
        }
    return skills


def load_certifications(path: Path) -> dict:
    certs = defaultdict(list)
    if not path.exists():
        return certs
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            employee = row["Employee"].strip()
            cert     = row["Certification"].strip()
            earned   = row.get("Earned Date", "").strip()
            if employee and cert:
                certs[employee].append((cert, earned))
    return dict(certs)


_RR_GA_DATE         = datetime(2024, 10, 1)
_RR_MIN_DAYS        = 90
_RR_ACTIVE_STATUSES = frozenset({"assigned", "in progress", "closed", "complete"})


def load_agentforce_rrs(path: Path):
    if not path.exists():
        return None
    counts: dict[str, int] = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            emp = row.get("Employee", "").strip()
            if not emp:
                continue
            if row.get("AF Skill", "").strip().lower() != "yes":
                continue
            if row.get("Status", "").strip().lower() not in _RR_ACTIVE_STATUSES:
                continue
            try:
                start = datetime.strptime(row.get("Start Date", "").strip(), "%m/%d/%Y")
                if start < _RR_GA_DATE:
                    continue
            except ValueError:
                continue
            try:
                if int(row.get("Duration Days", "0").strip()) < _RR_MIN_DAYS:
                    continue
            except ValueError:
                continue
            counts[emp] = counts.get(emp, 0) + 1
    return counts


_CERT_STOPWORDS = {"and", "the", "of", "in", "for", "to", "a", "an", "with", "by", "at"}

_JUSTIFICATION_REQUIRED_SKILLS: dict[str, str] = {
    "observability frameworks and tools": (
        "3-Advanced on Observability requires hands-on implementation at the instrumentation level — "
        "not configuration of managed packages (e.g., Salesforce Shield, packaged Splunk connectors). "
        "Qualifying evidence includes: instrumenting CI/CD pipelines with OpenTelemetry or a comparable "
        "SDK; building metric/log/trace dashboards from your own telemetry data (Grafana + Prometheus, "
        "Datadog, ELK/OpenSearch, or equivalent); or tuning alert thresholds and on-call runbooks on a "
        "production system. "
        "Please justify with: (1) specific tool(s) used, (2) whether implemented directly or via a "
        "managed package/pre-built integration, and (3) the customer engagement or internal project context."
    ),

    "containerization frameworks and tools": (
        "3-Advanced on Containerization requires hands-on Kubernetes engineering experience — not "
        "local Docker Desktop usage, not running pre-configured Helm charts without modification, and "
        "not conceptual familiarity from coursework or guided labs. "
        "\n\n"
        "The qualifying bar is the ability to independently design and operate containerized workloads "
        "on a real Kubernetes cluster. Qualifying evidence includes:"
        "\n\n"
        "Kubernetes administration: Independently configured cluster networking (CNI, Ingress controllers), "
        "RBAC policies, persistent storage (PVCs, StorageClasses), resource quotas, and namespace "
        "isolation — not just kubectl get/apply following runbooks."
        "\n\n"
        "Application packaging: Authored a Helm chart or Kustomize overlay from scratch for a "
        "multi-component application, with parameterized values, environment overlays, and "
        "documented upgrade strategy — not just modified an existing chart's values.yaml."
        "\n\n"
        "GitOps: Designed a GitOps reconciliation loop (ArgoCD or Flux) where a Git repository "
        "is the sole source of truth for live cluster state, including app-of-apps patterns, "
        "sync policies, and health checks."
        "\n\n"
        "CI/CD integration: Authored pipeline stages that build, scan (container image scanning), "
        "push, and deploy container images to a registry and a running cluster, with rollback "
        "logic — not just added a docker build step to an existing pipeline."
        "\n\n"
        "What does NOT qualify for 3-Advanced: (1) Using Docker Desktop for local development "
        "without Kubernetes cluster experience; (2) deploying a pre-built Helm chart following "
        "documentation without authoring chart logic; (3) completing a Kubernetes tutorial or "
        "lab environment without production or customer-facing deployment; (4) KCNA certification "
        "alone (knowledge-based, no hands-on component)."
        "\n\n"
        "Please provide: (1) cluster platform (self-managed K8s, EKS, AKS, GKE, OpenShift, or other), "
        "(2) your specific role — did you design the cluster/workloads or deploy onto an existing "
        "platform someone else built, (3) whether work was on a customer engagement or internal "
        "infrastructure, and (4) link to a Helm chart, Kustomize config, ArgoCD app definition, "
        "or pipeline config that demonstrates independent authorship."
    ),

    "configuration management frameworks and tools": (
        "3-Advanced on Configuration Management requires independent authorship and architectural design "
        "of CI/CD pipeline infrastructure — not bug fixes, feature enhancements, or configuration changes "
        "made under the guidance of another engineer. "
        "\n\n"
        "The qualifying bar is the ability to design and implement centralized, reusable pipeline "
        "governance from scratch. Platform-specific evidence that qualifies:"
        "\n\n"
        "GitHub Actions: Authored a composite action (action.yml, using: composite) with parameterized "
        "inputs, outputs, and error handling; OR designed a reusable workflow (on: workflow_call) in a "
        "centralized org-level actions repository, versioned via semantic tags "
        "(e.g., uses: org/shared-actions/.github/workflows/build.yml@v1), with caller repos referencing "
        "it via thin shim workflows."
        "\n\n"
        "GitLab CI/CD: Authored a CI/CD component (.gitlab/ci/components/) with declared inputs; OR "
        "designed a reusable pipeline template hierarchy using 'include: component:' or "
        "'include: project:' references from a group-level shared project, pinned to a version tag."
        "\n\n"
        "Bitbucket Pipelines: Authored a custom Pipe (Docker-based reusable step published to a "
        "registry with defined YAML parameters); OR designed shared pipeline templates consumed "
        "via 'include:' across multiple repos."
        "\n\n"
        "IaC and Config Management tools: Authored parameterized Terraform modules (not just "
        "ran terraform apply against existing configs); OR written Ansible playbooks/roles for "
        "idempotent server state management; OR designed a GitOps workflow (ArgoCD, Flux) "
        "reconciling a Git repo against live Kubernetes cluster state."
        "\n\n"
        "What does NOT qualify for 3-Advanced: (1) Running or troubleshooting existing pipelines, "
        "(2) adding a new job or step to an existing workflow file, (3) configuring environment "
        "variables or secrets in an existing pipeline, (4) using Copado or Gearset as the sole "
        "evidence without platform-native workflow authorship, (5) any work performed under "
        "active guidance or review of a more senior engineer without independent design decisions."
        "\n\n"
        "Please provide: (1) platform (GitHub/GitLab/Bitbucket/other), (2) whether you authored "
        "the architecture or contributed to an existing one, (3) link to repo, PR, or artifact "
        "that demonstrates independent authorship, and (4) whether the work is in production and "
        "consumed by other teams."
    ),

    "environment/sandbox management": (
        "3-Advanced on Environment/Sandbox Management requires independently designed org environment "
        "architecture — not foundational sandbox creation (covered by Platform Administrator) and not "
        "working within an environment strategy that someone else designed."
        "\n\n"
        "The qualifying bar is independent design and governance of a Salesforce environment strategy. "
        "Qualifying evidence includes:"
        "\n\n"
        "Sandbox strategy design: Independently designed a sandbox allocation model for a multi-team "
        "Salesforce implementation — selecting sandbox tiers (Developer, Developer Pro, Partial, Full), "
        "assigning sandboxes to dev / QA / integration / staging / UAT roles, and establishing a "
        "refresh cadence aligned to sprint or release cadence."
        "\n\n"
        "Scratch org governance: Configured Salesforce DX scratch orgs with project-scratch-def.json, "
        "org shapes, source tracking, and seeding strategies in a CI/CD pipeline context."
        "\n\n"
        "DevOps pipeline environment management: Designed an environment tree in Copado or Gearset — "
        "not just ran existing pipelines, but designed the branch-to-environment promotion path, "
        "environment variable strategy, and conflict resolution approach for the team."
        "\n\n"
        "What does NOT qualify for 3-Advanced: (1) Using a developer sandbox for solo feature work "
        "without owning the environment strategy; (2) Salesforce Certified Platform Administrator "
        "alone — validates foundational sandbox creation, not environment architecture; "
        "(3) Being staffed on a project where another engineer designed the sandbox strategy while "
        "you worked within it."
        "\n\n"
        "Cert path for this skill — "
        "(1) Salesforce Certified Development Lifecycle and Deployment Architect (PDLDA — primary; "
        "if you hold PDLDA, document the specific environment architecture decisions you made on a "
        "customer engagement as your justification); "
        "(2) Salesforce Certified Advanced Administrator (secondary; covers Change Sets, sandbox "
        "management workflow, and metadata deployment depth beyond Platform Admin); "
        "(3) Copado Fundamentals I or II (supplementary; validates environment tree design and "
        "sandbox promotion path management in a Salesforce DevOps pipeline). "
        "Platform Administrator alone is not sufficient for 3-Advanced. "
        "4-Specialist: PDLDA + Advanced Administrator + evidence of enterprise-scale environment "
        "governance (multi-team or multi-release-train sandbox strategy; org shape governance policy; "
        "scratch org pool design for high-velocity CI/CD)."
        "\n\n"
        "Please provide: (1) cert(s) held from the path above, (2) the customer engagement or project "
        "where you independently designed the environment strategy, (3) whether you were the environment "
        "architect or worked within a strategy someone else defined, and (4) whether you managed a "
        "multi-sandbox allocation model or worked primarily in a single developer sandbox."
    ),
}

# 17 skills required at 3+ for Agentforce Ready (Salesforce Readiness Definition, page 3)
_AF_READY_SKILLS: frozenset[str] = frozenset({
    "build and deploy technical capabilities",
    "development lifecycle frameworks",
    "retrieval augmented generation",
    "design and configure solutions",
    "conversation design",
    "prompt engineering",
    "prompt builder",
    "agentforce delivery",
    "agentforce testing",
    "data 360 (aka: data cloud) for agentforce",
    "data cloud for agentforce",
    "flow",
    "ai consulting",
    "action planning",
    "demonstrate business acumen",
    "executive alignment",
    "agility",
    "agentforce security",
})

# 4 skills required at 3+ only for Agentforce Expert (not counted in the 17 Ready skills)
_AF_EXPERT_ONLY_SKILLS: frozenset[str] = frozenset({
    "agent performance tracking and optimization",
    "agentforce troubleshooting",
    "ai ecosystem and frameworks",
    "agentic delivery",
})


def _is_af_ready_skill(skill_name: str) -> bool:
    norm = normalize(skill_name)
    return any(s in norm or norm in s for s in _AF_READY_SKILLS)


def _is_af_expert_only_skill(skill_name: str) -> bool:
    norm = normalize(skill_name)
    return any(s in norm or norm in s for s in _AF_EXPERT_ONLY_SKILLS)


_AF_TIER2_SKILLS = frozenset({
    "demonstrate business acumen",
    "business acumen",
    "ai consulting",
    "executive alignment",
    "agility",
})

_TIER2_GRADE_CEILING: dict[str, int] = {
    "Grade 4":  2,
    "Grade 5":  3,
    "Grade 6":  3,
    "Grade 7":  4,
    "Grade 8":  4,
    "Grade 9":  5,
    "Grade 11": 5,
}


def _is_af_tier2_skill(skill_name: str) -> bool:
    norm = normalize(skill_name)
    return any(t2 in norm or norm in t2 for t2 in _AF_TIER2_SKILLS)


_AF_DELIVERY_KEYWORDS = frozenset({
    "delivery", "testing", "conversation design", "performance tracking",
    "field service",
})

_AF_DELIVERY_EXPLICIT = frozenset({
    "ai ecosystem and frameworks",
    "retrieval augmented generation",
})


def _is_af_delivery_skill(skill_name: str, af_skill_name: str = "") -> bool:
    lower    = skill_name.lower()
    af_lower = af_skill_name.lower()
    return (
        any(kw in lower or kw in af_lower for kw in _AF_DELIVERY_KEYWORDS)
        or any(ex in lower or ex in af_lower for ex in _AF_DELIVERY_EXPLICIT)
    )


def _has_agentforce_specialist_cert(cert_list: list) -> bool:
    for cert_name, _ in cert_list:
        n = normalize(cert_name)
        if "agentforce" in n and ("specialist" in n or "expert" in n):
            return True
    return False


CERT_DOMAIN_MAP = {
    "development lifecycle and deployment": [
        "environment", "sandbox", "release management", "deployment",
        "configuration management", "source control", "change management",
        "devops", "ci/cd", "pipeline", "version control",
    ],
    "copado": [
        "copado", "release management", "deployment", "devops",
        "source control", "pipeline", "configuration management",
        "environment", "sandbox",
    ],
    "advanced administrator": [
        "environment", "sandbox", "salesforce administration",
        "configuration", "declarative", "release management",
        "deployment",
    ],
    "application architect": [
        "application design", "architecture", "solution design",
        "design and configure", "technical governance",
        "platform strategy", "org or platform", "org strategy", "org assessment",
        "security", "data architecture", "data model",
    ],
    "platform data architect": [
        "data architecture", "data model", "data management",
        "data strategy", "data integration",
        "platform strategy", "org or platform", "org strategy", "architecture",
    ],
    "sharing and visibility architect": [
        "security", "sharing", "visibility", "access",
        "platform strategy", "org or platform", "org strategy", "architecture",
    ],
    "agentforce": [
        "agentforce", "agent", "agentic", "ai consulting",
        "conversation design", "prompt", "ai fluency",
        "action planning",
        "design and configure",
        "build and deploy",
    ],
    "omnistudio": [
        "omnistudio", "vlocity", "industry cloud",
    ],
    "mulesoft": [
        "mulesoft", "integration", "api", "anypoint",
        "integration and api",
    ],
    "integration architect": [
        "integration", "api", "integration and api", "middleware",
        "platform events", "streaming",
    ],
    "identity and access management": [
        "integration and api", "api", "security", "access",
        "identity",
    ],
    "platform administrator": [
        "salesforce administration", "configuration", "declarative",
        "environment", "sandbox",
        "flow",
    ],
    "platform developer": [
        "apex", "lwc", "visualforce", "platform development",
        "code review", "technical governance",
    ],
    "experience cloud": [
        "experience cloud", "community", "portal", "digital experience",
    ],
    "ai associate": [
        "ai fluency", "ai literacy", "artificial intelligence",
        "machine learning", "einstein",
    ],
    "gearset": [
        "gearset", "release management", "deployment", "devops",
    ],
    "git": [
        "git", "source control", "version control", "branching",
    ],
    "data 360": [
        "data cloud", "data 360", "cdp", "data actions",
        "data analysis", "data strategy", "data architecture",
    ],
}

CERT_RECOMMENDATIONS = {
    "data analysis":            ("Cert path by level across three pillars — "
                                 "3-Advanced: Any one of: Salesforce Certified Tableau Data Analyst, "
                                 "Certified CRM Analytics and Einstein Discovery Consultant, or "
                                 "Certified Data Cloud Consultant / Data 360 Consultant. "
                                 "4-Specialist: Any two of the three. "
                                 "5-Expert: All three credentials.",
                                 "Three-pillar cert stack: Tableau (BI), CRM Analytics (predictive), Data Cloud (platform data)."),
    "data cloud":               ("Salesforce Certified Data Cloud Consultant / Data 360 Consultant",
                                 "Covers data ingestion, identity resolution, segmentation, and data actions."),
    "data strategy":            ("Salesforce Certified Data Cloud Consultant / Data 360 Consultant "
                                 "or Certified CRM Analytics and Einstein Discovery Consultant",
                                 "Demonstrates strategic command of enterprise data platforms."),
    "data architecture":        ("Salesforce Certified Platform Data Architect",
                                 "Validates data modeling, large data volumes, and data lifecycle design."),
    "data integration":         ("Salesforce Certified MuleSoft Integration Architect "
                                 "or Certified Platform Data Architect",
                                 "Covers API-led connectivity, data mapping, and integration patterns."),
    "integration and api":      ("3-Advanced: MuleSoft Integration Architect or Integration Architect. "
                                 "4-Specialist: Either Integration Architect credential. "
                                 "5-Expert: Integration Architect + Certified Identity and Access Management Architect.",
                                 "Integration cert for 4-Specialist; Integration + IAM Architect for 5-Expert."),
    "integration":              ("Salesforce Certified Integration Architect "
                                 "or Salesforce Certified MuleSoft Integration Architect",
                                 "Demonstrates enterprise integration design and API management."),
    "api":                      ("Salesforce Certified MuleSoft Integration Architect "
                                 "or Salesforce Certified Integration Architect",
                                 "Validates API-led connectivity strategy and implementation."),
    "configuration management": ("3-Advanced: GitHub Actions certification, GitLab CI/CD Associate, "
                                 "HashiCorp Terraform Associate (004), or AWS DevOps Engineer Professional. "
                                 "4-Specialist: Above + Microsoft DevOps Engineer Expert (AZ-400), "
                                 "Terraform Authoring and Operations Advanced, or Red Hat Ansible Specialist (EX294).",
                                 "GitHub Actions cert or Terraform Associate (004) for 3-Adv; AZ-400 for 4-Spec."),
    "environment":              ("Cert path for Environment/Sandbox Management — "
                                 "Primary (3-Advanced): Salesforce Certified Development Lifecycle and Deployment Architect (PDLDA). "
                                 "Secondary (3-Advanced): Salesforce Certified Advanced Administrator. "
                                 "Supplementary: Copado Fundamentals I or II. "
                                 "What does NOT qualify standalone: Platform Administrator alone. "
                                 "4-Specialist: PDLDA + Advanced Administrator + enterprise-scale governance evidence.",
                                 "PDLDA primary; Advanced Admin secondary; Copado I/II supplementary."),
    "release management":       ("Certified Platform Development Lifecycle and Deployment Architect "
                                 "or Copado Consultant",
                                 "Validates end-to-end release governance and deployment architecture."),
    "deployment":               ("Certified Platform Development Lifecycle and Deployment Architect",
                                 "Covers deployment strategies, change management, and pipeline design."),
    "observability":            ("3-Advanced: Splunk O11y Cloud Certified Metrics User, Dynatrace Certified Associate, "
                                 "Grafana Certified Associate, or New Relic Certified Performance Pro. "
                                 "4-Specialist: Elastic Certified Observability Engineer, Dynatrace Certified Professional, "
                                 "or Splunk Enterprise Certified Architect. No Datadog proctored cert exists.",
                                 "Splunk O11y / Dynatrace Associate for 3-Adv; Elastic Certified Observability Engineer for 4-Spec."),
    "containerization":         ("3-Advanced: CKAD or CKA (CNCF performance-based proctored exams). "
                                 "4-Specialist: CKS (requires active CKA) or Red Hat EX280. "
                                 "Docker DCA discontinued 2023. KCNA is knowledge-based only.",
                                 "CKAD or CKA for 3-Adv; CKS (requires CKA) or Red Hat EX280 for 4-Spec."),
    "security":                 ("Salesforce Certified Sharing and Visibility Architect "
                                 "or Salesforce Security Privacy Accredited Professional",
                                 "Validates platform-level security model, OWD, profiles, permission sets."),
    "architecture":             ("Salesforce Certified Application Architect "
                                 "(System Architect + Domain credentials combined)",
                                 "Validates enterprise architectural judgment across the full platform."),
    "platform strategy":        ("3-Advanced: PDLDA. "
                                 "4-Expert: PDLDA + Platform Data Architect, "
                                 "PDLDA + Sharing and Visibility Architect, "
                                 "or PDLDA + Application Architect.",
                                 "PDLDA is the baseline for 3-Advanced; architectural depth certs are required for 4-Expert."),
    "org or platform":          ("3-Advanced: PDLDA. "
                                 "4-Expert: PDLDA + Platform Data Architect, "
                                 "PDLDA + Sharing and Visibility Architect, "
                                 "or PDLDA + Application Architect.",
                                 "PDLDA is the baseline for 3-Advanced; architectural depth certs are required for 4-Expert."),
    "org assessment":           ("Salesforce Certified Application Architect (requires Platform Data Architect + "
                                 "Sharing and Visibility Architect as components)",
                                 "Includes evaluation of org health, technical debt, and fit-for-purpose design."),
    "business value":           ("No direct Salesforce certification. Consider PMI-PBA or IIBA CBAP.",
                                 "Business value framing is a consulting skill; evidence-based validation applies."),
    "high-traffic":             ("No direct Salesforce certification. "
                                 "Validate via Salesforce Well-Architected review artifacts or load-testing documentation.",
                                 "Large-scale system design is best evidenced through delivery artifacts."),
    "agentforce":               ("Salesforce Certified Agentforce Specialist",
                                 "Covers agent configuration, topics, actions, testing, and delivery patterns."),
    "conversation design":      ("Salesforce Certified Agentforce Specialist",
                                 "Covers topic/instruction design, dialogue flows, and UX for agent interactions."),
    "prompt":                   ("Salesforce Certified Agentforce Specialist",
                                 "Includes Prompt Builder, prompt engineering patterns, and LLM grounding."),
    "retrieval augmented":      ("Salesforce Certified AI Specialist (includes RAG, vector databases, grounding techniques). "
                                 "Also document via customer RAG delivery evidence.",
                                 "RAG expertise is best validated through AI Specialist + delivery portfolio."),
    "ai fluency":               ("Salesforce Certified AI Associate",
                                 "Validates foundational AI/ML concepts, responsible AI, and Salesforce AI features."),
    "ai consulting":            ("Salesforce Certified AI Specialist or Certified Agentforce Specialist",
                                 "Validates ability to translate AI strategy into Salesforce platform delivery."),
    "leadership":               ("No Salesforce certification covers leadership presence. "
                                 "Observable evidence: 360-degree feedback, delivery lead track record, peer/stakeholder testimonials.",
                                 "Leadership is a behavioral competency; evidence-based validation applies."),
    "empathy":                  ("No Salesforce certification. Observable evidence: customer satisfaction scores, 360 feedback.",
                                 "Interpersonal competency; evidence-based validation applies."),
    "communicate":              ("No Salesforce certification. Observable evidence: presentation recordings, workshop facilitation records.",
                                 "Communication is a behavioral competency; evidence-based validation applies."),
    "collaborate":              ("No Salesforce certification. Observable evidence: cross-functional project outcomes, peer recognition.",
                                 "Collaboration is a behavioral competency; evidence-based validation applies."),
    "source control":           ("Foundations of Git - Certified (Copado credential) or GitHub Foundations certification",
                                 "Validates branching strategy, merge patterns, and source-of-truth management."),
}


def _find_cert_recommendation(skill_name: str) -> str:
    norm = normalize(skill_name)
    for keyword, (suggestion, _) in CERT_RECOMMENDATIONS.items():
        if keyword in norm:
            return suggestion
    return ""


CERT_SKILL_EXCLUSIONS = {
    "development lifecycle and deployment": [
        "org or platform", "platform strategy", "org strategy",
        "architecture", "org assessment",
        "integration and api",
    ],
    "shield": [
        "observability",
    ],
    # Agentforce Specialist is intentionally NOT excluded from Data 360/Data Cloud —
    # it is relevant evidence even though it isn't sufficient on its own (the
    # separate Data 360 check adds a note about the missing Data Cloud cert).
}

_KEYWORD_BLOCKLIST = {"platform", "certified", "salesforce", "cloud"}


def cert_corroborates_skill(skill_name: str, cert_list: list) -> tuple:
    norm_skill = normalize(skill_name)
    # Replace non-word/non-space chars with a space so "environment/sandbox"
    # produces ["environment", "sandbox"], not ["environmentsandbox"].
    skill_words = [
        w for w in re.sub(r"[^\w\s]", " ", norm_skill).split()
        if len(w) >= 4
        and w not in _CERT_STOPWORDS
        and w not in _KEYWORD_BLOCKLIST
    ]

    matching_certs: list[str] = []
    for cert_name, _ in cert_list:
        norm_cert = normalize(cert_name)

        excluded = False
        for cert_pattern, excluded_skills in CERT_SKILL_EXCLUSIONS.items():
            if cert_pattern in norm_cert:
                if any(excl in norm_skill for excl in excluded_skills):
                    excluded = True
                    break
        if excluded:
            continue

        matched = (skill_words and any(w in norm_cert for w in skill_words))
        if not matched:
            for cert_pattern, covered_skills in CERT_DOMAIN_MAP.items():
                if cert_pattern in norm_cert:
                    if any(kw in norm_skill for kw in covered_skills):
                        matched = True
                        break
        if matched:
            matching_certs.append(cert_name)

    if matching_certs:
        return True, " | ".join(matching_certs)
    return False, ""


def match(norm_name: str, index: dict):
    if norm_name in index:
        return norm_name, index[norm_name]
    for key, val in index.items():
        if norm_name in key or key in norm_name:
            return key, val
    return None, None


def validate_record(row: dict, catalog: dict, agentforce: dict, devops: dict,
                    certifications: dict, rr_counts=None) -> dict:
    skill_name = row["Skill or Certification"].strip()
    norm        = normalize(skill_name)
    employee    = row["Resource"].strip()
    rating_str  = row["Rating"].strip()
    rating      = rating_int(rating_str)
    emp_grade   = EMPLOYEE_GRADES.get(employee, "")
    emp_certs   = certifications.get(employee, [])

    has_cert, supporting_cert = cert_corroborates_skill(skill_name, emp_certs)

    result = {
        **row,
        "Employee Grade":          emp_grade,
        "In PSA Catalog":          "",
        "Catalog Category":        "",
        "Catalog Type":            "",
        "Catalog Description":     "",
        "Is Agentforce Required":  "No",
        "AF Min Rating Required":  "",
        "AF Rating Met":           "",
        "AF Feedback":             "",
        "AF Level Definition":     "",
        "Is DevOps Skill":         "No",
        "DevOps Skill Category":   "",
        "DevOps Grade Requirements": "",
        "Grade Floor Met":         "",
        "Supporting Cert":         supporting_cert,
        "Cert Corroborates Skill": "Yes" if has_cert else "No",
        "AF Delivery RRs":         "",
        "AF Ready Skill":          "",
        "AF Enabled":              "",
        "Validation Status":       "OK",
        "Validation Notes":        "",
        "Suggested Cert Path":     "",
    }

    notes = []

    _, cat_entry = match(norm, catalog)
    if cat_entry:
        result["In PSA Catalog"]      = "Yes"
        result["Catalog Category"]    = cat_entry["catalog_category"]
        result["Catalog Type"]        = cat_entry["catalog_type"]
        result["Catalog Description"] = cat_entry["catalog_description"]
    else:
        result["In PSA Catalog"] = "No"
        notes.append("Skill not found in PSA catalog — verify skill name is correct.")

    _, af_entry = match(norm, agentforce)
    if af_entry:
        if _is_af_ready_skill(skill_name):
            result["AF Ready Skill"] = "Yes (1 of 17)"
        elif _is_af_expert_only_skill(skill_name):
            result["AF Ready Skill"] = "Expert Only"
        else:
            result["AF Ready Skill"] = "Yes (1 of 17)"

        is_enabled = employee in AF_ENABLED_EMPLOYEES
        result["AF Enabled"] = "Yes" if is_enabled else "No"
        if not is_enabled and rating >= 4:
            # 4-Expert on an AF skill requires AF Enabled — Change Required.
            # Expert-level mastery of the AF stack presupposes the Data Cloud
            # credential and superbadges that define foundational enablement.
            notes.append(
                f"AGENTFORCE: 4-Expert rating on '{skill_name}' requires AF Enabled status. "
                f"{employee} has not completed AF Enabled requirements (Agentforce Champion, "
                f"Innovator, and Legend Trailhead superbadges + Salesforce Certified Data Cloud "
                f"/ Data 360 Consultant cert). AF Enabled is a prerequisite for expert-level "
                f"Agentforce skill claims."
            )
        elif not is_enabled and rating == 3:
            # 3-Advanced is the path toward AF Ready — informational only.
            notes.append(
                f"AF NOT ENABLED: {employee} has not completed AF Enabled requirements "
                f"(Agentforce Champion, Innovator, and Legend Trailhead superbadges + "
                f"Salesforce Certified Data Cloud / Data 360 Consultant cert). "
                f"AF skill ratings cannot count toward Agentforce Ready status until "
                f"enablement is complete."
            )

    if af_entry:
        min_req = af_entry["af_min_rating"]
        result["Is Agentforce Required"] = "Yes"
        result["AF Min Rating Required"] = f"{min_req}+"

        claimed_level = max(rating, min_req)
        if claimed_level >= 4 and af_entry.get("af_criteria_4"):
            level_label = "4-Specialist"
            level_criteria = af_entry["af_criteria_4"]
        else:
            level_label = "3-Advanced (minimum required)"
            level_criteria = af_entry.get("af_criteria_3", "")
        if level_criteria:
            result["AF Level Definition"] = (
                f"{af_entry['af_skill_name']} — {level_label}:\n{level_criteria}"
            )

        if rating >= min_req:
            result["AF Rating Met"] = "Yes"
        else:
            result["AF Rating Met"] = "No"
            criteria_3 = af_entry.get("af_criteria_3", "")
            feedback = (
                f"Agentforce Ready requires a minimum rating of {min_req}-Advanced. "
                f"Current rating: {rating_str or 'Not rated'}."
            )
            if criteria_3:
                sentences = [s.strip() for s in criteria_3.replace("\n", " ").split(".") if s.strip()]
                feedback += f" 3-Advanced criteria: {'. '.join(sentences[:2])}."
            result["AF Feedback"] = feedback
            notes.append(f"AGENTFORCE: Rating below minimum. {feedback}")

    af_catalog_name = af_entry.get("af_skill_name", "") if af_entry else ""
    if af_entry and rating >= 3 and _is_af_delivery_skill(skill_name, af_catalog_name):
        level_label  = rating_str or f"{rating}-Advanced"
        has_af_cert  = _has_agentforce_specialist_cert(emp_certs)
        issues: list[str] = []

        if not has_af_cert:
            issues.append("Agentforce Specialist certification not on file")

        if rr_counts is not None:
            rr_count  = rr_counts.get(employee, 0)
            rr_needed = 4 if rating >= 4 else 2
            result["AF Delivery RRs"] = str(rr_count)
            if rr_count < rr_needed:
                issues.append(
                    f"{rr_count} qualifying Agentforce RR(s) on file "
                    f"(post Oct 2024, ≥90 days, Assigned/Closed/In Progress) — "
                    f"need {rr_needed}+ for a {level_label} delivery claim"
                )

        if issues:
            notes.append(
                f"AGENTFORCE: Delivery evidence insufficient — "
                + "; ".join(issues) + "."
            )

    if ("data 360" in norm or "data cloud" in norm) and rating >= 3:
        has_data_cloud_cert = any(
            "data 360" in normalize(c[0]) or "data cloud" in normalize(c[0])
            for c in emp_certs
        )
        if not has_data_cloud_cert:
            notes.append(
                "AGENTFORCE: Data 360 / Data Cloud for Agentforce at 3-Advanced requires the "
                "Salesforce Certified Data 360 / Data Cloud Consultant cert — Agentforce Specialist "
                "alone does not validate Data Cloud data ingestion, identity resolution, or "
                "segmentation capabilities. No Data Cloud cert on file."
            )
            result["Suggested Cert Path"] = (
                "Salesforce Certified Data Cloud Consultant / Data 360 Consultant "
                "(covers data ingestion, identity resolution, segmentation, and data actions). "
                "Agentforce Specialist alone is not sufficient for this skill."
            )

    if (af_entry and rating >= 3
            and not _is_af_tier2_skill(skill_name)
            and not _is_af_delivery_skill(skill_name, af_catalog_name)
            and "data 360" not in norm and "data cloud" not in norm):
        if not _has_agentforce_specialist_cert(emp_certs):
            notes.append(
                f"AGENTFORCE: Tier 1 Agentforce skill rated {rating_str} without the "
                f"Agentforce Specialist certification. The Agentforce Specialist cert is "
                f"required at 3-Advanced for Tier 1 AF skills — it is the vendor-endorsed "
                f"signal that the employee has foundational knowledge of agent configuration, "
                f"topics, actions, prompts, and deployment. Without it, this is an unvalidated "
                f"self-assertion. Cert path: Salesforce Certified Agentforce Specialist."
            )

    if af_entry and _is_af_tier2_skill(skill_name):
        tier2_ceiling = _TIER2_GRADE_CEILING.get(emp_grade, 3)
        if rating > tier2_ceiling:
            notes.append(
                f"TIER2: '{skill_name}' rated {rating_str} exceeds the grade ceiling for "
                f"{emp_grade or 'unknown grade'}. Professional competency skills (Business "
                f"Acumen, AI Consulting, Executive Alignment, Agility) require Grade 7+ for a "
                f"4-Specialist claim — this level requires a demonstrated executive advisory "
                f"track record, not just delivery participation. Grade ceiling for {emp_grade}: "
                f"{tier2_ceiling}+. Evidence should come from bio, client scope, and tenure."
            )

    _, dv_entry = match(norm, devops)
    if dv_entry:
        result["Is DevOps Skill"] = "Yes"
        result["DevOps Skill Category"] = dv_entry.get("devops_category", "")
        grade_reqs = dv_entry["devops_grade_reqs"]
        grade_summary = "; ".join(
            f"{grade} ({DEVOPS_TITLES[i]}): {req}+"
            for i, (grade, req) in enumerate(grade_reqs.items())
        )
        result["DevOps Grade Requirements"] = grade_summary

        check_grade = emp_grade if emp_grade in grade_reqs else "Grade 4"
        grade_min   = grade_reqs.get(check_grade, grade_reqs.get("Grade 4", 1))
        if rating >= grade_min:
            result["Grade Floor Met"] = "Yes"
        else:
            result["Grade Floor Met"] = "No"
            if check_grade in DEVOPS_GRADES:
                title = DEVOPS_TITLES[DEVOPS_GRADES.index(check_grade)]
                grade_label = f"{check_grade} ({title})"
            else:
                grade_label = check_grade
            notes.append(
                f"DEVOPS: Rating {rating_str} is below the {grade_label} minimum of {grade_min}+. "
                f"Full requirements: {grade_summary}"
            )

    for jus_key, jus_message in _JUSTIFICATION_REQUIRED_SKILLS.items():
        if jus_key in norm or norm in jus_key:
            if rating >= 3:
                notes.append(f"JUSTIFICATION REQUIRED: {jus_message}")
            break

    if rating >= 4 and not has_cert and emp_certs:
        cert_suggestion = _find_cert_recommendation(skill_name)
        result["Suggested Cert Path"] = cert_suggestion
        notes.append(
            f"CERT: Self-rated {rating_str} but no certification corroborates this skill. "
            f"Consider requesting observable evidence or portfolio examples."
        )

    if notes:
        result["Validation Status"] = "NEEDS REVIEW"
        result["Validation Notes"]  = " | ".join(notes)

    return result


def write_detail(records: list, path: Path):
    if not records:
        return
    fieldnames = list(records[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"  Detail report:  {path}")


def write_summary(records: list, path: Path, certifications: dict):
    by_employee = defaultdict(lambda: {
        "total": 0, "ok": 0, "needs_review": 0, "issues": [],
        "cert_corroborated": 0, "grade": "",
    })

    for r in records:
        emp = r["Resource"]
        by_employee[emp]["total"] += 1
        by_employee[emp]["grade"] = r.get("Employee Grade", "")
        if r["Validation Status"] == "OK":
            by_employee[emp]["ok"] += 1
        else:
            by_employee[emp]["needs_review"] += 1
            by_employee[emp]["issues"].append(r["Skill or Certification"])
        if r.get("Cert Corroborates Skill") == "Yes":
            by_employee[emp]["cert_corroborated"] += 1

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "Resource", "Grade", "Total Skills", "Passed", "Needs Review",
            "Cert-Corroborated Skills", "Total Certs on File", "Skills Needing Review"
        ])
        writer.writeheader()
        for emp, data in sorted(by_employee.items()):
            writer.writerow({
                "Resource":                emp,
                "Grade":                   data["grade"],
                "Total Skills":            data["total"],
                "Passed":                  data["ok"],
                "Needs Review":            data["needs_review"],
                "Cert-Corroborated Skills": data["cert_corroborated"],
                "Total Certs on File":     len(certifications.get(emp, [])),
                "Skills Needing Review":   "; ".join(data["issues"]),
            })
    print(f"  Summary report: {path}")


def write_feedback(records: list, path: Path, certifications: dict):
    by_employee = defaultdict(list)
    for r in records:
        if r["Validation Status"] != "OK":
            by_employee[r["Resource"]].append(r)

    all_employees = sorted({r["Resource"] for r in records})

    with open(path, "w", encoding="utf-8") as f:
        f.write("SKILL & CERTIFICATION RATING VALIDATION FEEDBACK\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        for emp in all_employees:
            issues = by_employee.get(emp, [])
            emp_grade = EMPLOYEE_GRADES.get(emp, "Unknown")
            emp_cert_list = certifications.get(emp, [])
            all_emp_records = [r for r in records if r["Resource"] == emp]

            f.write(f"EMPLOYEE: {emp}  |  Grade: {emp_grade}\n")
            f.write(f"Total skill ratings: {len(all_emp_records)}  |  "
                    f"Needs review: {len(issues)}  |  "
                    f"Certifications on file: {len(emp_cert_list)}\n")

            if emp_cert_list:
                f.write("Certifications:\n")
                for cert_name, earned in emp_cert_list:
                    date_str = f" (earned {earned})" if earned else ""
                    f.write(f"  ✓ {cert_name}{date_str}\n")

            if not issues:
                f.write("→ All skill ratings passed validation.\n")
            else:
                f.write(f"\nSkills requiring attention ({len(issues)}):\n")
                f.write("-" * 60 + "\n")
                for r in issues:
                    cert_status = (f"  Supporting cert: {r['Supporting Cert']}"
                                   if r.get("Supporting Cert") else "  No corroborating cert on file")
                    f.write(f"\n  Skill: {r['Skill or Certification']}\n")
                    f.write(f"  Self-rated: {r['Rating']} | Evaluation Date: {r['Evaluation Date']}\n")
                    f.write(f"{cert_status}\n")
                    for note in r["Validation Notes"].split(" | "):
                        f.write(f"  → {note}\n")

            f.write("\n" + "=" * 80 + "\n\n")

    print(f"  Feedback report:{path}")


def main():
    global EMPLOYEE_GRADES, AF_ENABLED_EMPLOYEES

    parser = argparse.ArgumentParser(description="Validate skill ratings against benchmarking criteria.")
    parser.add_argument("--ratings", type=Path, default=None,
                        help="Path to the scraped skill_certification_ratings CSV")
    parser.add_argument("--roster", type=Path, default=None,
                        help="Path to team_roster.csv from the scraper (overrides auto-discovery)")
    args = parser.parse_args()

    EMPLOYEE_GRADES = load_employee_grades(args.roster)
    AF_ENABLED_EMPLOYEES = load_af_enabled(args.roster)

    ratings_file = args.ratings or find_most_recent_ratings()

    print(f"\nLoading data...")
    print(f"  Ratings:      {ratings_file.name}")
    print(f"  Catalog:      {CATALOG_FILE.name}")
    print(f"  Agentforce:   {AGENTFORCE_FILE.name}")
    print(f"  DevOps:       {DEVOPS_FILE.name}")
    rr_status = (RR_FILE.name if RR_FILE.exists()
                 else f"{RR_FILE.name} (not found — run scrape_agentforce_resource_requests.py)")
    print(f"  Certs:        {CERT_FILE.name}")
    print(f"  RR data:      {rr_status}\n")

    with open(ratings_file, encoding="utf-8-sig") as f:
        employee_ratings = list(csv.DictReader(f))

    catalog        = load_catalog(CATALOG_FILE)
    agentforce     = load_agentforce(AGENTFORCE_FILE)
    devops         = load_devops_guide(DEVOPS_FILE)
    certifications = load_certifications(CERT_FILE)
    rr_counts      = load_agentforce_rrs(RR_FILE)

    print(f"Loaded {sum(len(v) for v in certifications.values())} certifications "
          f"across {len(certifications)} employees.")
    if rr_counts is not None:
        total_q = sum(rr_counts.values())
        print(f"Loaded Agentforce RR data: {total_q} qualifying RRs across "
              f"{len(rr_counts)} employee(s).")
    else:
        print("Agentforce RR data not loaded — delivery evidence checks will be skipped.")
    print()

    print(f"Validating {len(employee_ratings)} employee ratings...\n")
    validated = [validate_record(r, catalog, agentforce, devops, certifications,
                                 rr_counts=rr_counts)
                 for r in employee_ratings]

    needs_review = sum(1 for r in validated if r["Validation Status"] == "NEEDS REVIEW")
    print(f"Results: {len(validated) - needs_review} passed | {needs_review} need review\n")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    write_detail(validated,  DOWNLOADS / f"skill_validation_detail_{ts}.csv")
    write_summary(validated, DOWNLOADS / f"skill_validation_summary_{ts}.csv", certifications)
    write_feedback(validated, DOWNLOADS / f"skill_validation_feedback_{ts}.txt", certifications)
    print("\nDone.")


if __name__ == "__main__":  # pragma: no cover
    main()
