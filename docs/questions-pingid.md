# Questions for the Ping / identity team

1. PingOne or PingFederate? Issuer URL with OIDC discovery (`/.well-known/openid-configuration`) and JWKS.
2. Can we register the app as a public client (SPA/Native) using **Authorization Code + PKCE**, or is a confidential client
   with secret required? (Our backend-for-frontend can do either.)
3. Are access tokens **JWT or opaque**? (Opaque ⇒ introspection endpoint + client credentials for it.)
4. Which claim carries **group/role** membership (`groups`, `memberOf`, …) and the naming convention, so we can map to
   `org_admin | workspace_admin | team_lead | auditor | developer`? Is the claim in the ID token or only via UserInfo?
5. Refresh-token policy and session lifetime; idle timeout expectations for the app session cookie.
6. **End-session** (RP-initiated logout) endpoint and allowed post-logout redirect URIs.
7. Allowed redirect URIs for local dev (`http://localhost:8000/v1/auth/callback`) and the deployed origin.
8. MFA/step-up requirements for admin roles; can we get an `acr`/`amr` claim to enforce it for the admin console?
