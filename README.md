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
- Ambient motion layer (`public/effects.js` + `public/effects.css`): scroll progress rail, drifting aurora wash, pointer constellation canvas, cursor spotlight, scroll-reveal with stagger, animated gradient type, button shimmer and click ripples, cover light-sweep, hero parallax, and a calm variant for the admin console. It is additive and fully disabled under `prefers-reduced-motion`.

## Security and load hardening

Beyond the baseline (PBKDF2 hashing, hashed session tokens, HttpOnly/SameSite cookies, CSRF on writes, role checks on the server, ownership-scoped SQL), the server now defends against the failure modes that matter for a public shop with unpredictable traffic.

**Database safety.** Every request opens its connections through a tracked factory, and every one of them is closed when the request finishes — including error paths, which previously leaked a connection holding an open write transaction and wedged all writes with `database is locked`. SQLite now runs in WAL mode with autocommit plus `busy_timeout`, so a failed write cannot poison later requests. Multi-statement operations use `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`.

**Abuse control.**

| Control | Default | Notes |
| --- | --- | --- |
| Per-client concurrency | 16 in flight | extra requests get a clean `503` |
| Global in-flight ceiling | 256 (scales with CPU) | protects the process, not just one client |
| API reads | 1800/min | keyed per session, so shared NAT does not throttle neighbours |
| Identity bootstrap (`/api/me`) | 3000/min | separate generous bucket so a flood cannot lock a visitor out of the UI |
| API writes | 120/min | |
| Sign-in attempts | 30/min | plus per-email lockout after 8 failures for 15 min |
| Registration | 12/min | |
| Static assets | 3000/min | |
| Header block | 16 KB / 10 s | slow-header (slowloris) connections are cut |
| Request body | 100 KB, JSON depth 12 | oversized or non-object bodies are refused |

Buckets are fixed names chosen by the route, never the raw URL, so `?nonce=` no longer buys a fresh allowance. `/api/health` is never rate limited and never shed, so monitoring stays truthful during an attack.

**Hardening.** Directory listings are disabled; path traversal is rejected after decoding; only `GET/HEAD/POST/PUT/DELETE` are answered (`TRACE`, `PATCH`, `OPTIONS` get `405`); the `Server` banner is stripped; the Host header is validated; and the response headers add `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` and `object-src 'none'` to the existing CSP/nosniff/frame policy.

**Shutdown and operations.** `SIGTERM`/`SIGINT` stop the listener, finish in-flight requests, and release the port. A background task prunes expired sessions and trims the audit log every hour. The Docker image runs unprivileged, read-only, with a health check against the unmetered endpoint.

Every ceiling above is an environment variable (`AXIA_MAX_INFLIGHT`, `AXIA_MAX_INFLIGHT_PER_CLIENT`, `AXIA_RATE_READ`, `AXIA_RATE_WRITE`, `AXIA_RATE_AUTH`, `AXIA_RATE_REGISTER`, `AXIA_RATE_STATIC`, `AXIA_RATE_IDENTITY`, `AXIA_LOCKOUT_THRESHOLD`, `AXIA_LOCKOUT_SECONDS`, `AXIA_HEADER_TIMEOUT`, `AXIA_SOCKET_TIMEOUT`, `AXIA_MAX_BODY_BYTES`, `AXIA_MAX_HEADER_BYTES`, `AXIA_BACKLOG`, `AXIA_DB_TIMEOUT`, `AXIA_TRUSTED_PROXIES`). Set `AXIA_TRUSTED_PROXIES` only when a reverse proxy you control forwards `X-Forwarded-For`; otherwise the header is ignored so clients cannot forge their identity.

**Measured in this repository's test run:** 500 parallel requests in ~0.5 s (≈960 req/s) with zero failures and p95 latency ≈110 ms on a single development process; a deliberately over-tuned instance (`AXIA_MAX_INFLIGHT=4`) shed load with clean `503`s and recovered immediately; the database accepted a write with no wedged lock after every burst.

**What still needs real infrastructure.** In-process memory for limits and lockouts is correct for one process only. Behind multiple instances or on a CDN you still want distributed rate limiting (Redis), a WAF/DDoS layer, PostgreSQL with pooling, and a real ASGI/WSGI server. This code removes the self-inflicted outages; it does not replace edge protection.

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

## Live static site on GitHub Pages

**https://axiasoft.github.io/AxiaPlatform/** is generated from this repository by `tools/build_static.py`.

GitHub Pages serves static files only, so the published site is the real public interface — design, motion
layer, catalog, product pages, About/Services/Contact and the policies — with the product data exported from
the database. Accounts, project requests, support, refunds and the admin console need the Python API, so those
actions open a clear explanation (and `/admin/` shows a gate page) instead of failing silently.

### How it is published

Pages is configured as **Source: Deploy from a branch → `main` → `/`**, so the generated files are committed to
the **repository root** next to the Python application. A project site is always served from
`/<repository>/`, which is why the base path is `/AxiaPlatform/` even though the files sit at the root.
`.nojekyll` at the root stops Jekyll from processing the tree — without it GitHub renders `README.md` as the
homepage and publishes raw `server/` sources.

| Item | Value |
| --- | --- |
| Served from | repository root (`main`, `/`) |
| Base path | `/AxiaPlatform/` |
| Key files | `index.html`, `404.html`, `.nojekyll`, `styles.css`, `app.js`, `static-adapter.js`, `data/products.json` |

Rebuild and publish after changing the catalog, text or styles:

```bash
python3 tools/build_static.py --out . --base /AxiaPlatform/ --origin https://axiasoft.github.io
git add -A && git commit -m "Rebuild static site" && git push origin main
```

The generated files are output — never edit them by hand; edit `public/` instead. Nothing secret is
published: the builder copies only `public/`, omits `admin/admin.js`, `admin/admin.css` and every `*.md`, and
`tools/pages-workflow.yml` fails the build if a database file would ever end up in the output.

### Serving from a user site or a custom domain

If the site ever moves to `<owner>.github.io` or a custom domain, rebuild with `--base /` so absolute links
point at the origin root, and keep `.nojekyll` in place.

### Automatic deployment

`tools/pages-workflow.yml` is a ready-made pipeline (build → `upload-pages-artifact` → `deploy-pages`).
Copy it to `.github/workflows/pages.yml` in the GitHub UI and set Pages **Source** to *GitHub Actions* to use
it. Pushing `.github/workflows/*` needs a token with the `workflows` scope, which is why the file lives in
`tools/`.

## GitHub: source and checks vs hosting

This project is a Python application with a server API and SQLite database. GitHub stores the repository, runs the automated checks, and publishes the static storefront on Pages; **Pages cannot run the backend or the admin login**, which is why the published build gates those features. The CI pipeline is provided at `docs/ci-workflow.yml`; it runs the Python test suite, JavaScript syntax checks and the DOM tests, and fails if a database file is ever committed. Copy it to `.github/workflows/ci.yml` to enable it, or add it through the GitHub UI, because pushing a workflow file requires the token `workflows` permission. To make the repository public or private on GitHub, create an empty repository there, then from this project root run:

```bash
git init -b main
git add .
git commit -m "Add AXIASOFT website"
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
git push -u origin main
```

Replace the remote URL with your own repository URL. A `.gitignore` now excludes databases, `__pycache__`, `.env` files and backups, so runtime data stays out of the repository. To make the site reachable to other people, deploy the container/app to a Python-capable server; pushing source to GitHub does not itself publish a running website.

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
node --check public/effects.js
node --check public/admin/admin.js
python3 -m py_compile server/app.py server/db.py server/provision_admin.py
python3 -m unittest discover -s tests -v
```

The Python suite (26 tests) covers the persistence and security invariants, plus explicit regressions for the write-lock wedge, request-body validation, rate-limit keying, login lockout, and the limiter primitives.

Two optional DOM tests render the real markup, scripts and effects layer in jsdom and assert that the decorative layers appear, that they are hidden from assistive technology, and that `prefers-reduced-motion` users get a calm page with no canvas or spotlight:

```bash
npm install --no-save jsdom
node tests/browser/effects.dom.test.mjs
node tests/browser/admin.dom.test.mjs
```

jsdom is intentionally not a project dependency; these tests are skipped in CI when it is absent. They are not a substitute for a full browser suite or a penetration test.
