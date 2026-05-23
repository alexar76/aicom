# User Cases

## Case 1: Buyer Checking Seller Reputation Before Purchase

**Persona:** Alex, a technical recruiter looking for an ATS scoring capability.

**Goal:** Ensure the capability they are about to purchase has a proven track record from
real buyers.

**Flow:**

1. Alex opens the Reputation Dashboard and selects the **Career** category.
2. The dashboard displays a ranked list of capabilities sorted by trust score:

   ```
   ┌─────────────────────────────────────────────────────────────┐
   │  Career Category — Top 10 by Trust Score                    │
   ├──────────────┬──────────┬────────┬──────────┬───────────────┤
   │ Capability   │  Rating  │ Reviews│ Trust    │ Price         │
   ├──────────────┼──────────┼────────┼──────────┼───────────────┤
   │ ATS Score v3 │ ★4.8     │ 47     │ 4.8      │ $0.50/run     │
   │ Resume Parse │ ★4.5     │ 32     │ 4.5      │ $0.30/run     │
   │ Skill Match  │ ★4.2     │ 18     │ 4.0      │ $0.40/run     │
   │ ...          │          │        │          │               │
   └──────────────┴──────────┴────────┴──────────┴───────────────┘
   ```

3. Alex clicks **ATS Score v3** to see detailed reviews.
4. The detail view shows a trust score timeline (30-day trend), rating distribution
   histogram, and the 10 most recent reviews.
5. Alex reads a review: *"Used this for 200+ fintech role screenings. Accuracy is
   consistently above 92% compared to manual review."* — verified purchase.
6. Satisfied, Alex proceeds to purchase the capability in the main marketplace.

**Value:** Without the dashboard, Alex would be choosing blindly. The reputation layer
converts an uncertain purchase into a confident one.

---

## Case 2: Seller Monitoring Their Trust Score

**Persona:** Jordan, a developer who publishes three capabilities on the marketplace
(ATS scoring, resume parsing, skill gap analysis).

**Goal:** Track reputation metrics across their portfolio and identify areas for
improvement.

**Flow:**

1. Jordans opens the Reputation Dashboard and connects their seller wallet.
2. The dashboard detects Jordan's published capabilities and shows a **Seller Console**:

   ```
   ┌─────────────────────────────────────────────────────────────┐
   │  Seller Console — jordan.eth                                │
   ├──────────────┬──────────┬──────────┬───────────┬────────────┤
   │ Capability  │ Rating   │ Reviews  │ Trend     │ Response   │
   ├──────────────┼──────────┼──────────┼───────────┼────────────┤
   │ ATS Score   │ ★4.8     │ 47       │ ▲ +0.1    │ —          │
   │ Resume Parse│ ★4.5     │ 32       │ ▼ -0.3    │ ⚠ 1 new   │
   │ Skill Gap   │ ★3.2     │ 8        │ ▼ -0.7    │ ⚠ 3 new   │
   └──────────────┴──────────┴──────────┴───────────┴────────────┘
   ```

3. Jordan sees that **Skill Gap** has a declining trend and 3 new reviews to respond to.
4. Clicking into the detail, Jordan reads:
   - *"Doesn't handle non-tech roles well. Got poor results for healthcare positions."*
   - *"The output format is hard to parse programmatically."*
5. Jordan uses the dashboard's **Reply to Review** feature to acknowledge the feedback
   and commits to adding healthcare industry support in the next release.
6. Over the following week, Jordan releases an update and sees the trend line
   stabilize.

**Value:** The dashboard gives sellers a direct feedback channel and a quantifiable
reputation metric that directly impacts their marketplace success.

---

## Case 3: Marketplace Curator Identifying Quality Capabilities

**Persona:** Taylor, a community curator responsible for maintaining quality standards
on the AI Marketplace.

**Goal:** Identify high-quality capabilities for featured placement and detect
low-quality or potentially fraudulent capabilities.

**Flow:**

1. Taylor opens the Reputation Dashboard and switches to **Curator Mode** using their
   curator wallet key.
2. The curator console shows a matrix view of all categories with outlier detection:

   ```
   ┌───────────────────────────────────────────────────────────────┐
   │  Curator Console — Outlier Detection                         │
   ├────────────────┬──────────┬──────────┬───────────┬───────────┤
   │ Category       │ Top Perf.│ Lowest   │ Flagged   │ Action    │
   ├────────────────┼──────────┼──────────┼───────────┼───────────┤
   │ career         │ 4.8      │ 1.2 ⚑    │ 2         │ Review    │
   │ devops         │ 4.7      │ 2.1      │ 0         │ —         │
   │ analyst        │ 4.9      │ 1.5 ⚑    │ 1         │ Review    │
   │ sales          │ 4.6      │ 3.0      │ 0         │ —         │
   │ hardening      │ 4.4      │ 1.8 ⚑    │ 3         │ Review    │
   └────────────────┴──────────┴──────────┴───────────┴───────────┘
   ```

3. Taylor clicks on the `career` flagged entry and sees a capability with:
   - 5.0 average rating but only 1 review
   - All reviews from the same wallet
   - No purchase transaction link (suspects fake review)
4. Taylor flags the capability for further investigation and, if confirmed fraudulent,
   delists it from the marketplace.
5. Separately, Taylor identifies the top-performing capabilities across categories and
   adds them to the **Featured** section of the marketplace homepage.

**Value:** The dashboard gives curators the tools to maintain marketplace quality at
scale, separating signal from noise in a growing ecosystem.
