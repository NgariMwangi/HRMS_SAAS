# Company domains

The main domain is **hrms.techtutor.co.ke**. Existing and newly created companies receive stable automatic addresses such as `kips-medical-centre.hrms.techtutor.co.ke`. Company renames do not change their addresses. Colliding names receive a unique suffix. Platform administration is available at `https://admin.hrms.techtutor.co.ke/admin` or the main domain's `/admin` page.

Company Owner/Admin: open **Workspace → Domains**, select the company, copy its automatic link or add a custom hostname. Platform Admin: open **Tenants → tenant → Company domains**. HR, Manager and Employee roles do not manage domains by default; a custom role can be explicitly granted `domains.manage`.

## Connect the public server

1. Deploy on a server with a public IP and allow incoming TCP 80/443 (UDP 443 is optional). DNS cannot route directly to a private localhost development address.
2. In the **techtutor.co.ke** DNS zone, add:

   | Type | Name | Value |
   | --- | --- | --- |
   | A | hrms | Your public server's IPv4 address |
   | CNAME | *.hrms | hrms.techtutor.co.ke |

   This includes `admin.hrms.techtutor.co.ke`. Remove conflicting DNS records. Add an AAAA record only if the server has working public IPv6. Use DNS-only records initially.
3. In the project root `.env`, set:

   ```dotenv
   HRMS_BASE_DOMAIN=hrms.techtutor.co.ke
   HRMS_DOMAIN_TARGET=hrms.techtutor.co.ke
   HRMS_CENTRAL_HOSTS=localhost,127.0.0.1,::1,backend
   DOMAIN_TLS_SECRET=<unique-random-secret>
   JWT_SECRET=<different-unique-random-secret>
   PLATFORM_ADMIN_PASSWORD=<strong-admin-password>
   TLS_EMAIL=<your-certificate-contact-email>
   GOOGLE_COOKIE_SECURE=true
   ```

   Generate secrets using `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep `.env` private. Setting a new platform password does not replace an existing seeded administrator's password; change an existing password through the supported administration process.
4. On the public server, with Docker Compose 2.24.4 or newer:

   ```sh
   docker compose -f docker-compose.yml -f docker-compose.domains.yml up -d --build
   ```

   The override builds the frontend, starts Caddy and keeps database, Redis and backend ports on localhost. Keep the persistent Caddy volumes to preserve certificates. Caddy requests certificates only for the main/admin/app addresses and active domains whose companies and tenants are active. The private authorization endpoint is blocked at the public gateway. [Caddy on-demand HTTPS documentation](https://caddyserver.com/on-demand-tls).

## Connect a company's custom domain

Add a **subdomain**, such as `people.company.co.ke`, in the Domains screen. The screen provides an exact CNAME pointing to `hrms.techtutor.co.ke` and a unique TXT proof at `_hrms-verification.people.company.co.ke`. Add both in the company's DNS provider, wait for propagation, then select **Verify connection**. Only a successful check activates routing. CNAME verification intentionally requires a subdomain rather than an apex ALIAS/flattened record. Keep the TXT record. No request is made to the submitted website; verification uses DNS queries.

“Active” means DNS ownership/routing were verified and the backend permits the hostname. It does not claim a certificate has already been issued; HTTPS is provisioned on the first public connection through the gateway. If connecting fails, check `docker compose -f docker-compose.yml -f docker-compose.domains.yml logs gateway backend`, the DNS records, CAA restrictions and ports 80/443. A disabled domain stops serving the company; reactivation requires verification again. Disconnecting the address currently in use requires opening the main HRMS address first.

## Sign-in and isolation

The request Host determines the company. Unknown, pending and disabled hosts fail closed. Forwarded-host and company-selection headers cannot override it. Company-bound sessions restrict reads and writes in the application as well as through PostgreSQL RLS. Another tenant's token cannot be used on the company's address; employee sign-in must match the linked employee's company. Owner/Admin/HR users in the same tenant retain their permissions but can access only the selected domain's company records. Use the main HRMS address for multi-company administration, signup and Platform Admin.

Tokens and Google nonce cookies remain scoped to each hostname; signing in on one domain does not sign in on another. Google sign-in needs a real client ID and each used HTTPS origin added to its **Authorized JavaScript origins** in Google Cloud. Google does not automatically authorize every tenant subdomain. [Google client setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid).

## Local development

Continue using `http://localhost:5173` and the ordinary `docker-compose.yml`; no public certificates are requested. Workspace → Domains works locally, but generated public links require the production DNS and gateway above. Host routing can be checked without changing Windows hosts files:

```sh
curl -H "Host: <company-address>.hrms.techtutor.co.ke" http://localhost:8000/domains/context
```

Use the actual generated address shown in Settings. Vite accepts `*.hrms.techtutor.co.ke` and preserves Host when proxying API requests. For a different configured base, update Vite's development allowed-host list too. Only exact extra central hosts in `HRMS_CENTRAL_HOSTS` bypass company selection; use that setting for a trusted development tunnel. Public frontend/backend requests share one origin through Caddy.
