# Recruitment

Recruitment has its own sidebar section. It is an internal HR workflow; public applications and automatic email delivery are not part of this release.

## Pages

| Page | Purpose |
| --- | --- |
| `/app/recruitment/overview` | Hiring totals, open vacancies and upcoming interviews |
| `/app/recruitment/jobs` | Draft, open and closed vacancies |
| `/app/recruitment/jobs/:id` | Vacancy details and applicant actions |
| `/app/recruitment/candidates` | Search candidate profiles |
| `/app/recruitment/candidates/:id` | Contact details, CV, applications, interviews, offers and history |
| `/app/recruitment/interviews` | Scheduling, cancellation and panel feedback |
| `/app/recruitment/offers` | Draft terms, issue tracking, acceptance, decline, withdrawal and hiring |
| `/app/recruitment/reports` | Application stage totals and vacancy progress |

## Try the workflow

1. Create a vacancy, save it as a draft and open it.
2. Add a candidate. Open their profile to upload a PDF or DOCX CV (up to 10 MB).
3. Add an application to an open vacancy. A candidate can apply to multiple vacancies using the same profile.
4. Shortlist the applicant and schedule an interview. The panel picker includes active employees with active logins and `recruitment.interview` permission.
5. Sign in as an assigned interviewer to record a 1–5 rating, recommendation and written feedback. Feedback never automatically selects or rejects a candidate.
6. HR prepares an offer with monthly gross salary, currency, start date, expiry and terms. After sharing it with the candidate, mark it as issued and record the candidate's response.
7. After acceptance, choose **Create employee**, confirm the branch and employment dates, and optionally enter the work email. The new employee appears under People with contact information, department, job title and assigned supervisor.

The offer amount is not automatically configured in Payroll. Employee login provisioning and employment documents use the existing employee workflows.

Closed vacancies cannot accept applications or progress active applications. A passed application closing date blocks new applications, but existing applicants can continue through interviews and offers. Rejected and withdrawn applications can be reopened against an open vacancy. Decisions and cancellations require reasons.

An issued or accepted offer must be withdrawn before changing application stage or offer terms. Edit a withdrawn/declined offer to prepare a new draft. Completed hires cannot be reversed through Recruitment; use the existing employee lifecycle workflow.

## Access and isolation

- Owner/Admin and HR manage recruitment by default.
- Managers see applications for vacancies assigned to them, plus applications for interviews assigned to them.
- Interviewers see only their assigned applications and interviews unless they also manage the vacancy.
- Managers/interviewers do not receive offer amounts, private HR notes or internal event history.
- Employees have no Recruitment access by default.
- Creating an employee requires both `recruitment.manage` and `people.manage`.
- Tenant scope is checked on every record lookup. Company references are validated before writes. Database row-level security also applies to all six new tables.
- A unique application per vacancy/candidate and unique candidate email per company prevent duplicates. Hiring locks the vacancy, application, candidate and offer, checks capacity and existing employee emails, and commits employee creation with the application update.

## Demo examples

Run `python -m app.db.seed_recruitment_demo` from the backend after migration `041_recruitment`.

The seeder requires the active `demo@example.com` owner of the active **East Africa Demo** tenant. It adds examples to that tenant's active companies only, does not delete existing records, does not reset edited examples and does not alter Performance.

Each company receives:

- Two open vacancies and one draft vacancy, labelled `DEMO`.
- Zuri Demo: new applicant, ready to shortlist.
- Kevin Demo: scheduled interview with Morgan Demo when that existing demo manager is available.
- Faith Demo: accepted offer, ready for HR to create the employee.
- Sam Demo: rejected application with a recorded reason.

Use the existing Performance demo manager login for Kevin's feedback, for example `performance.morgan@rift-demo.example`, password `PerformanceDemo12!`. The owner or demo HR login manages the remaining steps. The seeder does not change passwords or create employee records from accepted offers.

## Validation

Integration tests cover the complete hiring journey, candidate/application duplicates, CV access and file validation, interview assignment, unauthorized feedback, role and tenant isolation, company boundaries, accepted-offer requirements, capacity, immutable hires, expired offers, closed vacancies and guarded/idempotent demo seeding. Existing access tests enforce permission dependencies for every tenant mutation.
