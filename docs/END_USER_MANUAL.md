# Istithmar Investment Platform — End User Manual

**Purpose:** Offline administration for community investment: members, agents, contributions, share subscriptions, certificates, projects, investments, profit distribution, accounting (optional), and reports.

**Access:** Web application (e.g. `http://127.0.0.1:5000` in development). Users sign in with username and password.

---

## 1. User roles (who can do what)

| Capability | **Admin** | **Operator** | **Agent** |
|------------|-----------|----------------|-----------|
| Dashboard, profile | Yes | Yes | Yes (scoped) |
| **Members** — list, add, edit, view profiles | All members | All members | **Only “My team”** (members linked to that agent) |
| **Agents** — directory, create, edit | Yes | Yes | **No** (menu hidden) |
| **Contributions** — record payments | Scoped | Scoped | **Only own team’s members** |
| Verify / unverify contributions | Yes | Yes | **No** |
| **Projects** | Yes | Yes | Yes (see org policy) |
| **Investments** | Yes | Yes | Yes |
| Record investment ledger snapshot | Yes | Yes | **No** |
| Delete investment | Yes | **No** | **No** |
| **Invoices** | Scoped | Scoped | Scoped |
| **Subscriptions** (share subscriptions) | Scoped | Scoped | Scoped |
| Cancel subscription | Yes | Yes | **No** |
| **Certificates** — issue, revoke, print/PDF | Per permissions | Per permissions | Per permissions |
| **Profit distribution** (run batches) | Yes | Yes | **No** — sees **Profit history** instead |
| **Accounting** (full module) | Yes | Yes | **No** |
| **Reports** — full org reports | Yes | Yes | **Limited** (scoped data; some reports admin-only) |
| **Settings** (currency, rules, logos, flags) | Yes | **No** | **No** |
| **User management** (create app users) | Yes | **No** | **No** |
| **Audit logs** | Yes | **No** | **No** |

**Scoping rule:** If your login is an **Agent** user, almost all lists and totals are limited to members (and their transactions) assigned to **your** agent record. **Admin** and **Operator** see the whole organization unless filters are applied.

---

## 2. Core business flow (end-to-end)

This is the intended workflow the system supports (also summarized under **Reports → Community investment model** in the app):

1. **Agent network** — Register **Agents** (territory, region, country) as the field structure for assigning members.
2. **Members** — Register each person with a unique member ID, contact details, optional **Member kind** (Member / Shareholder / Investor), status, and **link to an agent** (may be required if the setting “require agent on member” is on).
3. **Share subscription** — Create a **Subscription** for a member: amount, payment plan (full or installment), link to an **Investment** when applicable, eligibility policy for profit (e.g. paid proportional vs fully paid only).
4. **Contributions** — Record each payment (cash, mobile, bank, etc.), optionally link to a subscription; system can allocate to installments. Receipt numbers are tracked.
5. **Verification** — **Operators/Admins** mark contributions **verified** when finance confirms funds; several downstream rules (certificates, profit basis) can depend on verification settings.
6. **Projects & investments** — Maintain **Projects** (category, status, budget) and **Investments** deployed against projects; link subscriptions to investments where business rules require investment-scoped profit.
7. **Certificates** — When a subscription is fully paid (and any verification rules pass), **issue** share certificates; can print/PDF; revoke if needed.
8. **Profit distribution** — **Admin/Operator** records profit on investments and runs **distribution batches** to members according to eligible paid amounts and policy.
9. **Accounting (optional)** — If enabled in settings, use chart of accounts, journal entries, trial balance, and general ledger for formal books.
10. **Reporting** — Use **Reports** and Excel/PDF exports for members, agents, contributions, investments, and profit.

---

## 3. Module guide (what each area is for)

### Dashboard
- Organization or agent-scoped headline metrics: members, collections, investments, profit, projects.
- Use as the daily landing page for monitoring.

### Members (“My team” for agents)
- **New member:** capture identity, agent assignment, kind, status.
- **Member profile:** subscriptions, contributions, certificates, profit lines for that member.
- **Contribution report** from a member profile: transaction list for one member.

### Agents (admin/operator only)
- Create and maintain agent records (ID, name, geography).
- Agent profile shows related members and activity as configured.

### Contributions
- **New contribution:** choose member, amount, date, payment type; link to subscription when relevant.
- **Verify/Unverify:** finance confirms money received (admin/operator).
- **Receipt:** generate/view receipt for a contribution.

### Projects
- Track project code, name, category (e.g. real estate, medical), status, dates, budget, manager.
- Supports profitability reporting against budget.

### Investments
- Investment vehicles under projects: amounts invested, profit generated, capital returned, distribution frequency notes.
- **Ledger snapshot:** records a point-in-time financial snapshot on the investment (admin/operator).

### Invoices
- Billing documents tied to members/subscriptions as per your process (list/create from the Invoices section).

### Subscriptions (share subscriptions)
- Defines commitment to shares: full or installment plan, status (Pending → Fully Paid, or Cancelled).
- **Installments:** schedule and payment allocation.
- **Link to investment:** align subscription with a specific investment vehicle.
- **Cancel subscription:** admin/operator only; cannot cancel if already fully paid (use certificate revocation if needed).

### Certificates
- Issue when business rules are met; print or PDF; revoke if invalid.

### Profit distribution (admin/operator)
- Create batches allocating profit to members for selected investments according to settings and eligible basis.
- **Profit history** — all roles that can access it see distribution lines; agents see scoped members.

### Accounting (admin/operator, if enabled)
- **Dashboard** — overview.
- **Account settings** — fiscal configuration.
- **Chart of accounts** — structure.
- **Journal entries** — list, view, void.
- **New journal entry** — manual postings.
- **Trial balance** / **General ledger** — period reporting; CSV export where available.

### Reports
- **Core reports** (numbered in the UI): members financial summary, agent performance, monthly/daily contributions, investment summary, profit history and calculation summaries.
- **Exports:** Excel (.xlsx) for members, contributions, profit, etc.; PDF for members and contributions; agents’ exports may be hidden or scoped.
- Some reports (e.g. agent rankings, investment summary, profitability, profit calculation) are **not available to agent logins**.

### Settings (admin only)
- Currency code/symbol, narrative rules for contributions and profit.
- **Flags** (examples): require agent on member, auto-issue certificate, require verification for certificate, investment-scoped profit, verified-only profit basis, global pool rules, accounting enabled, verified-only pool metrics.
- Company name/address/signatories for documents; **branding logos** (light/dark).

### User management (admin only)
- Create users with role **Admin**, **Operator**, or **Agent**.
- **Agent users** must be linked to an **Agent** record so scoping works.

### Audit logs (admin only)
- Who changed what (supplementary traceability for sensitive actions).

### Transactions
- Sidebar links to the contributions/transactions area for quick access (same underlying data as **Contributions**).

---

## 4. Mapping to “departments” (training tracks)

The product uses **roles**, not built-in department names. Map your org as follows:

| Your department | Typical role | Focus in training |
|-----------------|--------------|---------------------|
| **IT / System administration** | Admin | Settings, users, backups (see technical README), audit, branding |
| **Finance / Treasury** | Operator (or Admin) | Contributions, verification, subscriptions & installments, invoices, accounting module, profit distribution, trial balance |
| **Field sales / Relationship** | Agent | My team, new members (if allowed), contributions for their members, daily visibility, scoped reports |
| **Investment / PMO** | Operator / Admin | Projects, investments, profitability reports, ledger snapshots |
| **Compliance / Leadership** | Admin | Read-only or restricted operators; audit logs, exports, profit calculation reports |
| **Back-office operations** | Operator | Member data quality, subscription setup, certificate issuance |

**Suggested rollout:** (1) Admin training — settings and users. (2) Operator training — day 2 flows (member → subscription → contribution → verify). (3) Agent training — scoped UI and receipts. (4) Finance leadership — profit distribution and reports.

---

## 5. Daily operations checklist (operators)

1. Log in → **Dashboard** for totals.  
2. Record new **Contributions** and link to the right **Subscription**.  
3. **Verify** contributions once bank/cash is confirmed.  
4. Resolve **installment** statuses and follow up overdue where applicable.  
5. **Issue certificates** when fully paid (and rules satisfied).  
6. Coordinate **profit distribution** batches when management approves.  
7. Use **Reports** / exports for period close.

---

## 6. Tips and constraints

- **Agents** cannot access org-wide agent rankings, some investment/profit analytics, accounting, or admin settings — if someone needs that access, assign an **Operator** or **Admin** account.  
- **Subscription cancellation** is restricted and blocked for fully paid subscriptions.  
- **Investment deletion** is admin-only and blocked when profit or distributions exist.  
- Password changes: use **Profile**; admins manage other users under **User management**.

---

## 7. Support and documentation

- Technical setup, database, and deployment: see project **README.md** and **DEPLOYMENT.md**.  
- In-app help: **Reports → Community investment model** explains the live business metrics and narrative.

*Document version aligned with application structure (Flask app: `istithmar-investment-platform`). Update this manual when major modules or role rules change.*
