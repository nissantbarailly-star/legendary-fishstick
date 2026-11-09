# Architecture: Office Desk 1

## Goal and scope
A multi-user internal template catalog. Employees authenticate with the company identity provider, discover approved blank starting files, and create working copies in approved storage. The canonical source must never be directly opened or exposed by the UI.

## Components

- **React + TypeScript / Vite**: responsive dashboard, catalog search, department views, rollout progress and admin UI. It calls same-origin `/api` endpoints with the session cookie.
- **Flask**: OIDC session, CSRF checks on state-changing endpoints, input validation, group-gated admin operations, business logic and audit records.
- **PostgreSQL / SQLAlchemy**: departments, templates (opaque source key only), change requests, rollout tasks and template-copy audit records.
- **Company identity provider (OIDC)**: authentication. Production must issue/return a trusted `groups` claim and configure `OIDC_ADMIN_GROUP_ID`; map department-owner groups before granting departmental write access.
- **Microsoft Graph storage adapter (optional)**: app-only service for copying from a configured source drive to an approved destination folder. Use a dedicated Entra application and least-privilege SharePoint permissions, preferably `Sites.Selected` with explicit site grants. Secrets belong in a secret manager, never in the browser or repository.

## Request flow: create a copy
1. User signs in through OIDC; Flask validates the protocol response and creates an HTTP-only session.
2. React obtains a CSRF token and submits `POST /api/templates/{id}/copy` with the session and token.
3. Flask checks identity, template activity, configured opaque source key, and request fields.
4. Server-side Graph adapter resolves the item ID using configured drive IDs and copies it to the fixed destination folder. It never accepts a source URL or arbitrary destination from the client.
5. Flask stores an audit row and returns only the new copy's name/link.
6. The UI shows a link to the created copy. If storage is not configured, copy fails closed with a service-unavailable response.

## Data model

- `Department`: stable ID, display name, category, description, owner role and active flag.
- `Template`: stable ID, name, department FK, file type, description, opaque storage key, active flag.
- `ChangeRequest`: department, bounded request text/type, requester subject/email, status and timestamp.
- `RolloutTask`: phase, task, accountable role, completion state and last editor.
- `TemplateCopy`: template, authenticated subject, timestamp and provider destination item ID. Never store access tokens.

## API summary

- `GET /api/me`, `GET /api/csrf`
- `GET /api/departments`, `GET /api/templates`
- `POST /api/templates/{id}/copy`
- `POST /api/requests`; `GET /api/requests` (admin group)
- `GET /api/rollout`; `PATCH /api/rollout/{id}` (admin group)
- `POST /api/admin/departments`, `POST /api/admin/templates` (admin group)
- `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout`

## Authorization and security boundaries

Login is not authorization. Admin mutations and request listing are gated by a configured identity group. Before deployment, verify group claim provenance/overage behavior with your IdP and implement department-owner role mapping. Enforce all permissions in Flask, not React. Keep session cookies HTTP-only, secure in production, same-site; deploy behind HTTPS and a trusted proxy. Use CSRF tokens on state-changing requests, restrictive CORS (same-origin preferred), rate limits, audit retention, and secure headers. Validate catalog writes and restrict storage source/destination to administrator-approved records. Use short-lived Graph tokens, managed identity or secret-vault-backed credentials, and provider access limited to required sites.

## Delivery phases

1. Confirm identity provider/group claims, storage provider/site, copy destination policy and data-retention requirements.
2. Provision PostgreSQL and secrets; add Alembic migrations; deploy API and UI behind HTTPS.
3. Seed the complete owner-approved catalog, with source item IDs entered by authorized admins.
4. Grant and test storage permissions on non-production files; test copy creation and audit records.
5. Add department-owner workflows, review/approval states, notifications, telemetry and KPI aggregation.
6. Run accessibility/security review, backup/restore exercise, load testing and incident-response checks.

## Current scaffold limitations

This is a starter, not a certified production system. Demo seed data is incomplete. OIDC group claims vary by provider; the configured admin group must be verified. The Graph adapter supports a single configured source drive and destination folder; validate the tenant's Graph copy behavior and permissions in a test site. `db.create_all()` is development bootstrap only; production schema changes require migrations. Admin UI and owner-specific approvals remain to be built. Do not enable real users until those items are complete.
