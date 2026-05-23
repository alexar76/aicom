# User Cases

This document describes three detailed user cases for Interview Prep Coach, demonstrating how different personas interact with the app and the AI Market protocol.

---

## User Case 1: Job Seeker Preparing for a Google Interview

### Persona

**Name**: Priya Sharma
**Role**: Senior Software Engineer at a mid-size fintech company
**Goal**: Land a Senior SWE role at Google within 3 months
**Budget**: $30/month for interview prep
**Technical skill**: Comfortable with command-line tools and SDKs

### Scenario

Priya has a Google onsite interview in 4 weeks. She needs to prepare for behavioral questions (which she hasn't practiced in 5 years) and wants to know what questions have been asked recently at Google.

### Journey

#### Day 1: Setup

1. **Downloads and launches** Interview Prep Coach on her Linux laptop.
2. **Sees the welcome screen** explaining the marketplace model, privacy guarantees, and how she can earn credits by sharing her own interview experience later.
3. **Creates a wallet** during the setup wizard. The app generates a wallet key stored locally on her device. She funds it with $30 USDC on Base chain.
4. **Sets target**: Company = "Google", Role = "Senior Software Engineer".

#### Day 1: Discovery

5. The app's Prep tab shows three options: "Discover Question Banks", "Mock Interview", "My Progress".
6. She taps **"Discover Question Banks"**. The app calls:

```dart
final plan = await marketplace.discoverInterviewQuestions(
  company: 'Google',
  role: 'Senior Software Engineer',
  budget: 5.00,
);
```

7. The marketplace returns several capabilities:
   - `google-swe-q3-2026` — Google SWE question bank Q3 2026, $0.10/call, trust score 0.95
   - `google-swe-behavioral-2026` — Google behavioral patterns, $0.15/call, trust score 0.92
   - `google-ld-principles` — Google leadership principles guide, $0.08/call, trust score 0.88

8. She taps the **"What Was Asked This Week"** option. The app calls:

```dart
final signals = await marketplace.discoverRecentSignals(
  company: 'Google',
  role: 'Senior Software Engineer',
);
```

9. Results show 12 questions reported by candidates in the last 7 days at Google for SWE roles. She sees questions like:
   - *"Tell me about a time you had to make a decision with incomplete data."* (reported 2 days ago)
   - *"Describe a situation where you disagreed with your manager."* (reported 3 days ago)
   - *"How would you design a system for real-time collaborative editing?"* (reported 1 day ago)

**Her reaction**: "Wow, this is completely different from the LeetCode discussion board I was looking at last week. These questions are fresh."

#### Day 1: Purchase and Practice

10. She opens a $5 channel and purchases the `google-swe-q3-2026` question bank:

```dart
final result = await marketplace.getInterviewQuestions(
  capabilityId: 'google-swe-q3-2026',
  input: {
    'target_role': 'Senior Software Engineer',
    'years_experience': 8,
    'focus_areas': ['leadership', 'conflict_resolution', 'technical_debt'],
    'difficulty': 'hard',
  },
);
```

11. The result returns 10 behavioral questions with:
   - Full question text
   - Key points interviewers are looking for
   - Suggested answer framework (STAR method)
   - Common mistakes to avoid

12. She practices in the app's built-in mock interview mode. The app shows each question with a timer. She types her answer, then the app provides AI feedback on:
   - STAR structure completeness
   - Key point coverage
   - Conciseness
   - Suggested improvements

#### Day 14: Progress Check

13. After two weeks of practice, she checks **"My Progress"**:
   - 45 questions practiced
   - Average score improved from 62% to 81%
   - Weakest area: "conflict resolution" (she focuses on this)
   - Comparison with market: her answers are in the 73rd percentile

#### Day 28: After the Interview

14. Priya's Google interview included **2 of the exact questions** she had purchased from the marketplace. She prepared using the key points and felt confident.

15. **She receives an offer** from Google.

16. She shares her experience on the marketplace:

```dart
await marketplace.submitAnonymizedTrajectory(
  trajectory: {
    'question': 'Tell me about a time you led a cross-functional project',
    'answer_summary': 'I led a migration of our payment system... [STAR format]',
    'outcome': 'offer',
    'company': 'Google',
    'role': 'Senior Software Engineer',
    'difficulty': 'hard',
  },
  capabilityId: 'google-swe-trajectory-submit',
);
```

17. She earns $0.25 in marketplace credits for her contribution. Over time, as other candidates purchase her trajectory, she earns passive credits that fund her future interview prep (for the next round of negotiations or for helping friends).

### Outcome

- Priya landed her dream job at Google.
- She spent $7.50 on question banks and earned $0.25 back from her trajectory submission.
- The marketplace now has one more verified trajectory for Google SWE, helping future candidates.
- Priya continues using the app to prepare for follow-up interviews (team matching).

---

## User Case 2: Career Coach Managing Multiple Candidates

### Persona

**Name**: James Chen
**Role**: Independent career coach specializing in big tech placements
**Clients**: 15 active clients targeting FAANG companies
**Goal**: Efficiently prepare candidates with up-to-date interview materials
**Budget**: $100/month (billed to clients as part of coaching package)

### Scenario

James has 15 clients at various stages of interview preparation for Google, Meta, Amazon, and Apple. He needs to:
1. Quickly find relevant question banks for each client's specific company/role
2. Track each client's progress
3. Identify which companies are currently asking which questions
4. Generate reports for clients showing their readiness

### Journey

#### Setup

1. James installs Interview Prep Coach on his MacBook.
2. During setup, he enters his wallet and funds it with $100.
3. He does NOT set a single target company — instead, he uses the app's "multi-target" mode (switching between clients).

#### Daily Workflow

**8:00 AM — Review fresh signals across all companies:**

```dart
// James runs a batch discovery for all his clients' target companies
final googleSignals = await marketplace.discoverRecentSignals(
  company: 'Google', role: 'SWE',
);
final metaSignals = await marketplace.discoverRecentSignals(
  company: 'Meta', role: 'Product Manager',
);
final amazonSignals = await marketplace.discoverRecentSignals(
  company: 'Amazon', role: 'Senior SDE',
);
```

He sees a new trend: Google has been asking more "system design for AI/ML" questions this week, while Meta is focusing on "product sense." He adjusts his coaching plan accordingly.

**9:00 AM — Client session: Sarah (Amazon Senior SDE):**

1. James opens Sarah's profile in the app.
2. He purchases the `amazon-sde-leadership-2026` capability:

```dart
final leadershipQs = await marketplace.getInterviewQuestions(
  capabilityId: 'amazon-sde-leadership-2026',
  input: {
    'role': 'Senior SDE',
    'years_experience': 6,
    'focus_areas': ['ownership', 'hire_and_develop', 'dive_deep'],
    'include_lp_questions': true,
  },
);
```

3. The capability returns 15 Amazon leadership principle questions, each tagged with which LP it tests.
4. James and Sarah practice together. James uses the app's feedback to guide Sarah's answer improvement.

**11:00 AM — Client session: Mike (Meta Product Manager):**

1. James switches to Mike's profile. Target company = Meta, role = Product Manager.
2. He discovers Meta PM-specific question banks:

```dart
final metaPM = await marketplace.discoverInterviewQuestions(
  company: 'Meta', role: 'Product Manager',
);
```

3. He purchases the `meta-pm-product-sense-2026` capability:

```dart
final pmQuestions = await marketplace.getInterviewQuestions(
  capabilityId: 'meta-pm-product-sense-2026',
  input: {
    'role': 'Product Manager',
    'years_experience': 4,
    'focus_areas': ['product_sense', 'execution', 'analytics'],
  },
);
```

4. The result includes product sense questions like:
   - *"If you were to launch a new feature for Facebook Groups, what would it be and how would you measure success?"*
   - *"How would you improve Instagram Reels to compete with TikTok?"*

#### Weekly Reporting

James exports progress reports for each client:

```
Client Progress Report: Sarah Chen
Company: Amazon | Role: Senior SDE
Week of: 2026-05-18

Questions practiced: 32
Categories covered:
  - Leadership Principles: 15 (avg score: 78%)
  - System Design: 8 (avg score: 65%)
  - Behavioral: 9 (avg score: 82%)

Top improvement area: System Design (focus on scalability patterns)
Strength: Leadership Principle stories (well-structured STAR)

Market intelligence:
  - Amazon asking more "Ownership" questions this quarter (+23% vs Q2)
  - New focus area: "Cost optimization at scale" emerging this week
```

#### Marketplace Contribution

As an expert coach, James contributes high-quality trajectory data:

```dart
await marketplace.submitAnonymizedTrajectory(
  trajectory: {
    'question': 'Tell me about a time you had to push back against a timeline',
    'answer_summary': 'I identified a critical security issue...',
    'outcome': 'offer', // client got the offer
    'company': 'Amazon',
    'role': 'Senior SDE',
    'difficulty': 'medium',
    'coach_notes': 'Candidate used structured STAR with measurable impact',
  },
  capabilityId: 'coach-trajectory-submit',
);
```

James's trajectories sell at a premium because his clients have a high offer rate. His marketplace trust score is 0.97.

### Outcome

- James provides better, more current coaching than competitors using static materials.
- His clients see 40% higher offer rates (his marketing claim, backed by data).
- He earns ~$15/month in passive marketplace credits from his trajectory submissions.
- The marketplace benefits from high-quality, expert-verified trajectory data.

---

## User Case 3: HR Platform Embedding Interview Prep as a Feature

### Persona

**Organization**: TalentBridge HR (a mid-size HR SaaS platform)
**Users**: 500 enterprise customers managing 50,000+ candidates
**Goal**: Embed interview preparation into their talent management platform
**Constraint**: Cannot build a full interview prep product — needs to source content
**Technical approach**: White-label the Interview Prep Coach data via the AI Market API

### Scenario

TalentBridge wants to offer interview preparation to candidates in their pipeline. Instead of building question banks from scratch (which would take months and quickly become stale), they integrate with the AI Market protocol to source content programmatically.

### Integration Architecture

TalentBridge's backend (Python) integrates with the AI Market Hub:

```python
# TalentBridge backend integration (Python)
import requests

HUB_URL = "https://hub.aicom.io"
API_KEY = "talentbridge-api-key"

def get_question_bank(company, role, difficulty="medium"):
    """Fetch interview questions for a candidate's target company."""
    response = requests.get(
        f"{HUB_URL}/ai-market/v2/search",
        params={
            "intent": f"{company} {role} behavioral questions",
            "budget_usd": "0.50",
            "category": "career",
            "limit": 5,
        },
        headers={"X-AIMarket-Affiliate": "talentbridge-hr-platform"},
    )
    return response.json()

def invoke_capability(capability_id, input_data):
    """Purchase and invoke a question bank capability."""
    channel = open_channel(5.00)
    response = requests.post(
        f"{HUB_URL}/ai-market/v2/invoke",
        headers={
            "X-Payment-Channel": channel["channel_id"],
            "X-Market-Signature": sign(channel["channel_id"], capability_id),
            "Content-Type": "application/json",
        },
        json={
            "capability_id": capability_id,
            "input": input_data,
        },
    )
    close_channel(channel["channel_id"])
    return response.json()
```

### User Experience on TalentBridge

When a candidate is scheduled for an interview, the TalentBridge platform:

1. **Detects the target company** from the candidate's application (e.g., "Microsoft, Senior SWE").
2. **Queries the AI Market** for relevant question banks.
3. **Purchases 10 questions** from the best-rated capability (cost: $1.00-$2.00 per candidate).
4. **Presents questions** in TalentBridge's branded practice interface.
5. **Collects anonymized feedback** (candidate's self-assessment, not raw answers) and submits as market trajectory.

### Candidate Flow

```
TalentBridge Dashboard
│
├── Candidate: Alex Rivera
│   ├── Stage: Interview Scheduled (Microsoft, Senior SWE)
│   ├── Interview Date: 2026-05-30
│   ├── [Prepare for Interview] ← NEW button
│   │
│   └── Interview Prep Portal (TalentBridge branded)
│       ├── "Questions asked at Microsoft this month" (3)
│       ├── "Top behavioral questions for Senior SWE" (7)
│       ├── "System design scenarios" (5)
│       │
│       └── Practice mode
│           ├── Question 1 of 5
│           ├── Timer: 04:32
│           ├── Your answer: [text area]
│           └── [Submit for feedback]
│
└── Analytics Dashboard (Hiring Manager)
    ├── Candidate preparation score: 78/100
    ├── Coverage: Behavioral 85%, Technical 70%, System Design 60%
    └── Compared to market: Above average for Microsoft SWE candidates
```

### Privacy Considerations for Enterprise

TalentBridge must be transparent about data handling:

1. **Candidate answers are processed on-device** (via embedded Flutter web component or Electron app).
2. **Only anonymized trajectories** are submitted to the marketplace.
3. **TalentBridge does not share** candidate names, contact info, or specific answer text.
4. **Enterprise contract** specifies that candidate data is processed under TalentBridge's DPA.

### Enterprise Benefits

| Metric | Before (static content) | After (marketplace) |
|---|---|---|
| Content freshness | 3-6 months stale | Updated within days |
| Question bank breadth | 5 companies, 3 roles | 50+ companies, 20+ roles |
| Content cost | $50,000/year (internal team) | $0.10-$0.50 per candidate |
| Candidate offer rate | 22% | 34% (+12pp) |
| Time-to-prepare | 2 weeks (research) | 3 days (targeted practice) |

### Outcome

- TalentBridge differentiates its platform with current, marketplace-sourced interview prep.
- Candidates feel better prepared and perform better.
- The marketplace gains a steady stream of enterprise-submitted trajectories.
- TalentBridge saves $50K/year by not maintaining an internal content team.
- The AI Market proves its value as a B2B data sourcing layer.
