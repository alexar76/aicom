# User Cases

## Case 1: Freelance developer reviewing a client contract

### Persona
**Alex**, a freelance full-stack developer based in Berlin. They have a recurring client who sent a 12-page software development SOW. Alex charges €120/hr but has never hired a lawyer. The contract is in English with German governing law.

### Scenario

Alex receives the contract PDF via email and drops it onto the Freelance Contract Reviewer dashboard.

1. **Local parse**: The app splits the contract into clauses — scope of work, payment terms, IP ownership, confidentiality, termination, liability cap.
2. **Marketplace discovery**: Alex searches for "German software development contract IP clause library". The marketplace returns a capability bundle for €4.99 from a Berlin-based legal tech publisher.
3. **Purchase**: Alex deposits $5 into a payment channel and purchases the library.
4. **TEE execution**: The app verifies the TEE attestation, then sends the anonymized IP clause and payment clause to the enclave for evaluation.
5. **Results**:
   - **Red flag**: The IP assignment clause grants the client "all intellectual property rights" with no license back to Alex. The library flags this as high risk under German copyright law (UrhG § 69b).
   - **Yellow flag**: The liability cap is set to the contract value, which is unusually low for software development.
   - **Green**: Payment terms (net-30) and termination (14-day notice) are standard.
6. **Outcome**: Alex asks the client to amend the IP clause to a "license to use" rather than full assignment. The contract is revised. Alex paid $4.99 instead of $400+ for a lawyer.

### Anonymized sell (opt-in)

The app asks: *"Would you like to anonymize and sell this 'overbroad IP assignment' clause pattern?"* Alex clicks yes. The pattern is stripped of client name, project details, and amounts, then submitted to the marketplace. Alex earns $0.15.

---

## Case 2: Designer checking IP clause in a branding contract

### Persona
**Mia**, a freelance graphic designer in Los Angeles. She works with startups and routinely signs branding/project-based contracts. A new client sent a one-page SOW for a logo + brand identity package, $8,000.

### Scenario

Mia opens the contract in the reviewer.

1. **Local parse**: The app detects a short contract with only 5 clauses. The IP clause is particularly important for designers — who owns the final logo files?
2. **Marketplace discovery**: Mia searches for "California freelance designer IP lawyers for designers clause library". The marketplace returns a $6.99 library published by a California creative-rights advocacy group.
3. **TEE evaluation**: The library examines the IP clause text. Key findings:
   - **Red flag**: The clause says "all work product" transfers upon payment, with no portfolio rights retained.
   - **Explanation**: Under California Civil Code § 3426, trade secrets and preliminary sketches may still be protected, but the clause as written is overbroad.
   - **Suggestion**: Add a sentence: *"Designer retains the right to display the work in their portfolio and to use it for self-promotion."*
4. **Outcome**: Mia counters with the suggested amendment. The client accepts. Total cost: $6.99.

### Without the app

Mia would have either signed without reading the IP clause (common), or paid a lawyer ~$300–$500 for a 30-minute review.

---

## Case 3: Consultant verifying a non-compete clause

### Persona
**Jordan**, a management consultant in New York. They have an engagement with a private equity firm that includes a 12-month non-compete clause covering "any financial services client worldwide."

### Scenario

Jordan uploads the engagement letter.

1. **Local parse**: The app identifies a non-compete clause with a 12-month duration, unlimited geographic scope, and a broad industry definition.
2. **Marketplace discovery**: Jordan purchases a "New York non-compete enforceability 2026" library for $8.99. It was published by a law firm specializing in restrictive covenants.
3. **TEE evaluation**: The library analyzes the non-compete against New York case law:
   - **Red flag**: New York courts generally reject non-competes exceeding 6 months for consultants (see *BDO Seidman v. Hirshberg*, 93 N.Y.2d 382).
   - **Red flag**: Worldwide scope is almost certainly unenforceable. New York requires geographic scope to be "reasonable and related to the employer's legitimate interests."
   - **Yellow flag**: "Any financial services client" is too broad — the clause should be limited to clients Jordan actually worked with.
   - **Suggestion**: Propose a 6-month term, limited to direct client relationships, and restricted to the U.S.
4. **Outcome**: Jordan negotiates the non-compete down to 6 months and U.S.-only scope. The clause is now likely enforceable but no longer blocks Jordan from taking other PE clients.
5. **Anonymized sell**: Jordan's anonymized "overbroad non-compete" pattern is sold to the marketplace, earning $0.30.

### Marketplace data value

Over time, the marketplace accumulates patterns like:

> _non_compete | ny | unreasonable_duration_12m | high_dispute_rate: 73% | median_settlement_usd: 12000

This data becomes a valuable resource for both freelancers and publishers. Contributors earn royalties on every resale.
