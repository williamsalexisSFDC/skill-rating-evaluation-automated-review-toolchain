# FY26 Skill Rating Evaluation — Automated Review Toolchain

**Author:** Alexis Williams, Senior Manager Technical Consulting
**Scope:** Direct report team (5 ICs, Grades 5–7)
**Cycle:** FY26 Annual Skill & Certification Rating Review
**Last updated:** 2026-09-18 — Iteration 4: Environment/Sandbox Management cert hierarchy implemented (PDLDA primary, Advanced Admin secondary, Copado I/II supplementary); CERT_DOMAIN_MAP expanded to recognize Copado and Advanced Admin as corroborating certs for this skill; justification gate added at 3-Advanced.

---

## Problem Statement

Salesforce Professional Services uses an org62-based PSA (Professional Services Automation) system in which individual contributors self-rate their skills and certifications across a catalog of approximately 30–50 skills per employee. Submissions flow to a single manager as the point of review and final approval authority.

At full team scale, a manager may receive **up to or exceeding 150 individual skill records** in a single review cycle. Each record nominally requires the manager to:

1. Verify the claimed rating against the employee's grade-level floor (is the rating achievable at this grade?)
2. Verify alignment with Agentforce readiness standards where the skill is Agentforce-designated
3. Corroborate any 4-Specialist claim against certification evidence
4. Cross-reference delivery-type Agentforce claims against real customer engagement history
5. Reconcile discrepancies, draft coaching notes, schedule conversations, and record final decisions

Performed manually — record by record, across multiple org62 views and spreadsheet exports — this process is labor-intensive, inconsistently applied, and entirely dependent on the reviewing manager's recall of the standard for each skill. There is no built-in mechanism to enforce consistency between the criteria a manager applies to one employee versus another, nor any audit trail connecting validation reasoning to the final disposition.

This toolchain automates the labor-intensive phases of the review while adding methodological rigor that the manual process cannot reliably deliver.

---

## Solution Overview

The toolchain automates the three most labor-intensive phases of the review:

| Phase | Manual Effort Replaced | Tool |
|---|---|---|
| Data extraction | Navigating org62 RR records per employee (15–30 min/person) | `scrape_agentforce_resource_requests.py` via MCP Playwright |
| Validation | Reviewing 148+ records against 6 distinct rule sets | `validate_skill_ratings.py` |
| Artifact generation | Building review spreadsheets, per-person tabs, manager tracker | `generate_review_artifacts.py` |

**Estimated time savings:** Manual review at ~3–5 minutes per record across 150 records = 7–12 hours. Toolchain runtime = under 15 minutes including browser scraping.

---

## The Three-Tier Evaluation Framework

All Agentforce-designated skills in the PSA catalog are evaluated against one of three tiers based on the nature of the skill. The tier determines what evidence is required to support a 3-Advanced or higher claim.

### Tier 1 — Certification Gate

Applies to Agentforce-specific configuration and knowledge skills: Prompt Engineering, Prompt Builder, Design and Configure Solutions, Action Planning, Agentforce Security, Agentforce Troubleshooting, Agentforce Builder, Agentforce API, Build and Deploy Technical Capabilities, Development Lifecycle Frameworks, Flow.

**Required evidence at 3-Advanced:** The **Salesforce Certified Agentforce Specialist** certification. This cert validates foundational knowledge of agent architecture, topic and instruction design, action orchestration, Prompt Builder, and agent deployment. It is the vendor-endorsed minimum standard for claiming 3-Advanced on any Tier 1 AF skill.

**Exception — Data 360 for Agentforce:** This skill requires the **Salesforce Certified Data 360 / Data Cloud Consultant** certification specifically. The Agentforce Specialist cert does NOT cover Data Cloud data ingestion, identity resolution, or segmentation capabilities. Having the Agentforce Specialist cert alone is insufficient for a 3-Advanced claim on this skill.

**General technical Tier 1 skills** (Build and Deploy, Development Lifecycle Frameworks, Flow) also accept relevant platform certs as corroborating evidence (PDLDA, Copado Consultant, Platform Administrator). The Agentforce Specialist cert additionally corroborates Build and Deploy and Design and Configure in the Agentforce delivery context.

**AF Enabled status:** "AF Enabled" is a designation from the Salesforce Agentforce Readiness Definition. It requires completing the Agentforce Champion, Agentforce Innovator, and Agentforce Legend Trailhead superbadges AND earning the Salesforce Certified Data Cloud / Data 360 Consultant certification. AF Enabled is the prerequisite before any skill ratings can count toward "Agentforce Ready." Current team status (sourced from the org62 Readiness Summary dashboard):

| Employee | Agentforce Specialist | Data Cloud / Data 360 | AF Enabled |
|---|---|---|---|
| Ramandeep Kaur | Yes (Dec 2024) | Yes (Mar 2026) | **Yes — Enabled, Not Ready** |
| Craig Scott | Yes (Dec 2025) | No | No |
| Jordan Tetzel | Yes (Apr 2025) | No | No |
| Justin Powall | Yes (May 2026) | No | No |
| Keith Johnson | No | No | No |

This status is stored in `team_roster.csv` (see [Input Files — team_roster.csv](#team_rostercsv)) and used by the validation script to distinguish between employees who can progress toward Agentforce Ready and those who must complete enablement requirements first.

"AF Enabled but Not Ready" means the employee has completed the required enablement but has not yet accumulated the qualifying Resource Requests or reached 3+ across all 17 key skills required for the Agentforce Ready designation.

**Agentforce Readiness Levels (Salesforce Agentforce Readiness Definition):**

| Level | Prerequisites |
|---|---|
| **AF Enabled** | Agentforce Champion + Innovator + Legend Trailhead superbadges AND Salesforce Certified Data Cloud / Data 360 Consultant cert |
| **AF Ready** | AF Enabled + **3+ on all 17 key skills** + at least 1 qualifying Agentforce Resource Request (post-Oct 2024, ≥90 days, active status) |
| **AF Expert** | AF Ready + 2+ complex Agentforce projects + 4+ on ≥80% of the 17 skills + 3+ on all 4 advanced Expert-only skills |

**The 17 Agentforce Ready Key Skills** (all must be rated 3+ for AF Ready):

| # | Skill | Validation Tier |
|---|---|---|
| 1 | Build and Deploy Technical Capabilities | Tier 1 — Cert gate (Agentforce Specialist) |
| 2 | Development Lifecycle Frameworks | Tier 1 — Cert gate (Agentforce Specialist) |
| 3 | Retrieval Augmented Generation | Tier 3 — Delivery evidence (cert + 2+ RRs) |
| 4 | Design and Configure Solutions | Tier 1 — Cert gate (Agentforce Specialist) |
| 5 | Conversation Design | Tier 3 — Delivery evidence (cert + 2+ RRs) |
| 6 | Prompt Engineering | Tier 1 — Cert gate (Agentforce Specialist) |
| 7 | Prompt Builder | Tier 1 — Cert gate (Agentforce Specialist) |
| 8 | Agentforce Delivery | Tier 3 — Delivery evidence (cert + 2+ RRs) |
| 9 | Agentforce Testing | Tier 3 — Delivery evidence (cert + 2+ RRs) |
| 10 | Data 360 (aka: Data Cloud) for Agentforce | Tier 1 — Cert gate (**Data Cloud cert**, not Agentforce Specialist) |
| 11 | Flow | Tier 1 — Cert gate (Agentforce Specialist or platform cert) |
| 12 | AI Consulting | Tier 2 — Grade ceiling |
| 13 | Action Planning | Tier 1 — Cert gate (Agentforce Specialist) |
| 14 | Demonstrate Business Acumen | Tier 2 — Grade ceiling |
| 15 | Executive Alignment | Tier 2 — Grade ceiling |
| 16 | Agility | Tier 2 — Grade ceiling |
| 17 | Agentforce Security | Tier 1 — Cert gate (Agentforce Specialist) |

**4 Expert-only Advanced Skills** (needed at 3+ for AF Expert, not counted in the 17):

| Skill | Validation Tier |
|---|---|
| Agent Performance Tracking and Optimization | Tier 3 — Delivery evidence |
| Agentforce Troubleshooting | Tier 1 — Cert gate |
| AI Ecosystem and Frameworks | Tier 3 — Delivery evidence |
| Agentic Delivery | Tier 3 — Delivery evidence |

### Tier 2 — Grade / Tenure Gate

Applies to professional competency skills: **Demonstrate Business Acumen**, **AI Consulting**, **Executive Alignment**, **Agility**.

These skills reflect organizational seniority and client-facing advisory depth — capabilities that are not measurable by certification alone and for which Resource Request history is NOT valid evidence. The evaluation standard is grade level, bio/about me context, and client engagement history.

**Grade ceiling rules:**

| Grade | Max Supportable Rating | Rationale |
|---|---|---|
| Grade 4 | 2-Intermediate | Associate level — early commercial exposure |
| Grade 5 | 3-Advanced | Consultant — demonstrates acumen, not yet architecting client strategy |
| Grade 6 | 3-Advanced | Senior Consultant — breadth of delivery, not yet executive advisory |
| Grade 7 | 4-Specialist | Architect — direct executive-level client advisory track record required |
| Grade 8+ | 4-Specialist / 5-Expert | Senior Architect, Director, VP |

**About Me / Bio as evidence:** Each employee has an `aboutMeText` field on their org62 User profile (1000 character textarea) and an enterprise bio used in RR submissions. These are the authoritative sources for bio-based Tier 2 evidence. The manager should review these alongside the grade ceiling during 1:1 discussions for any Tier 2 skill rated at or near the grade ceiling. Key evidence to look for: client industry/type (commercial enterprise vs. public sector), scope of advisory engagement (executive sponsors, ARB presence, business case authorship), team leadership, and tenure.

**Critical:** RRs are explicitly not valid evidence for Tier 2 skills. Being staffed on an Agentforce delivery engagement does not demonstrate Business Acumen, AI Consulting depth, Executive Alignment capability, or Agility — these are cross-functional competencies evaluated against the employee's total professional profile.

### Tier 3 — Delivery Evidence Gate

Applies to Agentforce delivery execution skills: **Agentforce Delivery**, **Agentforce Testing**, **Conversation Design**, **Agent Performance Tracking**, **AI Ecosystem and Frameworks**, **Retrieval Augmented Generation**, **Agentforce Field Service**.

**Required evidence at 3-Advanced:** BOTH of the following must be on file:

1. **Agentforce Specialist certification** (cert gate — same as Tier 1)
2. **Qualifying Resource Requests** from the PSA system:
   - Primary Skill on the RR contains "agentforce" (case-insensitive)
   - Start date on or after **October 1, 2024** (Agentforce General Availability date)
   - Status: Assigned, In Progress, Closed, or Complete
   - Duration ≥ **90 days**

| Rating Level | Agentforce Specialist Cert | Qualifying RRs Required |
|---|---|---|
| 3-Advanced | Required | ≥ 2 |
| 4-Specialist | Required | ≥ 4 |

**Why 2 RRs for 3-Advanced:** Two qualifying engagements establishes a pattern — the employee has delivered in more than one customer context, ruling out a single outlier. Four for 4-Specialist reflects the mastery expectation: repeated, sustained delivery across diverse use cases sufficient to lead and guide others.

**Why 90 days minimum:** 90 days represents the lower bound of a Phase 1+ implementation engagement at which an engineer has moved past initial setup and into iterative delivery, testing, and customer feedback cycles. It also admits Phase 0 / new-logo pursuits (8–12 weeks scoping) where the resource carries the full technical posture of the Agentforce recommendation.

**Duration calculation for active assignments:** For RRs with status Assigned or In Progress, duration is calculated from Start Date to the current date — a scheduled End Date is a planning artifact, not evidence of conclusion. Active assignments accrue credit continuously.

---

## Toolchain Components

### `scrape_skill_ratings.py`

Uses **MCP Playwright** (browser automation) to authenticate into org62 via Okta SSO and scrape the Mass Approve Skills and Certifications page (`/lightning/n/Mass_Approve_Skills_and_Certification`). Extracts all submitted skill rating records pending manager review.

Output: `skill_certification_ratings_<timestamp>.csv`

### `scrape_agentforce_resource_requests.py`

Navigates each direct report's PSA Resource Request (`pse__Resource_Request__c`) related list. Implements a two-pass strategy:

- **Pass 1 (list view):** Extracts RR metadata — name, status, start date — without visiting individual records
- **Pass 2 (record visit):** Visits only post-October 2024 records with active statuses to retrieve the `pse__Primary_Skill_or_Certification__c` field value

Output: `agentforce_resource_requests.csv`

**Why Playwright + MCP?** Salesforce Lightning Experience renders all UI inside Lightning Web Components using Shadow DOM. Standard DOM queries (`document.querySelectorAll`) do not pierce shadow roots. Playwright's accessibility-tree-based locators traverse the accessibility tree and work correctly with Lightning's component model. The MCP integration exposes the live browser session to the Claude reasoning agent, enabling real-time selector debugging.

### `validate_skill_ratings.py`

Applies six rule sets to each of the 148+ skill rating records, implementing the full 3-tier framework:

1. **PSA Catalog check** — verifies the skill name exists in the current PSA Skills and Certifications catalog
2. **Agentforce minimum check** — verifies rating ≥ 3-Advanced on all Agentforce-designated skills
3. **Tier 1 cert gate at 3-Advanced** — for non-Tier-2, non-delivery AF skills at 3+, verifies Agentforce Specialist cert is on file
4. **Data 360 cert gate** — specifically for Data 360 / Data Cloud skills at 3+, verifies Data Cloud Consultant cert (Agentforce Specialist alone does not qualify)
5. **Tier 2 grade ceiling** — for professional competency skills, verifies rating does not exceed the grade-based ceiling (Grade 5–6: max 3-Advanced; Grade 7+: 4-Specialist)
6. **Tier 3 delivery evidence** — for delivery-type AF skills at 3+, verifies Agentforce Specialist cert AND qualifying RRs (≥2 for 3-Adv, ≥4 for 4-Spec)
7. **Grade floor check** — verifies rating meets the DevOps Leveling Guide minimum for the employee's grade
8. **Justification-required skills** — flags Observability, Configuration Management, Containerization, and Environment/Sandbox Management at 3+; each has a distinct qualification bar where surface-level exposure is commonly conflated with hands-on implementation depth
9. **4-Specialist cert corroboration** — flags any 4-Specialist claim without any corroborating cert on file

### `generate_review_artifacts.py`

Produces a single XLSX workbook with:

- **Overview tab** — team summary with per-employee flag counts and key issues
- **Manager Tracker tab** — all 148 records, pre-disposition (Approve / Discuss / Change Required), discussion notes column, and a cross-tab VLOOKUP that automatically pulls the employee's proposed change into the manager's decision view
- **Per-employee tabs** — flagged rows highlighted red/yellow with full criteria, cert evidence, and a "Proposed Change" dropdown; conditional formatting turns a row green once a proposed change is entered

**Pre-disposition logic:**
- **Change Required** (red): AGENTFORCE:, DEVOPS:, or TIER2: flag present → rating is structurally unsupported
- **Discuss** (yellow): CERT: or catalog flag only → low-stakes, manager judgment call
- **Approve** (green): no flags

---

## Input Files

| File | Source | Purpose |
|---|---|---|
| `team_roster.csv` | Maintained manually — see [team_roster.csv](#team_rostercsv) below | Employee grades and AF Enabled status |
| `skill_certification_ratings*.csv` | org62 Mass Approve page (scraped) | Employee self-ratings (148 submitted records) |
| `PSA Skills and Certifications Report-*.csv` | org62 PSA catalog export | Authoritative skill name list |
| `Agentforce Ready and Expert Skills Ratings - Sheet1.csv` | Internal Agentforce readiness framework | Minimum ratings, level criteria, skill classification |
| `Leveling Guides - DevOps .csv` | DevOps practice leveling guide | Grade-floor requirements per skill per grade |
| `employee_certifications.csv` | org62 certification records (verified) | Cert evidence for corroboration checks |
| `agentforce_resource_requests.csv` | Generated by `scrape_agentforce_resource_requests.py` | Qualifying Agentforce delivery RRs per employee |
| Employee `aboutMeText` / enterprise bio | org62 User profile, Google Slides bio deck | Tier 2 supplementary evidence (grade + bio reviewed in 1:1) |

### team_roster.csv

`team_roster.csv` is the only manually maintained input file. It maps each team member to their current grade level and Agentforce Enabled status. These two values cannot be reliably derived from other inputs: grade is not available from the skill ratings export, and AF Enabled status requires checking the Trailhead superbadge completions (Champion, Innovator, Legend) which are not present in the certifications export.

**Required columns:**

| Column | Type | Description |
|---|---|---|
| `Employee` | string | Full name exactly as it appears in the PSA skill ratings export |
| `Grade` | string | Grade level in the format `Grade N` (e.g., `Grade 5`, `Grade 7`) |
| `AF Enabled` | string | `Yes` if the employee has completed all three Agentforce Trailhead superbadges (Champion, Innovator, Legend) AND holds the Salesforce Certified Data Cloud / Data 360 Consultant certification. `No` otherwise. |

**Example:**

```csv
Employee,Grade,AF Enabled
Craig Scott,Grade 7,No
Jordan Tetzel,Grade 5,No
Justin Powall,Grade 6,No
Keith Johnson,Grade 6,No
Ramandeep Kaur,Grade 5,Yes
```

**How to determine AF Enabled status:** Check the org62 Readiness Summary dashboard (Professional Services Analytics app → Readiness Summary). An employee appears in the "Agentforce Enabled" or "AF Enabled but Not Ready" column if and only if they have met the enablement criteria. Employees in the "Agentforce Not Enabled" column should be set to `No`.

**When to update this file:**
- When a team member earns a new grade level
- When a team member completes all three Agentforce superbadges AND the Data Cloud cert (set `AF Enabled` to `Yes`)
- When adding a new direct report to the review scope

---

## Validation Logic and Flag Conditions

### Flag 0 — AF Not Enabled (Informational)

**Condition:** The employee is not listed as AF Enabled in `team_roster.csv` AND the rating on any Agentforce-designated skill is 3+.

**Output behavior:** An `AF NOT ENABLED:` note appears in the Flags column. This note is **informational only** — it does not change the Pre-Disposition. If the rating is otherwise fully justified (cert on file, qualifying RRs on file, rating at or above minimum), the record still shows **Approve** (green) with the informational note visible. The note becomes **Discuss** (yellow) only when other issues exist alongside it (e.g., a CERT: or catalog flag). It becomes **Change Required** (red) only when an `AGENTFORCE:` gate also fails.

**What the note means:** AF skill ratings accumulate in the system, but they cannot count toward the employee's Agentforce Ready or Agentforce Expert designation until AF Enabled prerequisites are complete (Agentforce Champion, Innovator, and Legend Trailhead superbadges + Salesforce Certified Data Cloud / Data 360 Consultant cert).

**Output columns added for AF skills:**
- `AF Ready Skill` — `Yes (1 of 17)` if the skill is one of the 17 Agentforce Ready Key Skills; `Expert Only` if it is one of the 4 Expert-only advanced skills
- `AF Enabled` — `Yes` or `No` based on `team_roster.csv`

### Flag 1 — Skill Not in PSA Catalog

**Condition:** The skill name does not match any entry in the current PSA Skills and Certifications catalog (exact or normalized partial match).

**Why it matters:** Skills outside the catalog cannot be approved in org62 and may represent outdated names, typos, or skills that have been sunset. Flagging ensures the manager either corrects the name or escalates for catalog addition before approval.

### Flag 2 — Agentforce Rating Below Minimum

**Condition:** The skill is designated Agentforce Ready and the self-rated value is below 3-Advanced.

**Why it matters:** Agentforce Ready is a program-level designation. A 1-Entry or 2-Intermediate rating on an Agentforce skill is an unresolved gap that should be surfaced for coaching or re-rating.

### Flag 2a — Tier 1 AF Cert Gate at 3-Advanced

**Condition:** The skill is a Tier 1 Agentforce skill (not Tier 2 professional competency, not Tier 3 delivery, not Data 360), the rating is 3-Advanced or higher, AND the Agentforce Specialist certification is not on file.

**Why it matters:** 3-Advanced is the first level asserting real delivery capability. Approving it without the vendor-endorsed credential means accepting an entirely self-reported claim with no external validation — inconsistent with how comparable claims in other technical disciplines are validated. The Agentforce Specialist cert is the minimum professional standard Salesforce has defined for Agentforce practitioners.

### Flag 2b — Data 360 Cert Gate

**Condition:** The skill name contains "data 360" or "data cloud," the rating is 3-Advanced or higher, AND the Data Cloud / Data 360 Consultant certification is not on file.

**Why it matters:** The Agentforce Specialist cert validates agent configuration and prompt engineering — it does not cover Data Cloud data ingestion pipelines, identity resolution, segmentation, or data activation. These capabilities require a distinct credential (Data Cloud Consultant). A 3-Advanced claim on Data 360 for Agentforce without the Data Cloud cert is structurally unsupported regardless of how the Agentforce cert is scoped.

### Flag 2c — Tier 2 Grade Ceiling Exceeded

**Condition:** The skill is a Tier 2 professional competency skill (Business Acumen, AI Consulting, Executive Alignment, Agility), AND the rating exceeds the grade-based ceiling (Grade 5–6 max: 3-Advanced; Grade 7+: 4-Specialist supported).

**Why it matters:** These skills reflect advisory seniority and executive engagement depth that are structurally tied to grade level and client history — not to delivery volume or certification count. A Grade 5 consultant claiming 4-Specialist on Executive Alignment has not yet had the organizational access required to develop that level of competency. Enforcing a grade ceiling prevents inflation of professional competency claims beyond what the employee's career stage can reasonably support.

**Note on bio evidence:** For Tier 2 skills that pass the grade ceiling check, the manager should still verify against the employee's bio and client history in the 1:1 conversation. The grade ceiling is the structural floor; the bio provides the qualitative substance.

### Flag 3 — Tier 3 Delivery Evidence Insufficient

**Condition:** The skill is a delivery-type Agentforce skill (Agentforce Delivery, Agentforce Testing, Conversation Design, Agent Performance Tracking, Field Service, AI Ecosystem and Frameworks, Retrieval Augmented Generation), the rating is 3-Advanced or higher, AND one or both of the following are missing: (a) Agentforce Specialist certification not on file; (b) fewer than the required qualifying RRs.

See the Three-Tier Framework section above for qualifying RR criteria and thresholds.

### Flag 3b — Observability Claim Without Implementation Evidence

**Condition:** The skill is "Observability Frameworks and Tools" and the self-rating is 3-Advanced or higher.

**Why it matters:** Observability is a domain where surface-level exposure (configuring a managed Splunk package, enabling Salesforce Shield event monitoring) is frequently conflated with hands-on implementation competency. Salesforce Shield is a data security product (field audit, event monitoring, platform encryption) — it does not corroborate observability engineering depth.

**Qualifying evidence for 3-Advanced:** Direct instrumentation of one or more of: Prometheus, Grafana, Datadog, ELK/OpenSearch, OpenTelemetry, Splunk (self-managed) at the platform level on a real project.

**Certification path:**

| Level | Certifications (proctored exams only) |
|---|---|
| 3-Advanced | Splunk O11y Cloud Certified Metrics User (Pearson VUE); OR Dynatrace Certified Associate (Pearson VUE); OR Grafana Certified Associate; OR New Relic Certified Performance Pro (PSI) |
| 4-Specialist | Elastic Certified Observability Engineer; OR Dynatrace Certified Professional; OR Splunk Enterprise Certified Architect |

Note: Datadog does not offer a proctored certification. OpenTelemetry has no formal CNCF certification.

### Flag 3c — Configuration Management Claim Without Independent Authorship Evidence

**Condition:** The skill is "Configuration Management Frameworks and Tools" and the self-rating is 3-Advanced or higher.

**Why it matters:** Engineers who have run existing pipelines, added jobs to existing workflow files, or made changes under guidance of a senior engineer routinely self-rate at 3-Advanced. The qualifying bar is independent design and authorship of reusable CI/CD governance infrastructure from scratch.

**Qualifying evidence for 3-Advanced** (one of):
- **GitHub Actions:** Authored a composite action (`action.yml`) or centralized reusable workflow repo, versioned and consumed by other teams
- **GitLab CI/CD:** Authored a CI/CD component with declared inputs, or a group-level shared pipeline template hierarchy
- **Bitbucket:** Authored a custom Docker-based Pipe published to a registry
- **IaC:** Authored parameterized Terraform modules; OR written Ansible roles for idempotent state; OR designed a GitOps workflow (ArgoCD/Flux) reconciling Git state to live infrastructure

**What does NOT qualify:** Running or troubleshooting existing pipelines; adding jobs to existing files; configuring secrets in existing pipelines; Copado/Gearset as sole evidence; work performed under active guidance.

**Certification path:**

| Level | Certifications (proctored exams) |
|---|---|
| 3-Advanced | **GitHub Actions certification** (PSI; primary signal); OR GitLab CI/CD Associate; OR HashiCorp Terraform Associate (004); OR AWS DevOps Engineer Professional |
| 4-Specialist | Above + one of: Microsoft DevOps Engineer Expert (AZ-400); OR Terraform Authoring and Operations Advanced; OR Red Hat Ansible Automation Specialist (EX294) |

### Flag 3d — Containerization Claim Without Kubernetes Engineering Evidence

**Condition:** The skill is "Containerization Frameworks and Tools" and the self-rating is 3-Advanced or higher.

**Why it matters:** Docker familiarity and conceptual Kubernetes knowledge are frequently cited as 3-Advanced evidence. The bar requires independent design and operation of containerized workloads on a real cluster — not guided labs, not local Docker Desktop, not deploying a pre-configured Helm chart.

**Qualifying evidence for 3-Advanced** (one of): Independently configured Kubernetes cluster networking/RBAC/storage; authored a Helm chart or Kustomize overlay from scratch; designed a GitOps reconciliation loop (ArgoCD or Flux); authored CI/CD stages covering build → image scan → push → cluster deploy with rollback.

**What does NOT qualify:** Local Docker Desktop only; deploying a pre-built chart from documentation; tutorials or labs without production deployment; KCNA cert alone (knowledge-based, no hands-on).

**Certification path:**

| Level | Certifications (CNCF performance-based, live cluster tasks) |
|---|---|
| 3-Advanced | **CKAD** — Certified Kubernetes Application Developer; OR **CKA** — Certified Kubernetes Administrator |
| 4-Specialist | **CKS** — Certified Kubernetes Security Specialist (**requires active CKA as prerequisite**); OR Red Hat Certified Specialist in OpenShift Administration (EX280) |

Note: Docker Certified Associate (DCA) was discontinued/paused in 2023. KCNA is knowledge-based only. No official ArgoCD certification exists.

### Flag 3e — Environment/Sandbox Management Claim Without Architecture Evidence

**Condition:** The skill is "Environment/Sandbox Management" and the self-rating is 3-Advanced or higher.

**Why it matters:** Platform Administrator certification covers foundational sandbox creation — scheduling refreshes, understanding sandbox tiers at a conceptual level. It does not validate the ability to independently design a multi-team, multi-sprint Salesforce environment strategy, configure Salesforce DX scratch org pipelines, or govern environment promotion paths in a DevOps toolchain. The gap between "I work in sandboxes" and "I designed the sandbox strategy" is the same gap observed in Observability (managed package vs. instrumentation) and Containerization (Docker Desktop vs. Kubernetes engineering).

**Cert hierarchy for this skill:**

| Cert | Tier | What It Validates |
|---|---|---|
| Salesforce Certified Development Lifecycle and Deployment Architect (PDLDA) | Primary / 3-Advanced | Sandbox tier strategy, org shapes, scratch org configuration, deployment methodology, environment-to-release alignment |
| Salesforce Certified Advanced Administrator | Secondary / 3-Advanced | Change Sets, sandbox management workflow, metadata deployment depth — a meaningful step above Platform Admin |
| Copado Fundamentals I or II | Supplementary | Environment tree design, sandbox promotion paths, environment variable management in a Salesforce DevOps pipeline |
| Salesforce Certified Platform Administrator | Baseline only | Foundational sandbox creation and refresh — does not support a 3-Advanced claim on environment *strategy* |

**What constitutes a qualifying 3-Advanced claim:**
- Independently designed sandbox allocation model (tier selection, role assignment, refresh cadence) for a multi-team implementation
- Configured Salesforce DX scratch orgs with project-scratch-def.json, org shapes, source tracking, and seeding in a CI/CD context
- Designed an environment promotion tree in Copado or Gearset (designed — not just operated an existing one)

**4-Specialist** requires PDLDA + Advanced Administrator + evidence of enterprise-scale environment governance: multi-team or multi-release-train sandbox strategy, org shape governance policy, or scratch org pool design for high-velocity CI/CD pipelines.

**Note on PDLDA holders:** If the employee holds PDLDA, the cert gate is satisfied. The justification request asks for the specific environment architecture decisions made on a customer engagement — this is routine documentation, not a challenge to the claim.

---

### Flag 4 — 4-Specialist Claim Without Cert Corroboration

**Condition:** The self-rating is 4-Specialist and no certification on file corroborates the claimed skill domain.

**Why it matters:** Specialist-level claims represent mastery. In the absence of a formal credential, the manager must obtain alternative observable evidence before approving.

### Flag 5 — Below DevOps Grade Floor

**Condition:** The self-rating is below the minimum specified in the DevOps Leveling Guide for the employee's grade.

**Why it matters:** The leveling guide defines the floor — the minimum expected proficiency at each grade level. A rating below floor indicates either a development gap that should be surfaced, or a miscalibrated self-assessment.

---

## Industry Rationale and Supporting References

### Experiential Learning and On-the-Job Evidence

The primacy of delivery evidence over self-assessment in this toolchain reflects a well-established principle in competency development research.

> "Learning is the process whereby knowledge is created through the transformation of experience."
> — Kolb, D.A. (1984). *Experiential Learning: Experience as the Source of Learning and Development.* Prentice-Hall. [^1]

The 70-20-10 learning model found that approximately 70% of professional development comes from on-the-job experiences, 20% from feedback and coaching, and 10% from formal training and coursework. [^2] A certification (formal training artifact) alone is therefore insufficient evidence of delivery capability — the 70% component must be demonstrated through work artifacts, which this toolchain approximates via PSA Resource Request history.

### Skill Level Frameworks

The four-point rating scale (1-Entry, 2-Intermediate, 3-Advanced, 4-Specialist) is structurally analogous to established competency level frameworks used across the technology industry.

The **Dreyfus Model of Skill Acquisition** (1980, refined 1986) describes skill development as a progression through five stages — Novice, Advanced Beginner, Competent, Proficient, Expert — differentiated primarily by the degree to which the practitioner can perform without explicit rules, handle novel situations, and take ownership of outcomes. [^3] The 3-Advanced / 4-Specialist distinction maps approximately to the Competent/Proficient boundary: at 3, the practitioner applies known methods independently; at 4, the practitioner perceives the situation holistically and adapts methods to fit.

The **SFIA (Skills Framework for the Information Age)** framework defines seven levels characterized by autonomy, influence, complexity, business skills, and knowledge. [^4] SFIA's Level 4 (Enable) and Level 5 (Ensure/Advise) map roughly to 3-Advanced and 4-Specialist: Level 4 requires working under general direction; Level 5 requires providing guidance to others and making decisions affecting the work of others.

The three-tier framework implemented in this toolchain reflects a structural distinction in how different skill types accumulate: Tier 1 skills (technical configuration knowledge) are most efficiently validated through vendor certification; Tier 2 skills (professional competency) accumulate through seniority, client exposure, and organizational scope that certificates cannot capture; Tier 3 skills (delivery execution) require evidence of both knowledge (cert) and applied practice (RR history) per the 70-20-10 model.

### Certification as Evidence of Knowledge Competency

Vendor certifications are widely used in enterprise technology talent management as a standardized, externally validated signal of domain knowledge. Research on competency assessment in IT organizations has consistently found that certification is a more reliable predictor of knowledge capability than self-assessment alone, due to social desirability bias and the Dunning-Kruger effect. [^5]

Salesforce's **Certified Agentforce Specialist** credential is positioned as the practitioner-level Agentforce certification, requiring demonstrated knowledge of agent architecture, topic and instruction design, data grounding, and deployment. Requiring it as a gate for 3-Advanced Tier 1 and Tier 3 claims is consistent with Salesforce's own framing of the credential as the minimum professional standard for Agentforce delivery practitioners.

### Evaluation Against Stated Standards

The structure of this toolchain — surfacing gaps against explicit, pre-defined criteria with documented reasoning for each flag — reflects the Level 3 (Behavior) and Level 4 (Results) evaluation approach described in the Kirkpatrick Model. [^6] Rather than evaluating only whether training occurred, the toolchain evaluates whether training has translated into changed on-the-job behavior (delivery on Agentforce engagements) and whether that behavior meets an organizational standard.

### Post-GA Date Boundary (October 2024)

Salesforce announced Agentforce at Dreamforce in September 2024, with general availability in October 2024. [^7] Delivery evidence predating GA is not qualifying because: (1) pre-GA Agentforce was a beta/pilot with significantly different architecture; (2) pre-GA engagements were exploratory, not representative of production delivery competency; (3) using GA as the boundary ensures qualifying RRs reflect the generally available product.

---

## Footnotes

[^1]: Kolb, D.A. (1984). *Experiential Learning: Experience as the Source of Learning and Development.* Englewood Cliffs, NJ: Prentice-Hall.

[^2]: McCall, M.W., Lombardo, M.M., & Morrison, A.M. (1988). *The Lessons of Experience: How Successful Executives Develop on the Job.* Lexington, MA: Lexington Books. The 70-20-10 ratio was later formalized by Jennings, C. (2013). *70:20:10 Framework Explained.* 70:20:10 Institute.

[^3]: Dreyfus, H.L., & Dreyfus, S.E. (1986). *Mind Over Machine: The Power of Human Intuition and Expertise in the Era of the Computer.* New York: Free Press. Original five-stage model: Dreyfus, S.E., & Dreyfus, H.L. (1980). *A Five-Stage Model of the Mental Activities Involved in Directed Skill Acquisition.* Operations Research Center, University of California, Berkeley.

[^4]: SFIA Foundation. (2021). *SFIA 8: Skills Framework for the Information Age.* Retrieved from https://sfia-online.org. Seven levels: 1-Follow, 2-Assist, 3-Apply, 4-Enable, 5-Ensure/Advise, 6-Initiate/Influence, 7-Set Strategy.

[^5]: Kruger, J., & Dunning, D. (1999). Unskilled and unaware of it: How difficulties in recognizing one's own incompetence lead to inflated self-assessments. *Journal of Personality and Social Psychology, 77*(6), 1121–1134. Applied to IT competency: Bandura, A. (1997). *Self-Efficacy: The Exercise of Control.* New York: Freeman.

[^6]: Kirkpatrick, D.L., & Kirkpatrick, J.D. (2006). *Evaluating Training Programs: The Four Levels* (3rd ed.). San Francisco: Berrett-Koehler.

[^7]: Salesforce, Inc. (2024). *Agentforce: The Agentic Layer of the Salesforce Platform.* General availability announced October 2024. Salesforce Dreamforce 2024 keynote, September 2024, San Francisco, CA.

---

## Usage

```bash
# Step 1 — scrape pending skill ratings from org62 Mass Approve page
# (launches a visible Chromium browser; authenticate via Okta SSO if prompted)
python3 scrape_skill_ratings.py

# Step 2 — scrape Agentforce delivery evidence (Resource Requests) from org62
python3 scrape_agentforce_resource_requests.py

# Step 3 — validate all skill ratings against the full 3-tier framework
python3 validate_skill_ratings.py

# Step 4 — generate the review XLSX workbook
python3 generate_review_artifacts.py
```

**After generating the XLSX:**

1. Upload `skill_rating_review_*.xlsx` to Google Drive
2. File → Save as Google Sheets (enables cross-tab VLOOKUP formulas)
3. Share each employee's individual tab with them for self-review
4. Employees fill in column L (justification) and column M (proposed change)
5. Manager Tracker column M auto-populates with each employee's proposed change via VLOOKUP
6. Hold 1:1 discussions for red-highlighted rows; record agreed rating in column N and final action in column O
7. Use Manager Tracker as reference for org62 Mass Approve / Change workflow

**Re-run cadence:** Re-run `scrape_skill_ratings.py` before each review cycle to pick up newly submitted records. Re-run `scrape_agentforce_resource_requests.py` whenever an employee completes a new Agentforce engagement, to refresh the Tier 3 RR evidence baseline.

---

## Iteration Log

| Date | Version | Changes |
|---|---|---|
| 2026-09-16 | v1 | Initial pipeline: scrape → validate → generate XLSX. Four rule sets: PSA catalog, AF minimum, delivery evidence (Tier 3), DevOps grade floor. |
| 2026-09-17 | v2 | Data 360 cert gate added: Agentforce Specialist excluded from corroborating Data 360/Data Cloud skills. Only Data Cloud Consultant cert qualifies. AF Enabled status corrected: Ramandeep Kaur is the only direct report with both Agentforce Specialist + Data Cloud Consultant certs. Craig Scott is NOT AF Enabled. |
| 2026-09-18 | v3 | Full 3-tier framework implemented: Tier 1 cert gate at 3-Advanced (Flag 2a), Tier 2 grade ceiling (Flag 2c). CERT_DOMAIN_MAP expanded to correctly cover "action planning", "design and configure", "build and deploy" under Agentforce Specialist; "flow" added to Platform Administrator domain. _pre_disposition and _summarize_notes updated for TIER2: flag prefix. README updated to document full framework, bio evidence sources, AF Enabled table, iteration log. |
| 2026-09-18 | v4 | Environment/Sandbox Management cert hierarchy added (Flag 3e). CERT_DOMAIN_MAP updated: Copado Fundamentals I/II now corroborates environment/sandbox skills; new "advanced administrator" entry added covering environment, sandbox, configuration, and release management keywords. CERT_RECOMMENDATIONS "environment" entry expanded to full cert path (PDLDA primary, Advanced Admin secondary, Copado I/II supplementary, Platform Admin baseline-only). Justification gate added to _JUSTIFICATION_REQUIRED_SKILLS at 3-Advanced with evidence criteria, qualifying vs. non-qualifying examples, and cert path. |
