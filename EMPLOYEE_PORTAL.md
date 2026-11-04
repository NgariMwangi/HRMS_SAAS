# Employee portal

Employee sign-in: `/employee/login`. Portal: `/employee`.

The portal provides an overview with live personal counts and clock-in/out, contact and emergency-contact editing, employment history, attendance history, leave requests and balances, public holidays, approved payslips with Print / Save PDF, document previews/downloads, performance goals and assessments, notifications, password changes, and Google account linking/disconnection. Layouts support mobile and the existing light/dark theme.

HR must create an employee record and its login using the existing employee login action. There is no public employee registration. Users without an active linked employee record cannot enter the portal. Tenant and company must also be active. Employee-role sign-in, installed-app launches, and legacy workspace URLs redirect to the portal. Performance notification links preserve their appraisal query. Other roles with employee records can open the portal from the workspace user menu.

Owners can open **Employees → employee → Employee portal login → Change login / reset password** to change the sign-in email or set a replacement password. Leaving both password fields blank preserves the current password. Only the workspace owner can use this update action; ordinary HR/manager grants do not permit credential resets. Employees can open **Account settings** in their portal to change their own login email after confirming their current password, or use the separate Change password form. Sign-in email changes do not alter work/personal contact emails, linked employee identity, assigned roles or an existing Google connection. Duplicate login emails are rejected.

The portal pins its company and branch to its employee record and hides management controls, including for an employee who also has an HR role. Backend self-service endpoints derive the employee from the authenticated user. Only approved payroll is visible, and neither another employee's payslip nor a draft payslip can be requested by ID. Contact edits cannot alter employment details, login email, payroll, statutory identifiers, or roles.

Two permissions were added: `people.update_own_contact` and `payroll.view_own`. Migration `040_employee_portal` grants these once to existing built-in roles, preserving their other grants and custom roles. Administrators can subsequently revoke them in Roles settings. Custom roles need the relevant own-record grants to use the portal.

## Enable Google sign-in

1. In Google Cloud, create a project and configure its Google Auth Platform branding, audience, and OAuth consent settings. If it is in testing, add the employees who will test as test users.
2. Create an OAuth client of type **Web application**. Add the actual frontend origins to **Authorized JavaScript origins**. For local Vite development, include `http://localhost:5173` and `http://127.0.0.1:5173` if both are used. For production, add your exact HTTPS origin. This JavaScript callback flow does not require an authorized redirect URI.
3. Set the public client ID in the root `.env`:

   ```dotenv
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_COOKIE_SECURE=false
   ```

   Use `GOOGLE_COOKIE_SECURE=true` on HTTPS deployments. No Google client secret is needed or sent to the frontend.
4. Rebuild/restart the backend with `docker compose up -d --build backend`. Local Python runs must install `backend/requirements.txt` and apply `alembic upgrade head` before restarting.
5. Serve frontend and API through the same origin. Proxy `/auth`, `/employee-portal`, and the existing API prefixes to the backend; serve `/employee` and `/employee/login` as frontend routes. Vite's API proxy and service-worker exclusions already include the portal API. Private API responses are not service-worker cached.
6. Sign in at `/employee/login`. For the first Google sign-in, enter the HR-issued work login email/password, then select **Continue with Google**. Alternatively, sign in normally and connect Google in Account settings after confirming your password. After linking, Google alone signs in to that employee account. The Google email can differ from the work login email.

Until a client ID is configured, password sign-in remains available and the UI explains that Google setup is pending.

The backend verifies the Google token's RSA signature using Google's fixed HTTPS JWKS endpoint, audience, issuer, expiry, verified-email claim, and a short-lived browser-bound nonce. Successful nonces are consumed atomically to prevent replay. Identity binding uses Google's stable `sub`, never a client-provided email lookup alone. First-time linking requires the existing password; Google cannot create a tenant, employee, or elevated role. Linking/disconnecting requires password confirmation. Google credentials and nonce values are redacted from audit requests.

Setup reference: [Google Identity Services web client setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid). Verification reference: [Google server-side token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).

## Checks

Run `.venv/Scripts/python.exe -m pytest` inside `backend`. Tests use the isolated `hrms_test` database.

Run `npm run build` inside `frontend` for TypeScript, Vite, and service-worker validation. Real Google sign-in needs your configured client ID and authorized browser origin; automated tests use locally signed RSA tokens and substitute the trusted key lookup.

Password changes update the stored password immediately. Existing bearer tokens retain the project's current expiry behavior. Forgotten passwords are reset by HR through the existing login provisioning workflow; there is no email-reset delivery service in this project.
