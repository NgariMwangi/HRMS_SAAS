# Payslip PDF downloads

Employees open **Employee portal > Payslips**, choose a pay period, then select **Download PDF**. Only their own approved payslips are available.

Payroll managers open a payroll run and select **View / download payslip** beside an employee. Platform administrators can use the same action inside a tenant's payroll. Unapproved statements display a draft warning, including a watermark in the PDF.

The screen and PDF include employer contact details, employee details, pay period, earnings, employee deductions, and net pay. Employee details include PIN, SHIF and NSSF numbers, with missing values left blank. Taxable pay appears below total deductions. Employer contributions remain in payroll calculations but are omitted from the payslip. Amounts come from the saved payroll run. Gross and taxable summaries are not counted twice as earnings. Longer statements continue across A4 pages with repeated table headings.

Rebuild the Docker services to install the PDF dependency and update the frontend:

```sh
docker compose up -d --build
```

No additional environment variables are needed for PDF downloads. Run `alembic upgrade head` inside `backend` to add the optional employee PIN field when running Python locally; Docker applies migrations on startup. For local development, install `backend/requirements.txt` and restart the backend; Vite picks up the frontend changes.

Validation: `backend/tests/test_payslip_pdf.py` covers layout, earnings reconciliation, approval requirements, employee ownership, tenant isolation, platform access, and saved payroll amounts.
