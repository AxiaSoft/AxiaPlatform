# AXIASOFT — working development foundation

A responsive AXIASOFT brand site with a real server-side API and persistent SQLite database. This is an **operational development slice**, not a claim that the full production scope in the brief is complete. It is deliberately honest about the items that still require production engineering and external services.

## Implemented and testable

- Responsive premium dark/light interface, persisted theme choice, reduced-motion handling, catalog and product details loaded from the database, concept preview routes, About/Services/Contact/policy pages, and the AURION symbolic showcase.
- Restored first-pass visual styling: selective liquid-glass surfaces, the original ambient lighting/motion, responsive panels, and the supplied AXIASOFT and AURION logo images.
- Server-side registration/login, PBKDF2 password hashing, expiring opaque sessions stored as token hashes, HttpOnly/SameSite cookies, CSRF token checks on writes, rate limiting, request-size checks, validation, and role-protected admin endpoints.
- Real order request persistence, unique references, customer-scoped order listing, status history, admin status updates and audit records.
- Admin overview, database-driven product catalog, product creation, support ticket creation/escalation/replies/closure, and refund request review/decisions.
- Refund window enforced on the server at 14 calendar days from the order record. Admin approval only records a decision; there is no payment provider or automatic refund.
- Local bounded help assistant with approved product/process/policy guidance and a real human-support ticket escalation path. It is **not an LLM integration** and has no database/order access.
- AURION purchases and activation are intentionally non-operational.

## Run locally

Requirements: Python 3.10+ (standard library only); no `pip install` step is needed.

**macOS / Linux** (from the project root):

```bash
./run_local.sh
```

**Windows PowerShell:**

```powershell
.\run_local.ps1
```

Open `http://localhost:8000`. The app creates `data/axiasoft.sqlite3` and seeds the showcase catalog on first launch. If port 8000 is already occupied, choose another port, for example `PORT=8001 ./run_local.sh` (PowerShell: `$env:PORT=8001; .\run_local.ps1`). Stop the local server with Ctrl+C.

To create the administrator account, open a second terminal and run:

```bash
cd server
python3 provision_admin.py
```

The script prompts for a name, email and password (the password is not echoed). It writes a password hash to the local database, never a default password. Keep credentials and the SQLite database out of Git.

Optional settings: `PORT` (default `8000`) and `AXIA_DB` (database file path). For a containerized local run, use `docker compose up --build`, then open the same URL. Provision an admin inside the container with `docker compose exec axiasoft python server/provision_admin.py`. Docker persists SQLite data in a named volume.

## GitHub: source and checks vs hosting

This project is a Python application with a server API and SQLite database. GitHub can store the repository and run its automated checks, but **GitHub Pages alone cannot run this backend or the admin login**. The workflow in `.github/workflows/ci.yml` runs Python tests and JavaScript syntax checks on pushes and pull requests. To make the repository public or private on GitHub, create an empty repository there, then from this project root run:

```bash
git init -b main
git add .
git commit -m "Add AXIASOFT website"
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
git push -u origin main
```

Replace the remote URL with your own repository URL. Do not commit `.env` files, passwords, or `data/*.sqlite3`. To make the site reachable to other people, deploy the container/app to a Python-capable server; pushing source to GitHub does not itself publish a running website.

## Separate administrator console

A dedicated, responsive control panel is available at `/admin/` (for example, `http://localhost:8000/admin/`). It uses the same server-managed administrator session as the public site and includes an operations dashboard, project request workflow and status history, catalog management, customer directory/access controls, support inbox and replies, refund-decision records, audit activity, search/filtering, and CSV exports. It also supports the persisted English/Persian locale and RTL mode.

Administrator-only APIs enforce the role on the server; changes require the session CSRF token. Customer account suspension revokes active sessions. Refund decisions are records only—this console does not process payments. Product uploads, payment handling, and production-grade user/role administration are not implemented.

No default administrator or password is created. To provision one locally, from this project's `server` directory run:

```bash
python3 provision_admin.py
```

The script prompts for credentials without echoing the password. Existing customer accounts require an explicit `PROMOTE` confirmation; their existing sessions are then revoked. Never add real credentials to source control or chat.

## API overview

- `GET /api/health`, `/api/products`, `/api/products/{slug}`, `/api/me`
- `POST /api/register`, `/api/login`, `/api/logout`
- `POST /api/orders`, `GET /api/orders`
- `POST /api/support`, `GET /api/support`
- `POST /api/refunds`, `GET /api/refunds`
- Admin-only: `GET /api/admin/overview`, `/api/admin/customers`, `/api/admin/audit`, `/api/admin/orders/{id}/history`; `POST`/`PUT`/`DELETE /api/admin/products`; `PUT /api/admin/customers/status`, `/api/admin/orders/status`, `/api/admin/tickets/status`, `/api/admin/refunds/decision`; and `POST /api/admin/tickets/reply`

All write calls (except authentication) require the current session's `X-CSRF-Token`. Browser requests use same-origin cookies. Customer order and ticket queries are ownership-scoped in SQL.

## Production work required before launch

The brief describes a much larger product than this first deliverable. Do **not** deploy this development server as-is for real customers. In particular:

1. Replace `http.server` and SQLite with the intended supported stack (e.g. Next.js/NestJS, PostgreSQL/Prisma, migrations), production WSGI/ASGI process management, managed secret storage, TLS reverse proxy, backups and monitoring.
2. Add verified email, password-reset flow, MFA, user/role/permission management, stronger session lifecycle controls, persistent distributed rate limits, security headers/HSTS and automated security/dependency scans. PBKDF2 here is a safe standard-library development choice, not a substitute for a reviewed production identity solution/Argon2id.
3. Add private object storage, signed downloads, malware scanning and validated upload workflows. No file uploads are currently enabled.
4. Add production-grade user/role/permission administration, product media/category management and uploads, project assignments/files, internal notes, payment stages and configurable workflow statuses.
5. Add email-provider notifications, customer-visible ticket conversation UI, a real approved LLM provider behind a permission-limited backend adapter, conversation retention controls, escalation notifications and monitoring. No external AI provider is called here.
6. Integrate a real payment provider only after compliance/security review; never infer payment success. The refund workflow currently records review decisions only.
7. Complete consent/privacy disclosures and legal review for Germany/EU and any other operating markets, accessibility audit, SEO sitemap/robots/structured data, full browser and API test suites, load testing and OWASP review.
8. The supplied transparent AXIASOFT symbol and wordmark are installed in `public/brand/`; the wordmark sits beside the symbol in the header/footer. The supplied AURION logo is used on its showcase page. Both provided images retain their original raster artwork.

## Database and backups

The database file is configured by `AXIA_DB`; the default is `data/axiasoft.sqlite3`. Back up using SQLite's online backup mechanism or a quiesced copy, encrypt backups, restrict access, and periodically test restoration. Do not put production database files in a public/static directory. The schema in `server/db.py` is the complete current source of truth; automatic schema initialization is suitable only for this small development foundation, not production migrations.

## Verification

```bash
node --check public/app.js
node --check public/i18n.js
node --check public/admin/admin.js
python3 -m py_compile server/app.py server/db.py server/provision_admin.py
python3 -m unittest discover -s tests -v
```

The current test set covers important persistence/security invariants, but is not a production penetration test or complete end-to-end suite.
