# Leave workflow emails

Leave events use the existing server-side Brevo settings. The backend processes a durable email queue every five seconds while running; there is no additional service to start. Run migration `047_leave_emails` before restarting a local backend. Docker applies migrations on backend startup.

| Event | Recipients |
| --- | --- |
| Application recorded | Confirmation to employee; alert to each assigned active supervisor; alert to each active workspace owner |
| Supervisor approves or declines | Confirmation to acting supervisor; alert asking workspace owner for final HR response |
| HR approves or declines | Confirmation to workspace owner; final decision alert to employee |

Supervisor approvals **and declines** now go to `PENDING_HR`. Only the final HR decision approves/rejects the request. Existing HR-only applications still go directly to HR. Notifications do not change role permissions: HR-role users retain the existing ability to decide requests, but HR email recipients are workspace owners. Immediately approved HR-created applications generate application and final-decision notifications.

Employees and supervisors use `Employee.email` (Work email), not personal email or sign-in email. For an owner linked to an employee profile, use that profile's Work email; only owners with no employee profile fall back to their owner account email, as requested. Missing/invalid work emails block that recipient's message and are checked again once per minute. Other recipients can still receive their messages. Inactive recipients/workspaces are not sent email.

Queue entries are saved in the same transaction as the leave change, so rolled-back changes send nothing. Messages are sent individually, and recipient lists are not shared. Event uniqueness prevents queuing the same notification twice. Multiple backend processes claim messages using row locks. Requests contain a stable Brevo idempotency key, but delivery is not an exactly-once guarantee across process crashes/provider retention windows.

Connection failures and rate limits retry up to five times with increasing delays. A network error after sending or a provider 5xx response is recorded as `UNCERTAIN`; check Brevo's transactional logs before retrying. Other rejected submissions are `FAILED`. Backend logs include only message IDs/status/error codes, not credentials or leave details. The `leave_emails` table retains queue state and the submitted recipient. `SENT` means Brevo accepted the message; it does not guarantee inbox delivery.

Keep `HRMS_BASE_DOMAIN` set to the deployed platform's hostname so sign-in links in emails point to the right application. No approval action happens from an email link; recipients must sign in.
