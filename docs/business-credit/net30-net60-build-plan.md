# Lion Elite Business Credit Build Plan

_Last reviewed: August 4, 2026_

## Objective
Build a legitimate commercial credit profile for Lion Elite by opening useful vendor accounts, paying every invoice early, and verifying that tradelines appear on Dun & Bradstreet, Experian Business, and Equifax Business.

## Rules
1. Use the exact same legal business name, EIN, D-U-N-S number, address, phone, website, and business email on every application.
2. Buy only products the business actually uses.
3. Never carry a balance for credit-building purposes.
4. Pay invoices 10–15 days before the due date.
5. Save approvals, invoices, payment confirmations, and account numbers.
6. Verify bureau reporting after 30–90 days; reporting policies can change.

## Recommended sequence

### Phase 1 — Apply now

#### 1. Quill Net 30
- Purpose: office supplies, printer paper, labels, shipping-office necessities.
- Current terms: qualified businesses can receive Net 30; current application requires a $100 cart minimum.
- Reporting: commonly identified by current business-credit sources as a reporting vendor, but confirm directly before relying on it.
- Action: create a business account, place one legitimate $100+ order, request Net 30 at checkout, and pay 10–15 days early.

#### 2. Uline Net 30
- Purpose: shipping boxes, mailers, labels, gloves, shelving, packaging and warehouse supplies.
- Current terms: qualified businesses may select “Invoice Me” for Net 30; first invoiced order initiates credit review.
- Reporting: Uline does not publicly identify its bureaus; third-party sources commonly report Experian Business activity. Confirm with Uline and monitor reports.
- Action: order packaging Lion Elite already needs, choose Invoice Me if offered, and pay early.

#### 3. Shirtsy Net 30
- Purpose: branded shirts, staff uniforms, event apparel, customer merchandise and promotional products.
- Current terms: $99 annual membership, up to a stated $6,000 line, no personal guarantee, same-day decisions advertised.
- Reporting: Shirtsy currently states it reports to D&B, Equifax, and Creditsafe.
- Action: apply only if Lion Elite will actually use branded apparel or promotional products; place a real order and pay early.

### Phase 2 — Add after first approvals

#### 4. Grainger Open Account / Net 30
- Purpose: facility, maintenance, storage, safety, cleaning and operational supplies.
- Current terms: Net 30 for customers with established Grainger credit; approval is discretionary.
- Reporting: do not assume. Ask the credit department which business bureaus receive payment data before applying solely for credit building.
- Action: apply after at least one starter account is approved and paid.

#### 5. Existing suppliers as trade references
- Ask packaging, printing, laboratory-supply, fulfillment, rent, utilities, software or wholesale vendors whether they report commercial payment experiences.
- If they do not report automatically, consider submitting legitimate paid vendors as D&B trade references where eligible; acceptance is subject to D&B verification.

## Net 60 strategy
Do not prioritize Net 60 merely because the term is longer. For credit building, bureau reporting, useful purchases, low fees and clean payment history matter more than 60-day terms. Add Net 60 only when the vendor serves a real operational need and confirms bureau reporting.

## 90-day execution schedule

### Day 0
- Verify the D&B profile and all business identity information.
- Apply to Quill and Uline.
- Apply to Shirtsy only if the $99 fee and products make business sense.
- Record every application in the tracker below.

### Days 7–15
- Pay any posted invoices early.
- Save proof of payment.
- Do not submit many additional applications at once.

### Days 30–45
- Check D&B, Experian Business and Equifax Business reports.
- Confirm each account is associated with the correct EIN and D-U-N-S profile.
- Contact vendors whose tradelines do not appear and ask about reporting cycles.

### Days 45–60
- Add Grainger or another genuinely useful vendor.
- Request modest credit-limit increases only after successful payment history.

### Days 60–90
- Verify at least three reporting payment experiences.
- Keep utilization low and invoices paid early.
- Evaluate store cards, fleet cards or business cards only after the commercial file is established.

## Application tracker

| Vendor | Applied | Approved | Limit | Purchase | Invoice date | Due date | Paid date | Bureau confirmed | Tradeline appeared |
|---|---|---|---:|---:|---|---|---|---|---|
| Quill |  |  |  |  |  |  |  |  |  |
| Uline |  |  |  |  |  |  |  |  |  |
| Shirtsy |  |  |  |  |  |  |  |  |  |
| Grainger |  |  |  |  |  |  |  |  |  |

## Verification call script
“Before I apply, can you confirm whether this business account reports payment history to Dun & Bradstreet, Experian Business, Equifax Business, Creditsafe, or the Small Business Financial Exchange? How frequently do you report, and is there a minimum purchase or account activity requirement for reporting?”

## Claude Code task prompt
Use this prompt inside Claude Code when maintaining the repository:

> Review `docs/business-credit/net30-net60-build-plan.md`. Research each vendor using current official vendor pages first and reputable secondary sources second. Update terms, fees, eligibility, minimum purchases, personal-guarantee requirements, bureaus reported to, and the date verified. Clearly mark reporting as “vendor-confirmed,” “third-party reported,” or “unverified.” Never present a vendor as reporting unless current evidence supports it. Preserve the execution plan and tracker.
