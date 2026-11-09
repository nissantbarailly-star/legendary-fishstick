# Office Desk 1

A starter for the multi-user Office Desk workspace: React + TypeScript frontend, Flask API, SQLAlchemy persistence, company OIDC sign-in, and a server-side template-copy boundary.

## Status and important setup notes

This repository now contains the application scaffold, not a fully configured company deployment. Before using it with real users or documents:

1. Configure your identity provider's OIDC client and exact issuer/discovery URL.
2. Implement and configure the approved company storage provider in `backend/storage.py`. The copy API deliberately returns `503` until this is done; it never exposes or opens a canonical source URL.
3. Configure a production database, HTTPS, secret management, backups, and migrations.
4. Populate the catalog with approved canonical source keys. Demo entries have no source keys and cannot be copied.
5. Add organization/group-based authorization for catalog administration and any department-specific restrictions.

The scaffold authenticates users through OIDC but does not yet enforce company groups or admin roles. Do not treat login alone as authorization for administrative actions.

## Layout

- `frontend/`: Vite, React, TypeScript UI.
- `backend/`: Flask API, SQLAlchemy models, OIDC sign-in, and storage adapter boundary.
- `compose.yaml`: local PostgreSQL and application development services.

## Local development

Requirements: Docker Compose and a company OIDC test client (or configure an OIDC test provider).

1. Copy `.env.example` to `.env` and set `SECRET_KEY`, `OIDC_ISSUER`, `OIDC_CLIENT_ID`, and `OIDC_CLIENT_SECRET`. Register `http://localhost:5000/auth/callback` as the callback URL in the OIDC provider.
2. Run `docker compose up --build`.
3. Visit `http://localhost:5173` and sign in. The API is available at `http://localhost:5000`.

Without OIDC settings, the app/API can start but sign-in is unavailable. The copy action remains unavailable until a trusted storage adapter is implemented and configured.

## API outline

- `GET /api/me` — current signed-in user.
- `GET /api/templates` — catalog list (sign-in required).
- `POST /api/templates/<id>/copy` — request a copy in approved storage (sign-in required; unavailable until a provider is configured).
- `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout` — OIDC session flow.
- `GET /health` — basic health check.

The copy route accepts an optional JSON `name` and invokes the storage provider on the server. It does not return the canonical source location. The provider must authorize the destination, copy the file using a service identity or delegated user access, and return a link to the new copy.

## Production checklist

- Use HTTPS and set `SESSION_COOKIE_SECURE=true`; keep cookies HTTP-only and same-site.
- Use a strong random `SECRET_KEY` from a secret manager, never a committed `.env`.
- Use a managed PostgreSQL database and Alembic migrations; `create_all()` is only used for this starter.
- Implement the storage provider for your approved provider (for example, Microsoft 365 or Google Workspace), with least-privilege scopes, destination allowlists, and audit events.
- Add OIDC group/role mapping and server-side authorization for every privileged action.
- Add CSRF protection for state-changing session-authenticated endpoints before public deployment.
- Add rate limiting, structured logs, monitoring, retention policies, and tests for auth, permissions, and copy behavior.
- Populate real catalog records only after source files and owners are approved.
