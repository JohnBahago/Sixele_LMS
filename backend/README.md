# Sixele LMS FastAPI Backend

FastAPI + MongoDB backend for Sixele LMS.

## Run

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Bootstrap Super Admin

After MongoDB is configured and the environment is active:

```bash
python -m scripts.bootstrap_superadmin
```

The Super Admin is a system-level authority. Other roles are dynamic and are defined through the permission catalog.

## v0.5 Assessment & Quiz Management
- Quiz CRUD and publish/archive lifecycle.
- Question bank with single-choice, multiple-choice, true/false, short-answer, and essay questions.
- Configurable quiz pass mark, attempts, time limit, required flag, and ordering.
- Learner quiz attempts with automatic grading for objective questions.
- Manual grading workflow for short-answer and essay questions.
- Assessment audit logging and MongoDB indexes.

## v0.9 — Notifications & Communication

Adds user notifications, read/unread tracking, bulk notification creation, notification preferences, and audit logging. Notification creation is permission-controlled; users can only read, update, or delete their own notifications.


## v1.8 — Assignment & Final Project Engine

Adds a dedicated assignment/final-project workflow:
- Assignment and final project CRUD with course scoping
- Draft/published/archived lifecycle
- Briefs, deliverables, submission rules, attempt limits and pass marks
- Learner submissions and resubmissions
- Instructor/assessment grading, rubric criterion scores and feedback
- Review and return-for-revision workflow
- Assignment progress tracking
- Final-project completion enforcement through `completion_rule.require_final_project`
- Audit events and MongoDB indexes for assignment data


## v1.9 — Learner Assignment & Final Project Portal Integration
- Learner assignment/final-project list and detail endpoints.
- Learner submission and resubmission endpoints with attempt enforcement.
- Learner submission history with feedback and grading results.
- Assignment progress surfaced to the learner portal.
- Learner dashboard pending-assignment count.
- Course module assignment counts.
- Learner-facing responses exclude grader identity and other administrative internals.


## v2.5 — Background Jobs & Scheduled Tasks
- In-process asynchronous job scheduler started and stopped with the FastAPI lifespan.
- Database-backed leases prevent the same scheduled job from being processed concurrently across workers.
- Email outbox processing runs automatically every 30 seconds.
- Read-notification cleanup runs automatically according to `notifications.retention_days` (default 180 days).
- Job execution status, results, errors, worker ID, and timestamps are persisted in `scheduled_jobs`.
- Admin job status endpoint: `GET /api/jobs`.
- Manual job execution endpoint: `POST /api/jobs/{job_name}/run`.
- New `jobs.view` and `jobs.manage` permissions.
- Scheduler failures are isolated so a failed background task does not terminate the API process.


## v2.5 completion automation
The completion engine reconciles active enrollments, emits a course-completed event once, and can automatically issue certificates using the configured/default active template. The scheduled completion reconciliation job runs every 60 seconds by default.


## v2.6 — Certificate PDF Generation & Verification
- Generates a print-ready A4 landscape certificate PDF when a certificate is issued.
- Stores the generated certificate file under the configured upload directory.
- Certificate responses expose a protected download endpoint.
- Learners can download their own certificates; staff need `certificates.view`.
- Public certificate verification remains available by certificate number.
- PDF generation failures are audited without invalidating the certificate record.
- Added `reportlab` dependency and certificate PDF indexing.

## v2.8 — Admin Course Builder & Publishing Engine

Adds a validation-driven course publishing workflow. Courses can be validated, submitted for review, and published only when required structure and completion dependencies are configured. The existing course publish endpoint uses the same validation service to prevent bypassing the builder rules.

New endpoints:
- `GET /api/course-builder/{course_id}/validate`
- `POST /api/course-builder/{course_id}/submit-review`
- `POST /api/course-builder/{course_id}/publish`


## v3.3 Attendance Rules & Training Compliance
- Configurable `attendance.minimum_percentage` system setting (default 75%).
- Cohort attendance compliance report.
- Per-learner compliance summary.
- Compliance statuses: `compliant`, `at_risk`, `not_started`.
- Cancelled sessions are excluded from compliance calculations.


## v3.4 — Attendance Alerts & Training Compliance Automation
- Scheduled attendance compliance monitoring every 15 minutes.
- Automatic learner warning, at-risk, and recovery notifications.
- Optional instructor alerts when a learner enters or leaves attendance risk.
- Configurable attendance alerts, warning margin, and instructor notification settings.
- Session cancellation/rescheduling notifications to active cohort learners.
- Attendance notification preference support.
- Persistent compliance alert state prevents repeated duplicate alerts.
- Added compliance-alert indexes and audit events.
