-- Row-Level Security for tenant isolation.
-- Tenant sessions: SET LOCAL app.current_tenant_id = '<uuid>'
-- Platform owner sessions: SET LOCAL app.is_platform_admin = 'true'

ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE companies FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_companies ON companies
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR tenant_id = current_setting('app.current_tenant_id', true)::uuid
    );

ALTER TABLE branches ENABLE ROW LEVEL SECURITY;
ALTER TABLE branches FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_branches ON branches
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE departments FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_departments ON departments
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE job_titles ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_titles FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_job_titles ON job_titles
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_employees ON employees
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE employee_lifecycle_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_lifecycle_events FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_employee_lifecycle_events ON employee_lifecycle_events
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE employee_lifecycle_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_lifecycle_attachments FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_employee_lifecycle_attachments ON employee_lifecycle_attachments
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE employee_next_of_kin ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_next_of_kin FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_employee_next_of_kin ON employee_next_of_kin
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE document_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_categories FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_document_categories ON document_categories
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE employee_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_documents FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_employee_documents ON employee_documents
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE leave_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE leave_types FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_leave_types ON leave_types
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE public_holidays ENABLE ROW LEVEL SECURITY;
ALTER TABLE public_holidays FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_public_holidays ON public_holidays
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE employee_supervisors ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_supervisors FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_employee_supervisors ON employee_supervisors
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE leave_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE leave_requests FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_leave_requests ON leave_requests
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE leave_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE leave_decisions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_leave_decisions ON leave_decisions
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE leave_balances ENABLE ROW LEVEL SECURITY;
ALTER TABLE leave_balances FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_leave_balances ON leave_balances
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_audit_logs ON audit_logs
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR (
            tenant_id IS NOT NULL
            AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR (
            tenant_id IS NOT NULL
            AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE attendance_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance_records FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_attendance_records ON attendance_records
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

-- countries, currencies, platform_admins, payroll_packs: no RLS.

ALTER TABLE company_payroll_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_payroll_settings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_company_payroll_settings ON company_payroll_settings
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE employee_compensation ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_compensation FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_employee_compensation ON employee_compensation
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE employee_pay_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_pay_lines FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_employee_pay_lines ON employee_pay_lines
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR compensation_id IN (
            SELECT id FROM employee_compensation
            WHERE company_id IN (
                SELECT id FROM companies
                WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
            )
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR compensation_id IN (
            SELECT id FROM employee_compensation
            WHERE company_id IN (
                SELECT id FROM companies
                WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
            )
        )
    );

ALTER TABLE payroll_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_payroll_runs ON payroll_runs
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE payroll_payslips ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_payslips FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_payroll_payslips ON payroll_payslips
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );

ALTER TABLE payroll_payslip_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE payroll_payslip_lines FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_payroll_payslip_lines ON payroll_payslip_lines
    USING (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    )
    WITH CHECK (
        current_setting('app.is_platform_admin', true) = 'true'
        OR company_id IN (
            SELECT id FROM companies
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
    );
