Updated todo list

The remaining work is concentrated in workflow completion and production readiness, not the core inventory domain. The highest-priority unfinished slice is the frontend for manager reallocation and approved substitutions; the supporting backend rules exist, and substitute-candidate discovery was just added and tested.



**Core Workflow Gaps**
1. **Finish substitution UI**
   - Approved-substitute candidate endpoint is implemented and tested.
   - Add candidate selection, quantity, reason, and confirmation to the claimed pick screen.
   - Display the explicit fulfillment UOM now returned by allocations.

2. **Add manager reallocation UI**
   - Backend reallocation, locking, auditing, and notifications already exist.
   - Add source allocation, target backorder, quantity, and required-reason controls to the fulfillment queue.

3. **Complete staging workflow**
   - Staging locations can be configured.
   - The actual action for moving picked material into staging before handoff is still missing.

4. **Complete request conveniences**
   - Repeat a previous request.
   - Create requests from item QR scans.
   - Improve job and cost-code selection once authoritative Spectrum data is available.
   - Confirm whether submitted-request editing needs more than cancellation/reallocation.

5. **Bulk imports**
   - Catalog and item classification import.
   - Employee-recipient directory import.
   - Opening-balance and location import with dry-run validation.

6. **Reporting**
   - Dedicated request/order reports.
   - Withdrawal and exception reports.
   - Export support where operationally required.

**Administration**
- User creation, role assignment, password reset, account disabling, session invalidation, and self-lockout protection are now implemented.
- Location/grid, QR-label, device, catalog, and reconciliation administration exist.
- Still needed:
  - Warehouse-level settings and application configuration UI.
  - Identity-provider configuration after IT confirms the provider.
  - Spectrum capability/configuration controls after the real contract is known.
  - Display orientation configuration for the warehouse grid.

**Production Integration**
- Implement the real Spectrum adapter only after authorized documentation, credentials, sandbox access, identifiers, and transaction rules are supplied.
- Integrate the confirmed corporate identity provider, preferably OIDC.
- Integrate the actual employee-directory source.
- Do not invent these contracts from assumptions.

**Security And Operations**
- Authentication, QR, and mutation rate limiting.
- Correlation IDs and sanitized structured logging.
- Metrics and alerts for API/database health, outbox age, reconciliation differences, backups, and administrative activity.
- CI for backend/frontend tests, linting, types, migrations, dependency scans, secret scans, container scans, and Snyk.
- Encrypted backup and restore scripts plus a completed restore drill.
- Runbooks for outages, failed synchronization, lost devices, incorrect stock, rollback, and database recovery.
- Threat model, retention policies, and named operational owners.

**Verification And Delivery**
- Broader authorization tests for every role and mutation.
- PostgreSQL concurrency tests for allocation, claims, counts, and withdrawals.
- Property tests for quantities and UOM precision.
- React component and accessibility tests.
- Playwright desktop/mobile workflow and overlap checks.
- Physical QR tests on target devices.
- Offline-shift, Spectrum-outage, and backlog-recovery exercises.
- Rebuild the containers with the latest source, apply migrations, and run end-to-end smoke tests.
- Replace the placeholder `README.md` with setup, operation, architecture, credentials, migration, backup, and troubleshooting documentation.

The next implementation order should be: **substitution UI → reallocation UI → staging workflow → imports/reporting → CI/security/operations → complete container and Playwright validation**.

Created 2 todos