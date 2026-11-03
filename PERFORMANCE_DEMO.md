> Historical documentation for the previous module. The replacement workflow is documented in [APPRAISALS.md](APPRAISALS.md).

# Performance review demo

The East Africa Demo workspace has two fictional performance reviews in each company. The earlier separate cycle-stage examples have been removed. Existing demo logins, employee records, company settings, and unrelated reviews are preserved.

Select **Rift Valley Trading Ltd ? Performance ? Reviews**.

| Review | What to see |
|---|---|
| Current performance review | Four employees, five approved goals each, two progress updates per goal, check-ins, and evidence. HR and the assigned manager can enter goal definitions; employees update progress. Self-review opens seven days after the examples were created and ends fourteen days later. |
| Completed performance review | Four completed self-reviews and manager assessments, discussions, acknowledgements, final ratings, development actions, and two improvement-plan examples. |

The completed review demonstrates scores of 4.73 (Outstanding), 3.46 (Meets Expectations), 2.42 (Needs Improvement), and 4.08 (Exceeds Expectations). Calibration is optional and disabled in these examples. The completed review retains historical self-review dates. Audit timestamps reflect when the fictional examples were created.

Use these existing logins, with password **PerformanceDemo12!** (unless you changed it):

| Role | Rift Valley login |
|---|---|
| HR | performance.helena@rift-demo.example |
| Manager | performance.morgan@rift-demo.example |
| Employee | performance.amina@rift-demo.example |

Nile Logistics and Coastal Packers have the same two-review walkthrough; replace `rift-demo.example` with `nile-demo.example` or `coastal-demo.example` in the login email.

HR can open self-review within its date window, start manager assessment after required employee submissions, record discussions, prepare final results, and close the review after individual records are finalized. Goal entry and employee self-review are separate tasks.

## Seed command

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.db.seed_performance_reviews
```

The command targets only the active East Africa Demo tenant. It matches the old seed names exactly and verifies synthetic participants before removing those examples and their dependent demo records. Replacement commits as one transaction. Repeated runs preserve the new reviews and do not reset passwords or recreate old cycle-stage examples. Existing system audit logs remain available.
