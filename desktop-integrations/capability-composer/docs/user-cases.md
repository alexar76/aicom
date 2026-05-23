# User Cases

## Case 1: Recruiter — LinkedIn Analysis to Cold Email to CRM Logging

**User:** Sarah, a technical recruiter at a staffing agency. She needs to evaluate 50+ candidates per day for fintech roles.

**Before Capability Composer:** Sarah manually opens each LinkedIn profile, takes notes, writes individual emails, and logs interactions in HubSpot. Each candidate takes 15 minutes.

**After Capability Composer:** Sarah builds a 3-node pipeline that processes a candidate in under 30 seconds.

### Pipeline

```
[pipeline_input: profile_url]
        │
        ▼
┌───────────────────────┐
│  LinkedIn Proxy v3    │  ← discovered via intent: "LinkedIn profile analysis"
│  $0.15/call           │     category: "career"
│  Output: name, role,  │
│  company, summary,    │
│  skills, experience   │
└──────────┬────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌──────────┐  ┌──────────┐
│Cold Email│  │ ATS Rules│  ← discovered via intent: "ATS scoring rules for fintech"
│Generator │  │ 2026 Q2  │     category: "career"
│$0.10/call│  │ $0.10/call│
│Output:   │  │Output:   │
│subject,  │  │score,    │
│body,     │  │keywords, │
│suggested │  │gaps      │
│email     │  │          │
└─────┬────┘  └─────┬────┘
      │             │
      └──────┬──────┘
             ▼
┌──────────────────────┐
│  CRM Contact Create  │  ← discovered via intent: "CRM contact creation from email"
│  $0.10/call         │     category: "productivity"
│  Output: contact_id,│
│  status, url        │
└──────────────────────┘
        │
        ▼
[pipeline_output: crm_contact_url, ats_score, email_preview]
```

### Sarah's Workflow

1. Sarah pastes a LinkedIn URL into the pipeline input
2. Pipeline executes: profile analysis -> ATS scoring + email generation -> CRM logging
3. Sarah reviews the output: ATS score, email preview, and CRM contact link
4. One-click approval sends the email and finalizes the CRM entry
5. Sarah repeats for the next candidate — **15 minutes per candidate becomes 30 seconds**

### Economics

```
Per-candidate cost: $0.15 (LinkedIn) + $0.10 (Email) + $0.10 (ATS) + $0.10 (CRM) = $0.45
Daily throughput (50 candidates): $22.50
Monthly cost: ~$500
Time saved per day: ~12 hours
```

---

## Case 2: Developer — Code Review to Security Scan to Deploy Check

**User:** Marcus, a lead developer on a fintech team. He needs to ensure every PR passes code review, security scanning, and deployment readiness checks before merging.

**Before Capability Composer:** Marcus runs three separate tools with different UIs, different output formats, and manual cross-referencing.

**After Capability Composer:** Marcus builds a pipeline that processes a PR diff through all three checks and produces a unified report.

### Pipeline

```
[pipeline_input: pr_diff, repo_url, base_branch]
        │
        ▼
┌──────────────────────┐
│  Code Review Agent   │  ← discovered via intent: "automated code review PR"
│  $0.20/call          │     category: "developer-tools"
│  Output: issues,     │
│  suggestions, score  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Security Scanner    │  ← discovered via intent: "security vulnerability scan code"
│  $0.25/call          │     category: "security"
│  Output: vulns,      │
│  severity, cve_ids   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Deploy Readiness    │  ← discovered via intent: "deployment readiness check"
│  $0.15/call          │     category: "devops"
│  Output: pass/fail,  │
│  risk_score,         │
│  checklist           │
└──────────┬───────────┘
           │
           ▼
[pipeline_output: summary_report, pass_fail, action_items]
```

### Marcus's Workflow

1. Marcus configures a GitHub webhook that sends new PR diffs to the pipeline
2. Pipeline executes automatically on each PR update
3. Code review catches logic errors and style issues
4. Security scanner identifies potential CVEs in new dependencies
5. Deploy readiness check validates configuration, migrations, and rollback plan
6. Unified report is posted as a PR comment with pass/fail status
7. Pipeline runs in ~45 seconds — **three separate manual reviews become one automated check**

### Economics

```
Per-PR cost: $0.20 (Code Review) + $0.25 (Security) + $0.15 (Deploy) = $0.60
PRs per day: ~15
Daily cost: ~$9.00
Monthly cost: ~$180
Value: Catches issues before they reach production. Avoids ~$50K average incident cost.
```

---

## Case 3: Marketer — Trend Detection to Content Generation to Scheduling

**User:** Priya, a content marketing manager for a B2B SaaS company. She needs to publish 3-4 high-quality, trend-aligned posts per week across LinkedIn, Twitter, and the company blog.

**Before Capability Composer:** Priya spends 2 hours daily reading industry news, 3 hours writing content, and 1 hour scheduling. By the time content publishes, trends may have shifted.

**After Capability Composer:** Priya builds a pipeline that detects trends overnight, generates drafts, and queues them for review.

### Pipeline

```
[pipeline_input: industry, keywords, target_audience]
        │
        ▼
┌──────────────────────────┐
│  Trend Detector          │  ← discovered via intent: "social media trend detection"
│  $0.30/call              │     category: "marketing"
│  Output: trends,         │
│  momentum_score,         │
│  related_topics          │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Content Generator       │  ← discovered via intent: "B2B content generation from trends"
│  $0.25/call             │     category: "marketing"
│  Output: drafts,         │
│  headlines, seo_keywords │
└──────────┬───────────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
┌──────────┐ ┌──────────┐
│LinkedIn  │ │ Twitter  │
│Formatter │ │ Formatter│
│$0.05/call│ │$0.05/call│
└─────┬────┘ └─────┬────┘
      │            │
      └─────┬──────┘
            ▼
┌──────────────────────────┐
│  Social Scheduler        │  ← discovered via intent: "social media post scheduling"
│  $0.10/call              │     category: "productivity"
│  Output: scheduled_posts,│
│  calendar_links          │
└──────────────────────────┘
        │
        ▼
[pipeline_output: drafts_for_review, schedule_links]
```

### Priya's Workflow

1. Priya sets the pipeline to run daily at 6 AM
2. Trend detector scans industry news, social media, and competitor content
3. Content generator produces 3 draft posts aligned with trending topics
4. Each draft is formatted for LinkedIn and Twitter
5. Drafts are queued in the scheduler for Priya's review at 9 AM
6. Priya reviews, tweaks, and approves — **6 hours of manual work becomes 30 minutes of curation**

### Economics

```
Per-run cost: $0.30 (Trends) + $0.25 (Content) + $0.10 (Formatting) + $0.10 (Scheduling) = $0.75
Runs per day: 1
Monthly cost: ~$22.50
Value: 3x content output with trend alignment. Estimated 5x engagement increase.
```
