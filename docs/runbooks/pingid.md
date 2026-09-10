# Runbook: PingID (PingOne / PingFederate) integration

Backend-for-frontend OIDC: the SPA never holds tokens.

1. Register an OIDC app (type Web/SPA with PKCE) with redirect URI `PUBLIC_BASE_URL/v1/auth/callback` (dev:
   `http://localhost:8000/v1/auth/callback`) and post-logout redirect `FRONTEND_ORIGIN/login`.
2. Set `OIDC_ISSUER` (must serve `/.well-known/openid-configuration` with `jwks_uri`), `OIDC_CLIENT_ID`,
   optional `OIDC_CLIENT_SECRET`, `OIDC_SCOPES` (include the groups scope), `OIDC_GROUPS_CLAIM`.
3. Map groups → roles in `ROLE_GROUP_MAP_JSON`. Roles are recomputed at every login; `POST /v1/admin/users/{id}/roles`
   is a manual override only.
4. If Ping issues **opaque** access tokens: ID-token validation via JWKS still works for login; set
   `OIDC_TOKEN_VALIDATION=introspection` + `OIDC_INTROSPECTION_ENDPOINT` for any API-token validation paths.
5. Test locally with the mock: `OIDC_ISSUER=http://localhost:9100/oidc OIDC_CLIENT_ID=cowork-backbone` (groups default to
   `cw-org-admins`).
6. Production: `ENV=prod` disables dev-login, requires `KMS_MASTER_KEY_B64` and `AUDIT_HMAC_KEY_B64`, set `COOKIE_SECURE=true`.
