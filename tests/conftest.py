"""Shared fixtures for skill-rating-evaluation tests."""
import pytest


# ---------------------------------------------------------------------------
# Minimal catalog fixture (keyed by normalized skill name)
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_catalog():
    return {
        "environment/sandbox management": {
            "catalog_name":        "Environment/Sandbox Management",
            "catalog_id":          "SKL-001",
            "catalog_description": "Managing sandbox orgs and environment strategies",
            "catalog_type":        "Technical",
            "catalog_category":    "DevOps",
            "catalog_parent_cat":  "Delivery",
        },
        "agentforce operations": {
            "catalog_name":        "Agentforce Operations",
            "catalog_id":          "SKL-002",
            "catalog_description": "Operating Agentforce agents in production",
            "catalog_type":        "Technical",
            "catalog_category":    "Agentforce",
            "catalog_parent_cat":  "AI",
        },
        "business acumen": {
            "catalog_name":        "Business Acumen",
            "catalog_id":          "SKL-003",
            "catalog_description": "Understanding business context and value drivers",
            "catalog_type":        "Professional",
            "catalog_category":    "Consulting",
            "catalog_parent_cat":  "Professional Skills",
        },
        "data 360 (aka: data cloud) for agentforce": {
            "catalog_name":        "Data 360 (aka: Data Cloud) for Agentforce",
            "catalog_id":          "SKL-004",
            "catalog_description": "Data Cloud / Data 360 for Agentforce use cases",
            "catalog_type":        "Technical",
            "catalog_category":    "Agentforce",
            "catalog_parent_cat":  "AI",
        },
        "agentforce testing": {
            "catalog_name":        "Agentforce Testing",
            "catalog_id":          "SKL-005",
            "catalog_description": "Testing Agentforce agents",
            "catalog_type":        "Technical",
            "catalog_category":    "Agentforce",
            "catalog_parent_cat":  "AI",
        },
        "org or platform strategy": {
            "catalog_name":        "Org or Platform Strategy",
            "catalog_id":          "SKL-006",
            "catalog_description": "Org-level strategy and architecture",
            "catalog_type":        "Technical",
            "catalog_category":    "Architecture",
            "catalog_parent_cat":  "Delivery",
        },
    }


# ---------------------------------------------------------------------------
# Minimal Agentforce fixture (keyed by normalized skill name)
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_agentforce():
    return {
        "agentforce operations": {
            "af_skill_name":  "Agentforce Operations",
            "af_definition":  "Build and operate Agentforce agents.",
            "af_criteria_3":  "Can configure and deploy Agentforce agents independently.",
            "af_criteria_4":  "Designs multi-agent orchestration patterns.",
            "af_criteria_5":  "",
            "af_min_rating":  3,
        },
        "business acumen": {
            "af_skill_name":  "Business Acumen",
            "af_definition":  "Demonstrates business judgment.",
            "af_criteria_3":  "Connects delivery to business outcomes.",
            "af_criteria_4":  "Executive-level advisory track record.",
            "af_criteria_5":  "",
            "af_min_rating":  3,
        },
        "data 360 (aka: data cloud) for agentforce": {
            "af_skill_name":  "Data 360 (aka: Data Cloud) for Agentforce",
            "af_definition":  "Data Cloud capabilities for Agentforce.",
            "af_criteria_3":  "Can implement Data Cloud ingestion pipelines.",
            "af_criteria_4":  "Architects full Data Cloud solutions.",
            "af_criteria_5":  "",
            "af_min_rating":  3,
        },
        "agentforce testing": {
            "af_skill_name":  "Agentforce Testing",
            "af_definition":  "Testing and QA for Agentforce agents.",
            "af_criteria_3":  "Can write test plans and validate agent behavior.",
            "af_criteria_4":  "Designs automated testing pipelines for agents.",
            "af_criteria_5":  "",
            "af_min_rating":  3,
        },
    }


# ---------------------------------------------------------------------------
# Minimal DevOps fixture (keyed by normalized skill name)
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_devops():
    return {
        "environment/sandbox management": {
            "devops_skill_name":  "Environment/Sandbox Management",
            "devops_category":    "DevOps",
            "devops_description": "Sandbox strategy and environment management",
            "devops_grade_reqs":  {
                "Grade 4": 1,
                "Grade 5": 2,
                "Grade 6": 2,
                "Grade 7": 3,
                "Grade 8": 3,
                "Grade 9": 4,
                "Grade 11": 4,
            },
        },
    }


# ---------------------------------------------------------------------------
# Certification fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def certs_with_af_specialist():
    """Employee has Agentforce Specialist cert."""
    return {
        "Alice Test": [
            ("Certified Agentforce Specialist", "2024-12-01"),
            ("Certified Platform Administrator", "2023-10-31"),
        ],
    }


@pytest.fixture
def certs_without_af_specialist():
    """Employee has certs but NOT Agentforce Specialist."""
    return {
        "Bob Test": [
            ("Certified Platform Administrator", "2023-10-31"),
            ("Certified Platform Development Lifecycle and Deployment Architect", "2024-01-29"),
        ],
    }


@pytest.fixture
def certs_empty():
    return {}


@pytest.fixture
def certs_with_data_cloud():
    return {
        "Carol Test": [
            ("Salesforce Certified Data Cloud Consultant", "2024-06-15"),
            ("Certified Agentforce Specialist", "2024-12-01"),
        ],
    }
