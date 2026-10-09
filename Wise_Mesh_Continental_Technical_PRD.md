# Wise Mesh Continental — Technical PRD

Oct 9, 2026 · Alp Gençgil

## Overview and scope

We are building a working hackathon prototype of Wise Mesh Continental: a multilateral invoice-netting and settlement add-on for Wise Business. The backend is Python (FastAPI), the frontend is SvelteKit with Tailwind, and the UI follows the Wise visual template.

Members upload invoices, counterparties confirm them, and at each window close the system cancels offsetting obligations across the member graph. Only the residual is settled, on an internal double-entry ledger. This PRD covers only what the team needs to plan and write the code; legal, commercial and production-infrastructure topics stay in the technical description.

### What we build and what we mock

| **Capability**          | **Prototype build**                                                                                | **Depth**                      |
|-------------------------|----------------------------------------------------------------------------------------------------|--------------------------------|
| Invoice ingestion       | CSV upload with a template, manual form, synthetic data generator                                  | Real, no accounting connectors |
| Entity resolution       | Counterparties matched against pre-seeded legal entities; mock invitation screen                   | Simplified                     |
| Confirmation            | Two-sided confirm, dispute and correct flow; a demo endpoint simulates counterparty replies        | Real                           |
| Windows                 | One open window; an admin "Close window" button freezes the eligible set                           | Simplified                     |
| FX                      | Static rate table, snapshot at freeze, lock at approval                                            | Simplified                     |
| Netting engine          | Cycle cancelling, net positions, greedy matching, zero-sum improvement heuristic, invariant checks | Real                           |
| Risk and compliance     | Mock sanctions list and one ring-detection rule                                                    | Simplified                     |
| Pricing                 | Gain-share fee and savings calculator with a break-even slider                                     | Real                           |
| Statements and approval | Per-member statements; approve, reject, withdraw; maker-checker                                    | Real                           |
| Settlement              | Two-phase prepare and commit with holds, simulated funding failure, abort path                     | Real, internal ledger only     |
| Ledger                  | Append-only double-entry tables with a zero-clearing check                                         | Real                           |
| Privacy                 | Per-member scoping on every query; "Mesh settlement" is the only visible counterparty on transfers | Real                           |
| Operations              | Global and per-member kill switch, audit log                                                       | Basic                          |

Out of scope for the build: real accounting connectors, KYB, the real Wise ledger and payment rails, external payouts, confidential computing, ML models, partner API, hedging, early netting, regulatory reporting and non-English UI.

### Invariants the code must enforce

| **ID** | **Invariant**                                                                                                                             | **Enforced in**                          |
|--------|-------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------|
| G1     | Net positions in a run sum to exactly zero per currency                                                                                   | Engine validation step                   |
| G2     | Each member's position after settlement equals paying every included invoice gross, fees aside                                            | Engine validation and property tests     |
| G4     | A run commits fully in the ledger or not at all                                                                                           | Commit runs as one database transaction  |
| G5     | Nothing is netted without both parties confirming the same invoice version, and nothing settles without approval of the current statement | Eligibility query and the prepare step   |
| G6     | Every included invoice has exactly one outcome, and cancelled plus residual equals outstanding                                            | invoice_outcomes table and validation    |
| G7     | A member sees only its own invoices, counterparties and settlement                                                                        | Repository scoping and API tests         |
| G8     | No run settles with a sanctioned or restricted member                                                                                     | Screening at freeze and again in prepare |
| G9     | Any failure ends in re-computation, gross fallback, or abort with every hold released                                                     | Run state machine                        |

Requirement IDs reuse the description's area codes (MC-NET, MC-SET and so on). Priority is Must (needed for the demo), Should (planned) or Could (only if time allows).

## Architecture and stack

One FastAPI service, built as a modular monolith, owns all logic and data. The SvelteKit app is a static single-page app that only calls the `/v1` API, PostgreSQL is the single store, and Docker Compose runs everything. This matches the prototype column of the description (FastAPI, PostgreSQL, in-process queue, append-only ledger table) with Svelte replacing React.

![System architecture: 1 service, 4 module groups, 1 database](Wise_Mesh_Continental_Technical_PRD_media/rId23.png)

The browser never touches the database or holds business rules; every invariant is enforced inside the FastAPI service.

### Stack

| **Layer**          | **Choice**                                                        | **Notes**                                               |
|--------------------|-------------------------------------------------------------------|---------------------------------------------------------|
| Backend language   | Python 3.12                                                       | Managed with uv                                         |
| API framework      | FastAPI + Uvicorn                                                 | OpenAPI schema drives the frontend client               |
| Schemas            | Pydantic v2, pydantic-settings                                    | Strict models on every request                          |
| Database           | PostgreSQL 16                                                     | Same engine for dev, tests and demo                     |
| ORM and migrations | SQLAlchemy 2.0 (sync sessions, psycopg 3) + Alembic               | Row locks with `SELECT ... FOR UPDATE` in settlement    |
| Graph work         | NetworkX                                                          | Components and cycle finding; amounts stay Python `int` |
| Background work    | Outbox table + in-process asyncio worker                          | No Kafka, Celery or Redis                               |
| Auth               | argon2id password hashes, signed JWT in an httpOnly cookie        | Seeded users; no sign-up or KYB                         |
| Frontend           | SvelteKit 2, Svelte 5, TypeScript, adapter-static                 | SSR off; no server routes                               |
| Styling            | Tailwind CSS 4 with Wise-template tokens                          | Inter, self-hosted                                      |
| Frontend libraries | Bits UI, Lucide, TanStack Query, Zod, Cytoscape.js, openapi-fetch | See the frontend section                                |
| Tests              | pytest, Hypothesis, httpx, Vitest, Playwright                     | See the testing section                                 |
| Quality            | Ruff, mypy, ESLint, Prettier, svelte-check                        | Run in CI                                               |
| Runtime            | Docker Compose: db, api, web                                      | GitHub Actions for CI                                   |

### Repository layout

    mesh/
      backend/
        app/
          main.py             # app factory, routers, middleware, lifespan worker
          core/               # config, db, security, errors, ids, money, hashing
          modules/            # one package per domain module (see Backend)
          events/             # outbox writer and worker
        migrations/           # Alembic
        tests/                # unit, property, api, scenarios
        pyproject.toml
      frontend/
        src/
          app.css             # Tailwind @theme tokens
          lib/                # api client, components, features, money helpers
          routes/             # (public), (member), (admin) route groups
        package.json
      docker-compose.yml
      .github/workflows/ci.yml

## Functional requirements

The prototype has 55 requirements. The 39 Must items form the demo path: upload, confirm, close the window, net, approve and settle.

### Members and access (MC-ONB)

| **ID**    | **Requirement**                                                                                                                             | **Acceptance criteria**                                                                                      | **Priority** |
|-----------|---------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|--------------|
| MC-ONB-01 | Seed script creates member businesses, legal entities and users with roles: member admin, finance user, approver, Wise ops, Wise compliance | The worked-example scenario creates members A to F; each seeded user can log in and sees only its own member | Must         |
| MC-ONB-02 | Each member stores a per-run payable limit, a maker-checker threshold and a settlement currency, editable by the member admin               | A payer whose net payable exceeds its limit is excluded and the run re-computes                              | Should       |
| MC-ONB-03 | A member must accept the current agreement version before its invoices can enter a run                                                      | A member without acceptance is skipped at freeze with reason AGREEMENT_PENDING                               | Could        |

### Invoice ingestion (MC-ING)

| **ID**    | **Requirement**                                                                                                                              | **Acceptance criteria**                                                                                                                                          | **Priority** |
|-----------|----------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------|
| MC-ING-01 | CSV upload against a downloadable template: invoice_number, issuer_tax_id, payer_tax_id, currency, amount, outstanding, issue_date, due_date | Invalid rows are rejected with row number, field and reason; valid rows are stored as IMPORTED; amounts parse straight to integer minor units with no float step | Must         |
| MC-ING-02 | Manual form for a single invoice                                                                                                             | Same validation as CSV; creates version 1                                                                                                                        | Should       |
| MC-ING-03 | Synthetic generator with member count, invoice count, currencies, cycle density and seed                                                     | The same parameters and seed produce the same invoice set                                                                                                        | Must         |
| MC-ING-04 | Fingerprint = SHA-256 over normalised issuer, payer, invoice number, issue date, currency and gross amount                                   | An exact duplicate is rejected with DUPLICATE_INVOICE                                                                                                            | Must         |
| MC-ING-05 | Near-duplicate check: same parties and amount with a similar invoice number                                                                  | Flagged for review, never merged automatically                                                                                                                   | Could        |

### Counterparties (MC-ENT)

| **ID**    | **Requirement**                                                                                  | **Acceptance criteria**                                                           | **Priority** |
|-----------|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|--------------|
| MC-ENT-01 | Match the counterparty by tax ID or registration number against seeded legal entities            | Exact match sets MATCHED; no match sets UNMATCHED and the invoice is never netted | Must         |
| MC-ENT-02 | Invite an unmatched counterparty from the invoice screen (record and mock screen; no email sent) | Invitation stored with status and expiry; the invoice stays UNMATCHED             | Could        |

### Confirmation and disputes (MC-CNF)

| **ID**    | **Requirement**                                                                                                | **Acceptance criteria**                                                                                                                                            | **Priority** |
|-----------|----------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------|
| MC-CNF-01 | The uploading party's side counts as confirmed; a MATCHED invoice creates a request in the other party's inbox | Invoice moves to PENDING_CONFIRMATION; the request shows amount, currency, due date and invoice number                                                             | Must         |
| MC-CNF-02 | The other party can confirm, dispute with a reason code, or propose a correction                               | Confirm sets CONFIRMED; dispute sets DISPUTED and excludes it; a correction creates a new version, voids earlier confirmations and returns to PENDING_CONFIRMATION | Must         |
| MC-CNF-03 | Demo endpoint simulates counterparty replies with a confirm rate and a dispute rate                            | Replies are stored with method SIMULATED and appear in the audit log                                                                                               | Must         |
| MC-CNF-04 | A confirmation applies to one invoice version only                                                             | An invoice is eligible only when both parties confirmed its current version                                                                                        | Must         |
| MC-CNF-05 | Auto-confirm when the counterparty uploads an invoice with the same fingerprint                                | The second upload confirms instead of creating a duplicate                                                                                                         | Could        |

### Windows and eligibility (MC-WIN)

| **ID**    | **Requirement**                                                                                                                                                     | **Acceptance criteria**                                                                                                  | **Priority** |
|-----------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|--------------|
| MC-WIN-01 | Exactly one OPEN window at a time; Wise ops closes it with a button                                                                                                 | Close freezes the eligible set, stores its input hash, moves invoices to LOCKED_IN_RUN and creates a run                 | Must         |
| MC-WIN-02 | Eligibility: current version confirmed by both sides, not disputed, both members ACTIVE or RESTRICTED, rate available, kill switch off, due date within the horizon | Every excluded invoice gets a reason code visible to its two parties; the horizon defaults to all due dates in demo mode | Must         |

### Currency and FX (MC-FX)

| **ID**   | **Requirement**                                                                                                 | **Acceptance criteria**                                                            | **Priority** |
|----------|-----------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|--------------|
| MC-FX-01 | Static rate table for EUR, USD, HUF, GBP and CNY with source and timestamp, copied to the run at freeze         | A pair without a rate has its cross-currency edges excluded                        | Must         |
| MC-FX-02 | Net each currency first, then convert residuals into each member's settlement currency at the snapshot rate     | Every conversion is stored as its own leg with its rate and shown on the statement | Must         |
| MC-FX-03 | Lock the rate at approval, with an expiry                                                                       | A commit after expiry aborts the run and re-prices it                              | Should       |
| MC-FX-04 | One rounding rule (half-even) plus largest-remainder allocation; residuals below a dust threshold carry forward | The sum of positions stays exactly zero after any conversion                       | Must         |

### Netting engine (MC-NET)

| **ID**    | **Requirement**                                                                                                         | **Acceptance criteria**                                                           | **Priority** |
|-----------|-------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|--------------|
| MC-NET-01 | Partition the graph by currency, then by connected component                                                            | Components compute independently; one failing component does not block the others | Must         |
| MC-NET-02 | Cancel directed cycles by their minimum edge until the graph is acyclic, recording each cancellation per invoice        | Cancellation records sum to each invoice's cancelled amount                       | Must         |
| MC-NET-03 | Compute signed net positions per member and currency (positive = receives)                                              | The engine asserts the sum is zero before continuing                              | Must         |
| MC-NET-04 | Greedy matching: pair the largest payer with the largest receiver                                                       | At most k - 1 transfers for k members with non-zero positions                     | Must         |
| MC-NET-05 | Improvement: exact-amount pairs first, then zero-sum subsets of size 3 to 4, within a time budget                       | Never more transfers than greedy; stops at the budget with the best valid plan    | Should       |
| MC-NET-06 | Validation: zero sum per currency, plan clears every position, one outcome per invoice, no zero or negative transfers   | A failed check discards the result, falls back to greedy and raises an alert      | Must         |
| MC-NET-07 | Determinism: sorted inputs, ID tie-breaks, seed derived from the input hash, recorded algorithm version and result hash | The same frozen input run twice gives an identical result hash                    | Must         |
| MC-NET-08 | Golden scenario from the description's worked example                                                                   | 8 invoices worth 450 become 3 transfers worth 80 (A, C and E pay F)               | Must         |

### Risk and compliance (MC-RSK)

| **ID**    | **Requirement**                                                                                 | **Acceptance criteria**                                                                | **Priority** |
|-----------|-------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|--------------|
| MC-RSK-01 | Mock sanctions list, screened at freeze and again in prepare                                    | A listed member is excluded before compute, a case opens and its invoices are released | Must         |
| MC-RSK-02 | Ring rule: flag a cycle whose members all joined recently and whose amounts are round and equal | The cycle's invoices are excluded with decision HOLD_FOR_REVIEW and a case opens       | Should       |
| MC-RSK-03 | Global and per-member kill switch                                                               | When on, window close and commit are refused; every change is audited with a reason    | Must         |

### Pricing and savings (MC-FEE)

| **ID**    | **Requirement**                                                                                                                            | **Acceptance criteria**                                                            | **Priority** |
|-----------|--------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|--------------|
| MC-FEE-01 | Gain-share: baseline = gross included value x standard rate; actual = residual x standard rate + Mesh fee; Mesh fee = fee share of savings | Rate and fee share come from config; the price version is printed on the statement | Must         |
| MC-FEE-02 | Allocate the total fee in proportion to each member's savings, with largest-remainder rounding                                             | Allocated fees sum to the total; no member's fee exceeds its savings               | Must         |
| MC-FEE-03 | Break-even slider: change fee share and standard rate and see savings update                                                               | Calls POST /v1/estimates; no stored data changes                                   | Should       |

### Statements and approval (MC-APR)

| **ID**    | **Requirement**                                                                                                                                                             | **Acceptance criteria**                                                                 | **Priority** |
|-----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|--------------|
| MC-APR-01 | One statement per member per computation: own invoices by counterparty, gross payable and receivable, cancelled, net, FX legs, fee, savings and debit or credit instruction | Statement JSON is canonicalised and hashed with SHA-256; no other member's data appears | Must         |
| MC-APR-02 | Approve or reject a statement; the approval carries the content hash the user saw                                                                                           | An approval with a stale hash is refused with STATEMENT_CHANGED                         | Must         |
| MC-APR-03 | Withdraw specific invoices from the run                                                                                                                                     | Triggers re-computation and new statements for affected members                         | Should       |
| MC-APR-04 | Maker-checker: a net payable above the member's threshold needs a second, different approver                                                                                | The same user approving twice is refused                                                | Should       |
| MC-APR-05 | Approval deadline; non-responders are removed (demo button "Expire approvals")                                                                                              | Removal triggers re-computation                                                         | Should       |
| MC-APR-06 | Re-computation is capped at 2 re-runs; a third exclusion ends in FALLBACK_GROSS                                                                                             | Members whose statement hash changed must approve again                                 | Must         |

### Settlement and ledger (MC-SET, MC-LED)

| **ID**    | **Requirement**                                                                                                       | **Acceptance criteria**                                                                        | **Priority** |
|-----------|-----------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------|--------------|
| MC-SET-01 | Prepare: re-check input hash, member status, screening and approvals; place a hold per payer for net payable plus fee | Total held equals total payable before commit can start                                        | Must         |
| MC-SET-02 | Commit: one database transaction posts payer to clearing, clearing to receiver, fees and FX legs                      | The run's clearing account is zero after commit; any error rolls back everything               | Must         |
| MC-SET-03 | Demo funding failure: mark a payer as unable to fund                                                                  | The payer is excluded, the run re-computes and new statements are issued                       | Must         |
| MC-SET-04 | Abort releases every hold and returns invoices to CONFIRMED for the next window                                       | No active holds remain for an aborted run                                                      | Must         |
| MC-SET-05 | Idempotency key per run, member and step                                                                              | Repeating prepare or commit has no extra effect                                                | Must         |
| MC-SET-06 | Record invoice outcomes SETTLED_BY_NETTING or SETTLED_BY_TRANSFER                                                     | Every locked invoice ends with exactly one outcome                                             | Must         |
| MC-LED-01 | Append-only double-entry ledger with member balance, hold, clearing, FX conversion, fee revenue and suspense accounts | Postings of every journal entry sum to zero per currency; no UPDATE or DELETE on ledger tables | Must         |
| MC-LED-02 | Hash chain: each journal entry stores the previous entry's hash                                                       | An admin check walks the chain and reports any break                                           | Should       |
| MC-LED-03 | Seeded opening balances per member and currency                                                                       | Balances in the UI are derived from postings                                                   | Must         |

### Privacy, audit and experience (MC-PRV, MC-OPS, MC-UX)

| **ID**    | **Requirement**                                                                                                     | **Acceptance criteria**                                                    | **Priority** |
|-----------|---------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|--------------|
| MC-PRV-01 | Every member-facing query is scoped by the member ID in the session                                                 | Requesting another member's invoice, run detail or statement returns 404   | Must         |
| MC-PRV-02 | Transfers and ledger lines show "Mesh settlement" as the counterparty                                               | No member can see which other member paid or received its residual         | Must         |
| MC-OPS-01 | Append-only audit log for every state change and every Wise staff action, with a reason code                        | Any run can be traced from its audit events alone                          | Must         |
| MC-UX-01  | In-app notifications for confirmation requests, statement ready, re-computation, funding needed and settlement done | Unread count in the header; no email in the prototype                      | Should       |
| MC-UX-02  | Admin network view of the whole graph; members see only their own counterparties                                    | The graph toggles between gross invoice edges and the settlement transfers | Should       |

## Frontend (SvelteKit + Tailwind)

The frontend is a SvelteKit single-page app built with adapter-static and SSR switched off, so every rule stays in the Python API. It reproduces the Wise template through one set of Tailwind tokens; no page sets its own colours, radii or font sizes.

### Setup

| **Concern**     | **Choice**                                                                                                                                                   |
|-----------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Framework       | SvelteKit 2 with Svelte 5 runes, TypeScript strict                                                                                                           |
| Rendering       | `adapter-static` with `fallback: 'index.html'`; `export const ssr = false` in the root `+layout.ts`; no `+page.server.ts` or `+server.ts` files              |
| API access      | Dev: Vite proxies `/v1` to the API. Compose: nginx serves the build and proxies `/v1`. Same origin, so no CORS and the session cookie just works             |
| API client      | Types generated from FastAPI's OpenAPI schema with `openapi-typescript`; calls through `openapi-fetch`; every state-changing call sends an `Idempotency-Key` |
| Server state    | TanStack Query for Svelte; run and statement screens poll every 5 s while a run is active                                                                    |
| Forms           | Zod schemas mirror the Pydantic models for instant field errors; the API stays the source of truth                                                           |
| UI primitives   | Bits UI for accessible dialogs, tabs, selects, tooltips                                                                                                      |
| Icons           | Lucide, Svelte package                                                                                                                                       |
| Font            | Inter, self-hosted through `@fontsource-variable/inter`                                                                                                      |
| Network graph   | Cytoscape.js                                                                                                                                                 |
| Package manager | pnpm                                                                                                                                                         |

### Routes

| **Route**                | **Screen**         | **Who**                    | **Key elements**                                                                                     |
|--------------------------|--------------------|----------------------------|------------------------------------------------------------------------------------------------------|
| `/`                      | Landing            | Public                     | Hero with display type, how netting works, worked-example savings, Log in                            |
| `/login`                 | Log in             | Public                     | Email and password; persona picker in demo mode                                                      |
| `/dashboard`             | Dashboard          | Member                     | Savings meter, current window, open actions, balances by currency                                    |
| `/invoices`              | Invoices           | Member                     | Receivable and payable tabs, status filters, confirmation state                                      |
| `/invoices/upload`       | Upload             | Finance user, member admin | Template download, dropzone, row-level errors                                                        |
| `/invoices/[id]`         | Invoice detail     | Member                     | Versions, confirmations, outcome, audit trail                                                        |
| `/confirmations`         | Confirmation inbox | Finance user, member admin | Terms, Confirm, Dispute with reason, Propose correction                                              |
| `/counterparties`        | Counterparties     | Member                     | Matched and unmatched, Invite                                                                        |
| `/runs` and `/runs/[id]` | Runs               | Member                     | State timeline, own position, approvals, re-computations                                             |
| `/statements/[id]`       | Netting statement  | Member                     | Plain-language summary first, then gross vs net, FX legs, fee and savings; Approve, Reject, Withdraw |
| `/savings`               | Savings            | Member                     | Per-run and cumulative savings, break-even slider                                                    |
| `/settings`              | Settings           | Member admin               | Limits, maker-checker threshold, settlement currency, team                                           |
| `/admin`                 | Ops console        | Wise ops, Wise compliance  | Close window, run monitor, settle or abort, kill switches, cases, ledger check, audit log            |
| `/admin/network`         | Network graph      | Wise ops                   | Whole graph before and after netting                                                                 |
| `/admin/demo`            | Demo controls      | Wise ops, demo mode only   | Reset, seed scenario, generate data, simulate replies, funding failure, expire approvals             |

### Colour tokens

These are the publicly observed Wise values from our earlier research; verify them against wise.design before the demo.

| **Token**                      | **Hex**            | **Use**                                            |
|--------------------------------|--------------------|----------------------------------------------------|
| `brand-primary`                | \#9FE870           | Primary buttons, active states, savings highlights |
| `brand-forest`                 | \#163300           | Text and icons on brand-primary                    |
| `content-primary`              | \#0E0F0C           | Headings and primary text                          |
| `content-secondary`            | \#454745           | Body text                                          |
| `content-tertiary`             | \#868685           | Captions, helper text                              |
| `brand-pale`                   | \#E2F6D5           | Selected rows, success backgrounds                 |
| `background-neutral`           | \#E8EBE6           | Section backgrounds, neutral chips                 |
| `background-screen`            | \#FFFFFF           | Page and cards                                     |
| `sentiment-positive`           | \#054D28           | Success text, money received                       |
| `sentiment-warning`            | \#FFD11A           | Pending states, deadlines                          |
| `sentiment-negative`           | \#D03238           | Errors and disputes only, never ordinary payables  |
| `accent-orange`, `accent-cyan` | \#FFC091, \#38C8FF | Illustrations and graph highlights only            |

### Typography tokens

Product screens use only these 14 px and 16 px Inter roles; emphasis comes from weight, not size. Large display type appears only in the landing hero.

| **Token**           | **Weight**                | **Size / line height** | **Letter spacing** | **Paragraph spacing** | **Use**                            |
|---------------------|---------------------------|------------------------|--------------------|-----------------------|------------------------------------|
| `title-group`       | Medium 500                | 14 / 20 px             | 1.5%               | not specified         | Section labels that split a screen |
| `body-large`        | Regular 400               | 16 / 24 px             | -0.5%              | 8 px                  | Primary body text, form values     |
| `body-large-bold`   | Semi Bold 600             | 16 / 24 px             | 0.5%               | 8 px                  | Key figures in body, row titles    |
| `body-default`      | Regular 400               | 14 / 22 px             | 1%                 | 8 px                  | Tables, helper text                |
| `body-default-bold` | Semi Bold 600             | 14 / 22 px             | 1.25%              | 8 px                  | Table emphasis, labels             |
| `link-large`        | Semi Bold 600, underlined | 16 / 24 px             | 1%                 | 8 px                  | Links inside large body            |
| `link-default`      | Semi Bold 600, underlined | 14 / 22 px             | 1.25%              | not specified         | Links inside default body          |

Screen titles, large money amounts and the landing hero are not in the spec. The values below are confirmed for now and may change during the build.

    /* src/app.css */
    @import "tailwindcss";
    @import "@fontsource-variable/inter";

    @theme {
      --font-sans: "Inter Variable", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;

      --color-brand-primary: #9fe870;
      --color-brand-forest: #163300;
      --color-content-primary: #0e0f0c;
      --color-content-secondary: #454745;
      --color-content-tertiary: #868685;
      --color-brand-pale: #e2f6d5;
      --color-background-neutral: #e8ebe6;
      --color-background-screen: #ffffff;
      --color-sentiment-positive: #054d28;
      --color-sentiment-warning: #ffd11a;
      --color-sentiment-negative: #d03238;
      --color-accent-orange: #ffc091;
      --color-accent-cyan: #38c8ff;

      --text-title-group: 14px;
      --text-title-group--line-height: 20px;
      --text-title-group--letter-spacing: 0.015em;
      --text-title-group--font-weight: 500;

      --text-body-large: 16px;
      --text-body-large--line-height: 24px;
      --text-body-large--letter-spacing: -0.005em;
      --text-body-large--font-weight: 400;

      --text-body-large-bold: 16px;
      --text-body-large-bold--line-height: 24px;
      --text-body-large-bold--letter-spacing: 0.005em;
      --text-body-large-bold--font-weight: 600;

      --text-body-default: 14px;
      --text-body-default--line-height: 22px;
      --text-body-default--letter-spacing: 0.01em;
      --text-body-default--font-weight: 400;

      --text-body-default-bold: 14px;
      --text-body-default-bold--line-height: 22px;
      --text-body-default-bold--letter-spacing: 0.0125em;
      --text-body-default-bold--font-weight: 600;

      /* not in the original spec; confirmed for now */
      --text-screen-title: 24px;
      --text-screen-title--line-height: 32px;
      --text-screen-title--font-weight: 600;
      --text-amount: 32px;
      --text-amount--line-height: 40px;
      --text-amount--font-weight: 600;

      --radius-pill: 9999px;
      --radius-card: 24px;
      --radius-card-lg: 32px;
    }

    @utility link-large {
      font-size: 16px; line-height: 24px; font-weight: 600;
      letter-spacing: 0.01em; text-decoration-line: underline;
    }
    @utility link-default {
      font-size: 14px; line-height: 22px; font-weight: 600;
      letter-spacing: 0.0125em; text-decoration-line: underline;
    }
    @utility para { margin-block-end: 8px; }

    /* landing hero only */
    @utility text-hero {
      font-size: clamp(48px, 7vw, 96px); line-height: 0.88; font-weight: 900;
    }

### Shape and layout

- Buttons are pills (`rounded-pill`): primary is `brand-primary` with `brand-forest` text, secondary is transparent with a 1 px border at 15% of `content-primary`. Labels use `body-large-bold`.
- Cards are white, `rounded-card` (24 px), 24 px padding, and use a 1 px ring at 10% of `content-primary` instead of drop shadows. Marketing cards use `rounded-card-lg`.
- Spacing follows Tailwind's 4 px scale. The page container is at most 1200 px wide and centred, with 24 px side padding.

### Components (`src/lib/components`)

| **Component**                                    | **Rules**                                                                                                                                                                                            |
|--------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Button                                           | Primary, secondary and link variants; sentence-case labels that start with a verb                                                                                                                    |
| Card, Section                                    | Token radius and ring border only                                                                                                                                                                    |
| Money                                            | Takes integer minor units plus currency; builds a decimal string from the currency exponent served by `/v1/currencies` and formats it with `Intl.NumberFormat`; never `parseFloat` or float division |
| StatusChip                                       | Invoice and run states as text plus colour, never colour alone                                                                                                                                       |
| DataTable                                        | Sorting, filters, cursor pagination with "Load more"                                                                                                                                                 |
| UploadDropzone                                   | CSV only, size limit, row-error table                                                                                                                                                                |
| ConfirmationCard                                 | Invoice terms with Confirm, Dispute and Propose correction                                                                                                                                           |
| StatementSummary                                 | Opens with one sentence such as "You will pay EUR 40,000 instead of EUR 100,000", then detail                                                                                                        |
| RunTimeline                                      | Run states as a stepper with re-computation markers                                                                                                                                                  |
| SavingsMeter, BreakEvenSlider                    | Savings per run and cumulative; slider calls `/v1/estimates`                                                                                                                                         |
| NetworkGraph                                     | Cytoscape wrapper; toggle between invoice edges and settlement transfers                                                                                                                             |
| Toast, Modal, Tabs, EmptyState, KillSwitchToggle | Built on Bits UI                                                                                                                                                                                     |

### UI rules

- Every statement and run screen starts with a plain-language summary, including what happens if the user does nothing.
- Fees, baseline cost and savings always appear together.
- WCAG 2.2 AA target: keyboard operable, labelled inputs, status never shown by colour alone.
- Desktop only; the demo has no mobile layout.

<!-- -->

    frontend/src/
      app.css                 # @theme tokens above
      lib/
        api/                  # generated schema.d.ts + client.ts
        components/           # Button, Card, Money, StatusChip, ...
        features/             # invoices/, confirmations/, runs/, statements/, admin/
        money.ts              # minor-unit helpers
        stores/               # session, notifications
      routes/
        +layout.ts            # export const ssr = false
        (public)/  (member)/  (admin)/

## Backend (Python, FastAPI)

The backend is one FastAPI app split into domain modules. Routers validate and delegate, services own transactions, and the netting engine is a pure function with no database access.

### Modules (`app/modules/`)

Each module has `router.py`, `schemas.py`, `models.py`, `service.py` and `repository.py`.

| **Module**           | **Owns tables**                                                                              | **Responsibilities**                                   |
|----------------------|----------------------------------------------------------------------------------------------|--------------------------------------------------------|
| members              | members, legal_entities, users, kill_switches                                                | Roles, limits, settings, kill switches                 |
| invoices             | invoices, invoice_versions                                                                   | CSV parsing, validation, fingerprint, versions         |
| counterparties       | invitations                                                                                  | Matching against legal entities, invitations           |
| confirmations        | confirmations                                                                                | Requests, confirm, dispute, correct, simulated replies |
| windows              | windows, run_invoices                                                                        | Eligibility query, freeze, input hash                  |
| fx                   | fx_rates, rate_snapshots, fx_locks                                                           | Snapshots, locks, conversion, rounding                 |
| netting              | none                                                                                         | Pure engine; the runs module persists its output       |
| risk                 | sanctions_list, risk_decisions, cases                                                        | Screening and the ring rule                            |
| pricing              | fee_charges                                                                                  | Gain-share fee, allocation, estimates                  |
| runs                 | netting_runs, run_computations, cancellations, net_positions, planned_transfers, withdrawals | Run state machine and re-computation                   |
| statements           | statements, approvals                                                                        | Build, hash, approve, maker-checker                    |
| settlement           | holds, settlement_jobs, invoice_outcomes                                                     | Prepare, commit, abort                                 |
| ledger               | ledger_accounts, journal_entries, postings                                                   | Posting API, balances, hash chain, clearing check      |
| notifications, audit | notifications, outbox_events, audit_events                                                   | Outbox handlers, audit writes and reads                |
| admin, demo          | none                                                                                         | Ops endpoints; demo scenarios behind `DEMO_MODE`       |

### Layering rules

1.  Routers parse Pydantic models, read the session user and call one service function. No SQL in routers.
2.  Services own the transaction, check permissions and write outbox events in the same transaction as the state change.
3.  Every member-facing repository function takes `member_id` as a required argument.
4.  `netting/engine.py` imports nothing from SQLAlchemy or `core.db`; it takes and returns frozen dataclasses.
5.  Money is `int` minor units end to end and rates are `decimal.Decimal`; `float` never appears in money code.

### Netting engine contract

    @dataclass(frozen=True)
    class Edge:                 # one invoice: payer owes receiver
        invoice_id: UUID
        payer: UUID             # member_id
        receiver: UUID          # member_id (issuer)
        amount_minor: int       # outstanding, > 0
        currency: str

    @dataclass(frozen=True)
    class EngineInput:
        edges: tuple[Edge, ...]
        rates: Mapping[tuple[str, str], Decimal]   # from the run's snapshot
        settlement_currency: Mapping[UUID, str]
        payable_limit_minor: Mapping[UUID, int]
        excluded_members: frozenset[UUID]
        time_budget_ms: int
        algo_version: str

    @dataclass(frozen=True)
    class EngineResult:
        positions: tuple[NetPosition, ...]
        transfers: tuple[PlannedTransfer, ...]
        cancellations: tuple[Cancellation, ...]
        outcomes: tuple[InvoiceOutcome, ...]
        fx_legs: tuple[FxLeg, ...]
        metrics: Metrics        # gross, net, reduction, transfer count
        input_hash: str
        result_hash: str

    def run_netting(inp: EngineInput) -> EngineResult: ...

1.  Canonicalise: drop edges of excluded members, sort by (currency, payer, receiver, invoice_id), hash the canonical JSON as `input_hash`, derive the seed from it.
2.  Partition by currency, then by weakly connected component. Build NetworkX graphs from sorted edges so traversal order is stable.
3.  Cancel cycles: inside each strongly connected component, find a cycle, subtract its minimum from every edge, record one Cancellation per invoice, drop zero edges, repeat until acyclic.
4.  Positions: receivables minus payables per member and currency; assert the sum is zero.
5.  Limits: a payer above its limit joins `excluded_members` and the engine restarts from step 1.
6.  Transfers: exact-amount pairs, then zero-sum subsets of 3 to 4 inside the time budget, then greedy for the rest. Keep the result only if it has no more transfers than greedy alone.
7.  Cross-currency pass (MC-FX-02): convert a member's off-currency residual into its settlement currency at the snapshot rate, half-even rounding plus largest remainder, booked against the FX conversion account so each currency still balances.
8.  Outcomes: cancelled = sum of cancellations; residual = outstanding - cancelled; outcome is SETTLED_BY_NETTING when residual is 0, else SETTLED_BY_TRANSFER.
9.  Validate (MC-NET-06), then hash the canonical result as `result_hash`.

### Run lifecycle

In the prototype, API calls drive every transition: Close window, Settle, and the demo buttons. Each transition is a service function that locks the run row with `SELECT ... FOR UPDATE`, checks the current state and writes an audit event.

![Netting run lifecycle: 10 states, 3 exit paths](Wise_Mesh_Continental_Technical_PRD_media/rId53.png)

Rejections, missing replies and funding failures loop back through Recompute at most twice; a commit error always ends in ABORTED with every hold released.

### Invoice states

Eligibility is computed at freeze, so ELIGIBLE is not a stored state; a released invoice goes back to CONFIRMED.

| **State**                                                         | **Next states**                                   | **Changed by**         |
|-------------------------------------------------------------------|---------------------------------------------------|------------------------|
| IMPORTED                                                          | MATCHED, UNMATCHED, REJECTED_DATA                 | invoices               |
| MATCHED                                                           | PENDING_CONFIRMATION                              | counterparties         |
| UNMATCHED                                                         | MATCHED                                           | counterparties         |
| PENDING_CONFIRMATION                                              | CONFIRMED, DISPUTED                               | confirmations          |
| CONFIRMED                                                         | LOCKED_IN_RUN, AMENDED, DISPUTED                  | windows, confirmations |
| AMENDED                                                           | PENDING_CONFIRMATION                              | confirmations          |
| DISPUTED                                                          | CONFIRMED, CANCELLED                              | confirmations          |
| LOCKED_IN_RUN                                                     | SETTLED_BY_NETTING, SETTLED_BY_TRANSFER, RELEASED | settlement, runs       |
| RELEASED                                                          | CONFIRMED                                         | runs                   |
| SETTLED_BY_NETTING, SETTLED_BY_TRANSFER, CANCELLED, REJECTED_DATA | Terminal                                          | \-                     |

### Settlement transactions

- **Prepare** (one transaction): lock the run; recompute the input hash from `run_invoices` and compare; re-check member state, sanctions, approvals against the current statement hash and FX locks. For each payer, lock its balance account, check available funds cover net payable plus fee, and post balance to hold.
- **Commit** (one transaction): one journal entry posts hold to clearing for payers, clearing to balance for receivers, hold to fee revenue, and the FX legs. Assert the run's clearing balance is zero before COMMIT, then write invoice outcomes and set the run to COMMITTED.
- **Abort**: post hold back to balance for every active hold, set invoices to RELEASED, then CONFIRMED.
- **Idempotency**: `settlement_jobs.idempotency_key = sha256(run_id, member_id, step)` is unique. A repeated call returns the stored result.
- **Crash safety**: the job row is written before and after each step, so calling Settle again resumes from the last stored step.

### Events and background work

- Services insert `outbox_events` rows in the same transaction as the change they describe.
- An asyncio worker started in the FastAPI lifespan polls unprocessed events every second and creates notifications. Handlers are idempotent on event ID.
- Event names follow the description: `invoice.confirmed`, `window.frozen`, `run.computed`, `run.statements_issued`, `run.approval_received`, `run.funding_failed`, `run.recomputed`, `run.committed`, `run.aborted`.

## Data model

PostgreSQL 16 holds all 35 tables. Money is BIGINT minor units, rates are NUMERIC(20,10), IDs are UUIDv7, and every timestamp is TIMESTAMPTZ in UTC.

### Rules

- **Money**: `amount_minor BIGINT` plus `currency CHAR(3)` referencing `currencies`. Unsigned amounts carry `CHECK (amount_minor > 0)`; signed amounts are named `*_signed_minor` or documented as signed.
- **Rates**: `NUMERIC(20,10)` in the database and `Decimal` in Python; serialised as strings in JSON.
- **IDs**: UUIDv7, generated in the app so they sort by time.
- **Status columns**: `TEXT` with a `CHECK` list, mirrored by Python `StrEnum` classes.
- **Hashes**: SHA-256 hex over canonical JSON (sorted keys, no whitespace).
- **Append-only**: invoice versions, confirmations, run computations, statements, approvals, journal entries, postings and audit events are never updated. The app's database role has no UPDATE or DELETE grant on `journal_entries`, `postings` and `audit_events`.

### Tables

| **Table**         | **Key columns**                                                                                                                                                                                    | **Constraints and notes**                                                                              |
|-------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| currencies        | code, exponent, name                                                                                                                                                                               | Seeded: EUR, USD, HUF, GBP, CNY                                                                        |
| legal_entities    | id, legal_name, tax_id, registration_no, country                                                                                                                                                   | unique (tax_id, country)                                                                               |
| members           | id, legal_entity_id, state, risk_tier, settlement_currency, payable_limit_minor, maker_checker_minor, agreement_version, created_at                                                                | state: INVITED, ONBOARDING, ACTIVE, RESTRICTED, SUSPENDED, OFFBOARDED                                  |
| users             | id, member_id, email, password_hash, role                                                                                                                                                          | member_id is null for Wise staff; unique email                                                         |
| kill_switches     | id, scope, member_id, enabled, reason, changed_by, changed_at                                                                                                                                      | scope: GLOBAL or MEMBER                                                                                |
| invoices          | id, issuer_entity_id, payer_entity_id, counterparty_raw, invoice_number, issue_date, due_date, currency, amount_minor, outstanding_minor, status, current_version, fingerprint, source, created_by | unique fingerprint; outstanding_minor between 0 and amount_minor; payer_entity_id null while UNMATCHED |
| invoice_versions  | invoice_id, version, change_type, changed_fields (jsonb), actor_id, created_at                                                                                                                     | PK (invoice_id, version)                                                                               |
| confirmations     | id, invoice_id, version, party_member_id, decision, reason_code, method, actor_id, created_at                                                                                                      | unique (invoice_id, version, party_member_id); method: USER, AUTO, SIMULATED                           |
| invitations       | id, from_member_id, invoice_id, contact_email, status, expires_at                                                                                                                                  | Could-priority feature                                                                                 |
| windows           | id, status, opened_at, closed_at, horizon_days, rules_version                                                                                                                                      | partial unique index allows one OPEN window                                                            |
| fx_rates          | base, quote, rate, source, valid_from                                                                                                                                                              | Static seed                                                                                            |
| rate_snapshots    | id, run_id, base, quote, rate, source, captured_at                                                                                                                                                 | Copied at freeze                                                                                       |
| netting_runs      | id, window_id, status, current_attempt, started_at, finished_at                                                                                                                                    | One per window; status follows the run lifecycle                                                       |
| run_invoices      | run_id, invoice_id                                                                                                                                                                                 | Frozen set; PK (run_id, invoice_id)                                                                    |
| run_computations  | id, run_id, attempt, input_hash, excluded_members, algo_version, seed, result_hash, metrics (jsonb), created_at                                                                                    | unique (run_id, attempt); attempt at most 3                                                            |
| cancellations     | computation_id, invoice_id, cycle_no, amount_minor                                                                                                                                                 | Engine trace for G6                                                                                    |
| net_positions     | computation_id, member_id, currency, amount_minor (signed), gross_in_minor, gross_out_minor                                                                                                        | Sum per computation and currency is 0                                                                  |
| planned_transfers | id, computation_id, payer_member_id, receiver_member_id, currency, amount_minor, kind, status                                                                                                      | kind: SETTLEMENT or FX_LEG                                                                             |
| withdrawals       | id, run_id, member_id, invoice_id, created_by, created_at                                                                                                                                          | Triggers re-computation                                                                                |
| fx_locks          | id, run_id, member_id, base, quote, rate, expires_at                                                                                                                                               | Set at approval                                                                                        |
| fee_charges       | id, computation_id, member_id, currency, baseline_minor, actual_minor, savings_minor, fee_minor, price_version                                                                                     | fee_minor at most savings_minor                                                                        |
| statements        | id, computation_id, member_id, content (jsonb), content_hash, issued_at, expires_at                                                                                                                | unique (computation_id, member_id)                                                                     |
| approvals         | id, statement_id, approver_id, decision, content_hash, method, created_at                                                                                                                          | unique (statement_id, approver_id)                                                                     |
| holds             | id, run_id, member_id, currency, amount_minor, status, journal_entry_id                                                                                                                            | status: ACTIVE, CONSUMED, RELEASED                                                                     |
| settlement_jobs   | id, run_id, member_id, step, idempotency_key, status, attempts, last_error, result (jsonb)                                                                                                         | unique idempotency_key                                                                                 |
| invoice_outcomes  | invoice_id, run_id, outcome, cancelled_minor, residual_minor                                                                                                                                       | unique (invoice_id, run_id); cancelled + residual = outstanding                                        |
| ledger_accounts   | id, type, member_id, run_id, currency                                                                                                                                                              | type: MEMBER_BALANCE, MEMBER_HOLD, CLEARING, FX_CONVERSION, FEE_REVENUE, SUSPENSE                      |
| journal_entries   | id, run_id, kind, idempotency_key, hash_prev, hash, created_at                                                                                                                                     | Insert-only; unique idempotency_key                                                                    |
| postings          | id, journal_entry_id, account_id, currency, amount_minor (signed)                                                                                                                                  | Sum per entry and currency is 0, checked in the service and by a test                                  |
| sanctions_list    | id, name, country, source                                                                                                                                                                          | Mock data                                                                                              |
| risk_decisions    | id, run_id, subject_type, subject_id, rule, decision, reasons (jsonb)                                                                                                                              | decision: ALLOW, EXCLUDE, HOLD_FOR_REVIEW, BLOCK                                                       |
| cases             | id, type, subject_type, subject_id, status, assignee_id, notes                                                                                                                                     | Opened by risk rules                                                                                   |
| notifications     | id, user_id, type, payload (jsonb), read_at, created_at                                                                                                                                            | Created by the outbox worker                                                                           |
| outbox_events     | id, type, aggregate_id, payload (jsonb), created_at, processed_at                                                                                                                                  | Same transaction as the change                                                                         |
| audit_events      | id, actor_id, action, subject_type, subject_id, before_hash, after_hash, reason_code, created_at                                                                                                   | Insert-only                                                                                            |

A re-computation adds a row to `run_computations` instead of overwriting the run. Positions, transfers, fees and statements hang off the computation, so every earlier attempt stays auditable.

## API specification

The API is REST with JSON under `/v1`. FastAPI's OpenAPI schema is the contract, and CI regenerates the frontend types from it and fails on drift.

### Conventions

- **Auth**: `POST /v1/auth/login` sets a signed JWT in an httpOnly, SameSite=Lax cookie (8 h in demo mode). State-changing requests must also send `X-Requested-With: mesh-web` as a CSRF guard.
- **Idempotency**: every POST that creates or changes state requires an `Idempotency-Key` header. The server stores key, request hash and response; a replay with a different body returns 409 `IDEMPOTENCY_MISMATCH`.
- **Money**: always `{"amount_minor": 4000000, "currency": "EUR"}`. Rates are strings such as `"0.2312"`.
- **Lists**: `?limit=50&cursor=...`, response `{"items": [...], "next_cursor": "..."}`.
- **Correlation**: `X-Correlation-ID` is accepted or generated, returned on every response and written to every log line.
- **Scoping**: member endpoints never take a member ID; it comes from the session. Another member's resource returns 404, not 403.

### Endpoints

| **Method** | **Path**                        | **Purpose**                                                         | **Roles**                            |
|------------|---------------------------------|---------------------------------------------------------------------|--------------------------------------|
| POST       | /v1/auth/login                  | Log in, set session cookie                                          | Public                               |
| POST       | /v1/auth/logout                 | End session                                                         | Any                                  |
| GET        | /v1/me                          | User, role and member summary                                       | Any                                  |
| GET        | /v1/members/me                  | Member state, limits, balances by currency                          | Member roles                         |
| PATCH      | /v1/members/me/settings         | Limits, maker-checker threshold, settlement currency                | Member admin                         |
| GET        | /v1/currencies                  | Codes and exponents                                                 | Any                                  |
| GET        | /v1/rates                       | Current static rates                                                | Any                                  |
| GET        | /v1/invoices                    | List with filters: direction, status, counterparty                  | Member roles                         |
| POST       | /v1/invoices                    | Create one invoice                                                  | Member admin, finance user           |
| POST       | /v1/invoices/uploads            | CSV upload; returns accepted and rejected rows                      | Member admin, finance user           |
| GET        | /v1/invoices/template.csv       | CSV template                                                        | Member roles                         |
| GET        | /v1/invoices/{id}               | Detail with versions, confirmations, outcome                        | Member roles                         |
| GET        | /v1/confirmations               | Inbox of pending requests                                           | Member admin, finance user           |
| POST       | /v1/invoices/{id}/confirmations | Confirm, dispute or propose a correction                            | Member admin, finance user           |
| GET        | /v1/counterparties              | Matched and unmatched counterparties                                | Member roles                         |
| POST       | /v1/invitations                 | Invite an unmatched counterparty                                    | Member admin, finance user           |
| GET        | /v1/windows/current             | Open window and its settings                                        | Any                                  |
| GET        | /v1/runs                        | Runs the member took part in                                        | Member roles                         |
| GET        | /v1/runs/{id}                   | Member-scoped run summary and timeline                              | Member roles                         |
| POST       | /v1/runs/{id}/withdrawals       | Withdraw invoices from the run                                      | Member admin, finance user           |
| GET        | /v1/statements/{id}             | Netting statement                                                   | Member roles                         |
| POST       | /v1/statements/{id}/approvals   | Approve or reject with content_hash                                 | Member admin, finance user, approver |
| GET        | /v1/savings                     | Per-run and cumulative savings                                      | Member roles                         |
| POST       | /v1/estimates                   | Break-even calculation from fee share and standard rate             | Member roles                         |
| GET        | /v1/notifications               | In-app notifications                                                | Any                                  |
| POST       | /v1/notifications/{id}/read     | Mark as read                                                        | Any                                  |
| GET        | /v1/network/me                  | Own counterparties and flows only                                   | Member roles                         |
| POST       | /v1/admin/windows/current/close | Freeze, screen, compute, issue statements                           | Wise ops                             |
| GET        | /v1/admin/runs/{id}             | Full run detail with all computations                               | Wise ops, Wise compliance            |
| POST       | /v1/admin/runs/{id}/settle      | Prepare and commit, resuming if interrupted                         | Wise ops                             |
| POST       | /v1/admin/runs/{id}/abort       | Abort and release holds                                             | Wise ops, Wise compliance            |
| PUT        | /v1/admin/kill-switches         | Set global or member switch with reason                             | Wise ops, Wise compliance            |
| GET        | /v1/admin/cases                 | Risk cases                                                          | Wise compliance                      |
| GET        | /v1/admin/ledger/check          | Clearing balances and hash-chain check                              | Wise ops                             |
| GET        | /v1/admin/audit-events          | Audit log with filters                                              | Wise ops, Wise compliance            |
| GET        | /v1/admin/network               | Whole graph before and after netting                                | Wise ops                             |
| POST       | /v1/demo/reset                  | Wipe and re-seed                                                    | Wise ops, demo mode                  |
| POST       | /v1/demo/scenarios/{name}       | Load worked_example or improvement_example                          | Wise ops, demo mode                  |
| POST       | /v1/demo/generate               | Synthetic graph: members, invoices, currencies, cycle density, seed | Wise ops, demo mode                  |
| POST       | /v1/demo/simulate-confirmations | Reply to pending requests with given rates                          | Wise ops, demo mode                  |
| POST       | /v1/demo/funding-failure        | Make a payer unable to fund                                         | Wise ops, demo mode                  |
| POST       | /v1/demo/expire-approvals       | Expire pending approvals of a run                                   | Wise ops, demo mode                  |

### Error format

    {
      "error": {
        "code": "STATEMENT_CHANGED",
        "message": "This statement was recomputed. Review the new version before approving.",
        "correlation_id": "01J9Z3...",
        "details": { "current_statement_id": "..." }
      }
    }

Codes in use: VALIDATION_FAILED, NOT_FOUND, FORBIDDEN, INVALID_STATE, DUPLICATE_INVOICE, STATEMENT_CHANGED, IDEMPOTENCY_MISMATCH, KILL_SWITCH_ON, LIMIT_EXCEEDED, FX_LOCK_EXPIRED, INSUFFICIENT_FUNDS, DEMO_MODE_OFF.

### Statement payload

    {
      "statement_id": "...",
      "run_id": "...",
      "attempt": 1,
      "member_id": "...",
      "summary": "You will pay EUR 40,000 instead of EUR 100,000.",
      "counterparties": [
        {
          "name": "Member B",
          "invoices": [
            { "invoice_id": "...", "invoice_number": "2026-0412", "direction": "PAYABLE",
              "outstanding": { "amount_minor": 10000000, "currency": "EUR" },
              "cancelled":   { "amount_minor": 6000000,  "currency": "EUR" },
              "residual":    { "amount_minor": 4000000,  "currency": "EUR" } }
          ]
        }
      ],
      "gross_payable":    { "amount_minor": 10000000, "currency": "EUR" },
      "gross_receivable": { "amount_minor": 6000000,  "currency": "EUR" },
      "net":              { "amount_minor": -4000000, "currency": "EUR" },
      "fx_legs": [],
      "fee":     { "amount_minor": 0, "currency": "EUR" },
      "savings": { "amount_minor": 0, "currency": "EUR" },
      "price_version": "2026-10-demo",
      "instruction": { "type": "DEBIT", "counterparty": "Mesh settlement", "reference": "MESH-..." },
      "approval": { "required_approvers": 1, "deadline": "..." },
      "content_hash": "sha256:..."
    }

Fee and savings show 0 here only to keep the sample short; real statements carry the gain-share values from the pricing module.

## Security, roles and non-functional targets

Security is sized for a demo but keeps the production shape: every request is authenticated, authorised by role and scoped to the caller's member on the server.

### Security controls

- Passwords hashed with argon2id (`argon2-cffi`); JWT signed with a secret from the environment; no secrets in the repository.
- Session cookie is httpOnly and SameSite=Lax; state-changing requests need the `X-Requested-With` header and a matching Origin.
- Pydantic strict models on every body; CSV uploads capped by size and row count (proposed: 5 MB, 10,000 rows).
- Login attempts rate-limited per IP and per email.
- Logs are structured JSON with correlation ID; no invoice numbers, legal names or amounts in log lines.
- Every Wise staff action requires a reason code and writes an audit event.

### Role permissions

| **Capability**                              | **Member admin** | **Finance user** | **Approver**    | **Wise ops** | **Wise compliance** |
|---------------------------------------------|------------------|------------------|-----------------|--------------|---------------------|
| View own invoices, runs and statements      | Yes              | Yes              | Yes             | Admin views  | Admin views         |
| Upload, create, confirm or dispute invoices | Yes              | Yes              | No              | No           | No                  |
| Approve a statement                         | Yes              | Up to threshold  | Above threshold | No           | No                  |
| Change limits and settings                  | Yes              | No               | No              | No           | No                  |
| Close window, settle, abort run             | No               | No               | No              | Yes          | Abort only          |
| Kill switches                               | No               | No               | No              | Yes          | Yes                 |
| Cases and sanctions list                    | No               | No               | No              | No           | Yes                 |
| Demo controls (demo mode only)              | No               | No               | No              | Yes          | No                  |

Maker-checker: above the member's threshold, two different users must approve, and the second must hold the approver or member admin role.

### Non-functional targets

These are proposed prototype targets; measure them with the synthetic generator before treating them as commitments.

| **Area**          | **Target**                                                                          |
|-------------------|-------------------------------------------------------------------------------------|
| Money correctness | Zero tolerance; every invariant checked on every computation                        |
| Determinism       | Same frozen input gives the same result hash                                        |
| Engine speed      | 1,000 members and 20,000 invoices computed in under 10 s on a laptop                |
| API latency       | p95 under 300 ms for member reads on demo data                                      |
| Auditability      | Any run rebuilt from run_invoices, its rate snapshot, computations and audit events |
| Browsers          | Current desktop Chrome, Firefox, Safari and Edge                                    |
| Accessibility     | WCAG 2.2 AA target                                                                  |

## Infrastructure, configuration and testing

Docker Compose runs the same three services on every laptop and in CI: PostgreSQL, the FastAPI API and the built Svelte app behind nginx.

### Services

| **Service** | **Build**                                    | **Port** | **Notes**                                                                                          |
|-------------|----------------------------------------------|----------|----------------------------------------------------------------------------------------------------|
| db          | postgres:16                                  | 5432     | Named volume; init script creates the app role without UPDATE or DELETE on ledger and audit tables |
| api         | backend/Dockerfile, python:3.12-slim with uv | 8000     | Runs `alembic upgrade head`, then Uvicorn                                                          |
| web         | frontend/Dockerfile, pnpm build then nginx   | 8080     | Serves the static build and proxies `/v1` to api                                                   |

During development the Svelte app runs with `pnpm dev` on 5173, and Vite proxies `/v1` to the API.

### Environment variables

| **Variable**           | **Default**                                 | **Purpose**                                                     |
|------------------------|---------------------------------------------|-----------------------------------------------------------------|
| DATABASE_URL           | postgresql+psycopg://mesh:mesh@db:5432/mesh | Database connection                                             |
| JWT_SECRET             | none, must be set                           | Session signing key                                             |
| SESSION_HOURS          | 8                                           | Session lifetime                                                |
| DEMO_MODE              | true                                        | Enables `/v1/demo` and the persona picker                       |
| NETTING_TIME_BUDGET_MS | 2000                                        | Improvement heuristic budget                                    |
| MAX_RECOMPUTES         | 2                                           | Re-runs before FALLBACK_GROSS                                   |
| STANDARD_RATE_BPS      | 52                                          | Baseline transfer cost, illustrative 0.52% from the description |
| FEE_SHARE_BPS          | 2500                                        | Mesh share of savings, illustrative 25% from the description    |
| DUST_THRESHOLD_MINOR   | 100                                         | Residuals below this carry forward                              |
| FX_LOCK_MINUTES        | 30                                          | Rate lock lifetime (proposed)                                   |
| ALGO_VERSION           | net-0.1.0                                   | Recorded on every computation                                   |

### CI (GitHub Actions)

1.  Backend: `ruff check`, `ruff format --check`, `mypy`, `pytest` against a Postgres service container.
2.  Frontend: `pnpm lint`, `svelte-check`, `vitest`, `pnpm build`.
3.  Contract: regenerate OpenAPI types and fail if they differ from the committed ones.
4.  End to end: start Compose, run the Playwright demo script.

### Test plan

| **Level**            | **Tool**       | **Must prove**                                                                                                                                                                               |
|----------------------|----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Unit                 | pytest         | CSV parsing, minor-unit parsing, rounding, fingerprints, eligibility, fee allocation                                                                                                         |
| Property-based       | Hypothesis     | On random graphs: zero sum, plan clears every position, cancelled + residual = outstanding, no non-positive transfers, improved plan never longer than greedy, same input gives same hash    |
| Golden               | pytest         | Worked example gives 3 transfers worth 80; positions +30, -30, +50, -50 give 2 transfers                                                                                                     |
| Reference            | pytest         | Engine positions equal a naive sum-per-member implementation                                                                                                                                 |
| API                  | pytest + httpx | Role checks, cross-member 404s, idempotency replay, error envelope                                                                                                                           |
| Settlement scenarios | pytest         | Funding failure re-computes; third exclusion ends in FALLBACK_GROSS; commit error releases every hold; a crash between steps still ends in exactly one commit; clearing is zero after commit |
| Frontend unit        | Vitest         | Money formatting for each currency exponent, status chip mapping                                                                                                                             |
| End to end           | Playwright     | Seed, upload, simulate confirmations, close window, approve, settle, see savings                                                                                                             |

Logs use structlog with the correlation ID; `/healthz` reports database reachability; run metrics live in `run_computations.metrics` and show in the ops console.

## Build order

Build the whole demo path on the worked example first, then widen.

### Workstreams

The description sizes the prototype for a team of four.

| **Workstream** | **Scope**                                                             | **Requirement areas**                          |
|----------------|-----------------------------------------------------------------------|------------------------------------------------|
| Engine         | Netting engine, FX rounding, pricing, property and golden tests       | MC-NET, MC-FX, MC-FEE                          |
| Core API       | Schema, auth, ingestion, matching, confirmations, windows, statements | MC-ONB, MC-ING, MC-ENT, MC-CNF, MC-WIN, MC-APR |
| Settlement     | Run orchestrator, holds, ledger, risk rules, audit, demo endpoints    | MC-SET, MC-LED, MC-RSK, MC-OPS                 |
| Frontend       | Tokens, components, member screens, ops console, network view         | MC-UX, MC-PRV views                            |

### Milestones

1.  **M0 Foundations**: repository, Compose, CI, Alembic baseline, auth, worked-example seed, Tailwind tokens, Button, Card and Money components. Gate: a seeded user logs in and sees a balance.
2.  **M1 Engine**: `run_netting` passes golden and property tests (MC-NET-01 to 04 and 06 to 08) plus the cross-currency pass (MC-FX-02, MC-FX-04). Runs in parallel with M0 because it has no database. Gate: the worked example gives 3 transfers worth 80.
3.  **M2 Invoice flow**: CSV upload, matching, confirmation inbox, simulated replies. Gate: confirmed invoices show as eligible for the open window.
4.  **M3 Run to statement**: close window, freeze, screening, compute, statements, approvals. Gate: each member sees only its own statement and can approve it.
5.  **M4 Settlement**: prepare, commit, ledger, funding failure, abort, outcomes, savings. Gate: clearing is zero after commit, and a funding failure re-computes.
6.  **M5 Demo polish**: landing page, network view, break-even slider, kill switch, Playwright demo script. Gate: the full demo script passes twice in a row on a fresh reset.

Should and Could requirements are picked up only after M5 passes. The frontend builds each screen against the generated API types as soon as its endpoints exist, using the seed data.

## Assumptions

Eight assumptions fill gaps in the brief; each one changes code if it is wrong.

| **\#** | **Assumption**                                                                                                                          | **What changes if wrong**                                   |
|--------|-----------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| 1      | Scope is the hackathon prototype from section 18 of the description, not the production P0 pilot                                        | Connectors, KYB, payouts and much larger data model         |
| 2      | FastAPI is the Python framework, as the description's prototype column proposes                                                         | Django would change routing, ORM, auth and admin            |
| 3      | "Backend in Python and that's it" means SvelteKit ships as a static SPA with no Node server code                                        | SSR or server routes would add a Node runtime to deployment |
| 4      | PostgreSQL 16 for dev, tests and demo; no SQLite                                                                                        | SQLite would need a different locking design for holds      |
| 5      | No access to Wise brand assets: Inter replaces Wise Sans, Lucide replaces Wise icons, and colours are the publicly observed Wise values | Only `app.css` tokens change                                |
| 6      | English-only UI; demo currencies EUR, USD, HUF, GBP and CNY with static rates                                                           | Seed data and rate table grow                               |
| 7      | Seeded users and a persona picker replace sign-up and KYB                                                                               | Onboarding screens and member lifecycle endpoints needed    |
| 8      | Notifications are in-app only: no email, push or webhooks                                                                               | Mail provider and webhook delivery log needed               |
