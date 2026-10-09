# Wise Mesh Continental

Local hackathon prototype for invoice confirmation, multilateral netting, approval and settlement.

## Run

```sh
make up
```

App: http://localhost:3010 · API docs: http://localhost:3011/docs · Postgres: localhost:5434.
Use the demo persona picker on the login page. The demo password is `mesh-demo-2026`.
`make dev` starts the Bun/Svelte and FastAPI reload servers. Bun handles frontend tooling;
the Python backend uses uv. `make reset` **deletes the local database volume** and reseeds it.

## Demo walkthrough (M2 to M5)

1. Log in as Wise ops (`ops@wise.test`). Open **Demo**, choose **Reset demo data**, load the
   worked example, then simulate 100% confirmations. The current window shows 8 eligible invoices.
2. In **Ops console**, close the window with a reason. The first computation produces
   3 transfers totalling €80,000 from invoices totalling €450,000. **Network** shows the gross
   invoice graph and the 3 settlement transfers.
3. Log in as each member A–F, open **Runs**, review the statement, and approve it.
   The run reaches **Approved** after every required approval.
4. As Wise ops, choose **Settle run** in the run monitor. Prepare holds each payer's net payable
   plus fee; commit posts one journal entry. The run is **Settled**, clearing is €0.00, and
   **Run ledger check** reports the hash chain intact.
5. As a member, the run page shows the payment to "Mesh settlement" and its ledger lines.
   **Savings** shows per-run and total savings, with a break-even slider (`POST /v1/estimates`).
   Member A pays €40,078.00 (€40,000 net plus a €78 fee) and saves €234.00.
6. To try ingestion, use a finance or member-admin persona. Open **Invoices → Add invoices**,
   download the CSV template, or create one invoice. The other party answers in **Confirmations**.

Failure paths, all from **Demo** and the run monitor:

- **Funding failure**: mark a payer unable to fund before settling. Prepare excludes it, opens a
  funding case, recomputes and issues new statements; unchanged statements keep their approvals.
  A payer whose balance can't cover its hold is excluded the same way.
- **Expire approvals** removes members who have not approved and recomputes.
- **Abort run** (ops or compliance) releases every hold and returns the invoices to the next window.
- Rejections, expired approvals and funding failures share the recompute cap: the third
  exclusion ends the run in `FALLBACK_GROSS`.
- A changed frozen input or an expired FX lock aborts the run in prepare or commit; any error
  inside commit rolls it back and aborts with every hold released. Calling Settle again after a
  crash resumes from the last completed step and never commits twice.
- With the global (or a participant's) kill switch on, window close and commit are refused.

Above the maker-checker threshold, two different approver/admin users must approve.
Sanctions hits (at freeze and again in prepare) open a compliance case.
Member APIs expose only the caller's invoices, terms and settlement; the counterparty of every
transfer and ledger line is "Mesh settlement", and cross-member resources return 404.
Residuals below the dust threshold are parked per member in SUSPENSE and paid out in the next run.

Also from M6 (Should):

- **Settings** (member admin): payable limit, maker-checker threshold and settlement currency
  (`PATCH /v1/members/me/settings`), plus the team. Limits apply from the next computation; a
  payer over its limit is left out and the rest recompute. The currency can't change while the
  member still has invoices locked in an unfinished run.
- **Withdraw** (member admin or finance user): on the statement, choose **Withdraw invoices**
  (`POST /v1/runs/{id}/withdrawals`). The invoices return to the next window and the run
  recomputes; this shares the recompute cap with rejections.
- **Ring rule**: at freeze, a cycle of equal, round invoices (whole multiples of 1,000) between
  members who joined in the last 90 days is held for review with a RING case. Seeded members A–F
  are established, so the demo datasets never trigger it.
- **Component isolation** (MC-NET-01): each connected component of the invoice graph nets on its
  own. If one fails a check, its invoices go back to the next window with an ENGINE_ALERT case,
  and the others still net.

Statements follow the PRD's statement payload (Money objects, invoices grouped by counterparty,
`instruction`, `approval`, `sha256:` content hash). Databases created before this change hold
statements in the old shape: run **Reset demo data** (or `make reset`) after upgrading.

M0–M5 are implemented. Seeded users keep stable IDs, so open sessions survive a demo reset
(a database seeded before this change logs its sessions out once, at the first reset).

## Verify

```sh
make test-be       # isolated mesh_test database; leaves the app database intact
make test-fe
make lint
make gen-api
make e2e          # requires Playwright Chromium and a running stack; RESETS the demo database
```

`e2e/demo.spec.ts` is the M5 demo script (reset, upload, simulate confirmations, close, approve,
settle, savings). It resets the database first, so it passes run after run:
`bunx playwright test e2e/demo.spec.ts --repeat-each=2`. Logins are rate limited to 30 per IP
per minute, so wait a minute between more than two back-to-back full suite runs.

For local machines with Chrome already installed:

```sh
cd frontend
PLAYWRIGHT_CHANNEL=chrome bunx playwright test
```

The M2/M3 browser smoke test resets the demo database, creates one A/B invoice and closes its window.
The API suite verifies the full golden scenario, privacy, corrections, screening, switches,
approval roles, stale hashes, carried approvals and recomputation limits. The settlement suites
cover holds, commit, clearing at zero, funding failure, abort, kill switches, input tampering,
FX locks, crash recovery (exactly one commit), dust carry-forward, savings and estimates.

CSV uploads use `POST /v1/invoices/uploads` with a raw UTF-8 CSV body and `Content-Type: text/csv`.
Mutations require `X-Requested-With: mesh-web` and `Idempotency-Key` (except login/logout).
After API changes, regenerate and keep `backend/openapi.json` and
`frontend/src/lib/api/schema.d.ts` together.

Aria was here
