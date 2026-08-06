# Authentication and authorization

M6.3 adds account authentication without exposing FastAPI to the browser.

## Local setup

Set these values in `.env` and never commit them:

```dotenv
AUTH_INTERNAL_TOKEN=<long-random-service-secret>
NEXTAUTH_SECRET=<long-random-authjs-secret>
AUTH_INITIAL_ADMIN_USERNAME=admin
AUTH_INITIAL_ADMIN_PASSWORD=<at-least-12-character-password>
AUTH_RATE_LIMIT_PER_MINUTE=10
```

Then run:

```powershell
docker compose up -d postgres api web
docker compose exec -T api alembic upgrade head
docker compose exec -T api python scripts/seed.py
```

The seed is idempotent and creates an administrator only when
`AUTH_INITIAL_ADMIN_PASSWORD` is set. Open `http://localhost:3000/login`.

## Request flow

- Auth.js Credentials Provider sends credentials server-side to FastAPI's internal login endpoint.
- Auth.js stores the session in an encrypted, HttpOnly JWT cookie.
- The Next.js proxy validates the session and signs a short-lived HMAC identity assertion.
- FastAPI validates the assertion and checks the account is still active in PostgreSQL on every request.
- Search, questions, documents, comparisons, and admin endpoints reject missing or invalid assertions.
- The browser never receives `HF_TOKEN`, database credentials, or the internal service secret.

## Roles and administration

Accounts have either `admin` or `user` role. There is no public signup. Administrators can create,
disable, delete, and reset accounts at `/admin`. Ask TaxLens has a per-user in-memory rate limit;
replace it with a distributed limiter before multi-replica production scale.

## Azure

`AUTH_INTERNAL_TOKEN` and `NEXTAUTH_SECRET` are Terraform-managed Key Vault secrets. Container Apps
inject them into the API and web containers through the existing managed identity. Terraform changes
are prepared but intentionally not applied until the local flow is reviewed and approved.
