# Payslip PDF downloads

## Email through Brevo

Payslips have a **Send to employee** button in payroll and **Email my payslip** in the employee portal. The PDF is sent only to the employee record's `Work email` field (`Employee.email`), never the login email or personal-email fallback. Add a work email to enable the button. Payroll managers and platform administrators can email drafts: the button reads **Send draft to employee**, the email subject/body identify it as unapproved, and the attached PDF retains its DRAFT watermark. Payroll managers and platform administrators retain their existing access boundaries; employees can send only their own approved payslips from the portal.

Set these server-side environment variables (never frontend/Vite variables):

```dotenv
BREVO_API_KEY=your-new-api-key
BREVO_SENDER_EMAIL=info@nexgenfuelworks.com
BREVO_SENDER_NAME=HRMS
```

Verify the sender/domain and enable transactional sending in Brevo. Restart the local backend after updating `.env`; for Docker, rebuild/recreate the backend so Compose passes the new settings. Rebuild the frontend to show the button. No database migration is needed for this feature.

The success message confirms Brevo accepted the message for delivery; final delivery is visible in Brevo's transactional logs. Network timeouts are not retried automatically because Brevo may already have accepted the message. Check those logs before manually retrying an uncertain submission.

Employees open **Employee portal > Payslips**, choose a pay period, then select **Download PDF**. Only their own approved payslips are available.

Payroll managers open a payroll run and select **View / download payslip** beside an employee. Platform administrators can use the same action inside a tenant's payroll. Unapproved statements display a draft warning, including a watermark in the PDF.

The screen and PDF include employer contact details, employee details, pay period, earnings, employee deductions, and net pay. Employee details include PIN, SHIF and NSSF numbers, with missing values left blank. Taxable pay appears below total deductions. Employer contributions remain in payroll calculations but are omitted from the payslip. Amounts come from the saved payroll run. Gross and taxable summaries are not counted twice as earnings. Longer statements continue across A4 pages with repeated table headings.

Rebuild the Docker services to install the PDF dependency and update the frontend:

```sh
docker compose up -d --build
```

No additional environment variables are needed for PDF downloads. Run `alembic upgrade head` inside `backend` to add the optional employee PIN field when running Python locally; Docker applies migrations on startup. For local development, install `backend/requirements.txt` and restart the backend; Vite picks up the frontend changes.

Validation: `backend/tests/test_payslip_pdf.py` covers layout, earnings reconciliation, approval requirements, employee ownership, tenant isolation, platform access, and saved payroll amounts.
