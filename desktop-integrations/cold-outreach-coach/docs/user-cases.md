# User Cases

## Case 1: B2B Sales Rep — SaaS Cold Outreach

### Persona

**Name:** Maya Chen  
**Role:** Senior SDR at CloudScale Technologies  
**Team:** 8 SDRs, targeting VP Engineering / CTO at mid-market SaaS companies  
**Stack:** Salesforce + Outreach.io + Cold Outreach Coach  

### Problem

Maya sends 80-100 cold emails per day. Her reply rate dropped from 4.2% to 1.8% over two months. The team suspects Gmail's spam filters changed — their usual templates are landing in Promotions or Spam. Maya needs to understand what's triggering the filters and adapt before her pipeline dries up.

### Solution with Cold Outreach Coach

#### Step 1: Discover current rules

Maya opens the Marketplace tab and searches for deliverability rules:

```dart
final plan = await agent.discover(
  intent: 'email deliverability rules for cold outreach Q2 2026',
  category: 'career',
);
```

The marketplace returns 3 relevant capabilities:

| Capability | Price | Trust Score | Description |
|------------|-------|-------------|-------------|
| SPF/DKIM Checker 2026 Q2 | $0.10/call | 0.97 | Latest SPF, DKIM, DMARC rules for Gmail/Outlook |
| Content Heuristics Bundle | $0.25/call | 0.94 | Structural patterns triggering modern spam filters |
| Sender Reputation Scanner | $0.15/call | 0.91 | Domain warm-up status and blacklist check |

#### Step 2: Check deliverability

Maya opens a $5 channel and runs the Content Heuristics Bundle against a draft email:

```dart
final channel = await agent.openChannel(5.00);

final result = await agent.invoke(
  capabilityId: 'content-heuristics-2026-q2',
  input: {
    'industry': 'saas',
    'target_role': 'VP Engineering',
    'word_count': 112,
    'paragraph_count': 5,
    'has_questions': true,
    'link_count': 3,
    'contains_attachment': false,
    'greeting_type': 'personalized_first_name',
    'closing_type': 'standard',
  },
  channelId: channel.id,
);
```

**Result:**
```json
{
  "deliverability_score": 72,
  "warnings": [
    "Link density above threshold: 3 links in 112 words (2.7%) — recommended <2%",
    "Paragraph count 5 may trigger Gmail clipping in mobile preview",
    "No SPF record detected for sending domain"
  ],
  "recommendations": [
    "Reduce to max 2 links or use plain-text URLs",
    "Merge paragraphs 4-5 into a single closing paragraph",
    "Add SPF TXT record: v=spf1 include:sendgrid.net ~all"
  ]
}
```

#### Step 3: Apply and iterate

Maya adjusts her email:
- Removes one link (2 links, 1.8% density)
- Merges closing paragraphs (4 paragraphs total)
- Asks IT to add the SPF record

She re-runs the check — score improves to 89.

#### Step 4: Track results

Over the next two weeks, Maya's reply rate climbs back to 3.9%. She anonymizes her successful structural pattern and contributes it to the marketplace, earning $0.01 per anonymized signal purchase.

### Key takeaway

Without the marketplace, Maya would need to A/B test blindly for weeks. With Cold Outreach Coach, she knows exactly what's wrong in 30 seconds and fixes it before hitting send.

---

## Case 2: Freelancer — Proposal Optimization

### Persona

**Name:** James Okafor  
**Role:** Senior UX/UI Designer (freelance)  
**Platform:** Upwork + direct outreach  
**Volume:** 50 personalized proposals per month  
**Current reply rate:** 4% (2 replies from 50 proposals)

### Problem

James spends 3-4 hours writing each proposal. His reply rate is 4% — well below the 15-25% benchmark for senior designers. He suspects his proposals are too long and detailed, causing potential clients to skim or skip. He needs structural benchmarks from the freelance market to optimize.

### Solution with Cold Outreach Coach

#### Step 1: Benchmark his current structure

James pastes his last 10 proposals into the Composer tab. The structural analyzer gives him:

| Metric | His average | Marketplace benchmark (freelance) |
|--------|-------------|-----------------------------------|
| Word count | 320 | 80-150 |
| Paragraphs | 8 | 3-4 |
| Questions | 0 | 1-2 |
| Links (portfolio) | 4 | 1 |
| Personalization tokens | 1 (name only) | 3+ (name, project details, mutual connection) |

#### Step 2: Discover freelance-specific patterns

He searches the marketplace for freelance proposal benchmarks:

```dart
final plan = await agent.discover(
  intent: 'freelance cold proposal reply rate signals 2026',
  budget: 3.00,
  category: 'career',
);
```

Results show that the highest-reply freelance proposals share:

1. **80-120 words** — longer proposals have a 60% lower reply rate
2. **Question in first paragraph** — increases reply rate by 34%
3. **Exactly 1 link** — more than 1 link reduces reply rate by 22%
4. **Project-specific detail** — generic proposals score 40% lower

#### Step 3: Restructure

James rewrites a proposal:

```
Before (320 words, 8 paragraphs, 0 questions, 4 links):
"I am a senior UX/UI designer with 8 years of experience...
[detailed portfolio descriptions...]
[4 links to different projects...]
I look forward to hearing from you."

After (98 words, 3 paragraphs, 1 question, 1 link):
"Hi [name] — I saw your project about [specific detail].
Would you prefer a mobile-first or desktop-first approach for the dashboard?

I recently solved a similar navigation problem for a fintech SaaS
[link to relevant case study].

[2 sentences of specific domain expertise related to project.]

Happy to jump on a quick call to discuss your specific needs."
```

#### Step 4: Measure improvement

Over the next month, James's reply rate increases from 4% to 22%. He contributes his anonymized template to the marketplace, earning passive income from other freelancers who purchase the signal data.

### Key takeaway

James didn't need a better portfolio — he needed structural feedback. The marketplace gave him benchmarks from thousands of anonymized freelance proposals that proved shorter, question-first messages outperform longer ones.

---

## Case 3: Recruiter — Candidate Outreach at Scale

### Persona

**Name:** Priya Sharma  
**Role:** Technical Recruiter at ScaleUp Talent Partners  
**Clients:** Series B/C startups hiring engineers  
**Volume:** 200+ personalized InMails/emails per week  
**Challenge:** InMail acceptance rate 8%, but reply-to-acceptance conversion only 30%

### Problem

Priya sends 200+ messages per week. Her initial InMail acceptance rate is 8%, which is industry average. But only 30% of accepted InMails result in a reply. Candidates accept, read, and don't respond. She needs to understand what structural patterns cause accepted InMails to convert to replies.

### Solution with Cold Outreach Coach

#### Step 1: Analyze the drop-off

Priya segments her last 500 InMails by structural pattern. She finds a clear signal: InMails with 4+ paragraphs have a 48% lower reply-after-acceptance rate than those with 2-3 paragraphs. But the marketplace confirms this is a known pattern.

#### Step 2: Discover recruiter-specific signals

She searches the marketplace:

```dart
final plan = await agent.discover(
  intent: 'recruiter outreach reply rate optimization technical candidates 2026',
  budget: 10.00,
  category: 'career',
);
```

The marketplace returns a specialized bundle for technical recruiting:

| Pattern | Impact on reply rate | Source |
|---------|---------------------|--------|
| 2-3 paragraphs (vs 4+) | +48% | Anonymized recruiter data |
| Salary range in first message | +35% | 15,000+ anonymized InMails |
| Tech stack mentioned in first sentence | +28% | Engineering candidates |
| "Why this company" paragraph | +22% | Retention-focused |
| Multiple links to job descriptions | -18% | Avoid in initial message |
| Greeting without name | -31% | Shows bulk sending |

#### Step 3: Build a template

Priya builds a data-driven template:

```
Hi [name] —

I'm reaching out because [specific_reason_related_to_their_stack]
at [client_company]. We're building [product] and need someone
with your [specific_skill].

Role: [title] — [salary_range]
Stack: [tech_stack] | Remote: [yes/no]

[Client elevator pitch — 1-2 sentences.]

Interested in a 15-min chat this week?

Best,
Priya
```

Structural metrics:
- Word count: 85-110
- Paragraphs: 3
- Questions: 1
- Links: 0 (in initial message)
- Personalization tokens: 3 (name, stack, specific reason)

#### Step 4: Deploy at scale

Priya uses the CSV import feature to upload her prospect list. The app bulk-checks each message's structural pattern against marketplace rules before sending.

#### Step 5: Results

Over 6 weeks:

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| InMail acceptance rate | 8% | 11% | +37% |
| Reply-after-acceptance | 30% | 52% | +73% |
| Overall conversion | 2.4% | 5.7% | +138% |

### Key takeaway

Priya didn't need better candidates — she needed better structure. The marketplace's anonymized signal aggregation showed her exactly what patterns work for technical candidates. She now contributes her own anonymized data, earning marketplace credits while the entire recruiter ecosystem improves.

---

## Cross-Case Learnings

| Pattern | B2B SaaS | Freelance | Recruiter |
|---------|----------|-----------|-----------|
| Optimal word count | 50-125 | 80-150 | 85-110 |
| Optimal paragraphs | 3-4 | 3-4 | 3 |
| Questions boost reply | +30% | +34% | +25% |
| Link density threshold | <2% | 1 link max | 0 links (initial) |
| Personalization minimum | 2 tokens | 3 tokens | 3 tokens |
| SPF/DKIM impact | Critical | Moderate | Low (platform DMs) |
| Market data freshness | Weekly | Bi-weekly | Weekly |

These benchmarks are **anonymized** — they aggregate structural patterns from thousands of users without exposing any individual's email content, prospect names, or company data.
