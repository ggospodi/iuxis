#!/usr/bin/env python3
"""Seed Iuxis with 2 demo projects for first-time users."""

import json
import sqlite3
import os
from datetime import datetime, timedelta, date

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "iuxis.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def seed_demo():
    conn = get_connection()

    # Check if demo data already exists
    existing = conn.execute("SELECT COUNT(*) FROM projects WHERE tags LIKE '%demo%'").fetchone()[0]
    if existing > 0:
        print("Demo data already exists. Skipping seed.")
        conn.close()
        return

    today = date.today()

    # -------------------------------------------------------------------------
    # Demo Project 1: NovaBrew (P1, product)
    # -------------------------------------------------------------------------
    conn.execute("""
        INSERT INTO projects (name, type, status, priority, description,
                              time_allocation_hrs_week, current_focus, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "NovaBrew",
        "product",
        "active",
        1,
        "AI-powered coffee subscription platform. Personalizes blends based on taste preferences and brewing method. Currently in beta with 200 subscribers.",
        25.0,
        "Launch referral program and onboard 3 new roastery partners",
        json.dumps(["demo", "saas", "consumer", "subscription"]),
    ))
    novabrew_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # NovaBrew sub-projects
    sub_projects_1 = [
        ("NovaBrew Mobile App", "product", "active", 1,
         "React Native mobile app for subscription management and brew guides.",
         10.0, "Push notification system for delivery updates", novabrew_id),
        ("NovaBrew Analytics", "product", "active", 2,
         "Customer taste profile analytics and churn prediction dashboard.",
         8.0, "Build cohort retention charts for investor deck", novabrew_id),
        ("NovaBrew Partnerships", "company", "active", 2,
         "Roastery partner onboarding and supply chain coordination.",
         5.0, "Finalize terms with Blue Ridge Roasters and Archipelago Coffee", novabrew_id),
    ]

    sub_ids_1 = {}
    for name, ptype, status, priority, desc, time_alloc, focus, parent in sub_projects_1:
        conn.execute("""
            INSERT INTO projects (name, type, status, priority, description,
                                  time_allocation_hrs_week, current_focus, parent_id, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, ptype, status, priority, desc, time_alloc, focus, parent, json.dumps(["demo"])))
        sub_ids_1[name] = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # NovaBrew tasks
    tasks_1 = [
        # Top-level NovaBrew tasks
        (novabrew_id, "Launch Referral Program", 1, "in_progress", 8.0,
         "Design and ship referral system — $5 credit per successful referral",
         (today + timedelta(days=7)).isoformat()),
        (novabrew_id, "Onboard Blue Ridge Roasters", 1, "todo", 4.0,
         "Contract review, API integration for inventory sync",
         (today + timedelta(days=10)).isoformat()),
        (novabrew_id, "Fix Subscription Pause Flow", 2, "todo", 3.0,
         "Users report confusion when pausing — simplify the UX",
         (today + timedelta(days=5)).isoformat()),
        (novabrew_id, "Prepare Series A Materials", 2, "todo", 12.0,
         "Deck, financials, customer metrics for fundraise conversations",
         (today + timedelta(days=21)).isoformat()),
        (novabrew_id, "Update Privacy Policy for EU Launch", 3, "todo", 2.0, "", None),

        # Mobile App tasks
        (sub_ids_1["NovaBrew Mobile App"], "Implement Push Notifications", 1, "in_progress", 6.0, "", None),
        (sub_ids_1["NovaBrew Mobile App"], "Add Brew Timer Feature", 2, "todo", 4.0, "", None),
        (sub_ids_1["NovaBrew Mobile App"], "Fix iOS Crash on Profile Edit", 1, "todo", 2.0,
         "", (today + timedelta(days=3)).isoformat()),

        # Analytics tasks
        (sub_ids_1["NovaBrew Analytics"], "Build Cohort Retention Dashboard", 1, "in_progress", 8.0,
         "", (today + timedelta(days=14)).isoformat()),
        (sub_ids_1["NovaBrew Analytics"], "Implement Churn Prediction Model", 2, "todo", 10.0, "", None),

        # Partnerships tasks
        (sub_ids_1["NovaBrew Partnerships"], "Sign Archipelago Coffee Agreement", 1, "todo", 3.0,
         "", (today + timedelta(days=5)).isoformat()),
        (sub_ids_1["NovaBrew Partnerships"], "Build Partner Inventory API", 2, "in_progress", 6.0, "", None),
    ]

    for project_id, title, priority, status, est_hours, desc, due in tasks_1:
        conn.execute("""
            INSERT INTO tasks (project_id, title, priority, status,
                               estimated_hours, description, due_date, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, title, priority, status, est_hours, desc, due, "ai"))

    # NovaBrew knowledge entries
    knowledge_1 = [
        (novabrew_id, "fact",
         "NovaBrew has 200 active subscribers as of March 2026. MRR is $4,200. Average order value is $21."),
        (novabrew_id, "fact",
         "Top 3 most popular blends: Ethiopian Yirgacheffe (34%), Colombian Supremo (28%), Sumatra Mandheling (19%)."),
        (novabrew_id, "decision",
         "Decided to use Stripe Billing for subscription management over custom solution. Saves 2 weeks of dev time."),
        (sub_ids_1["NovaBrew Mobile App"], "decision",
         "Mobile app will be React Native (not Flutter) to share code with web dashboard components."),
        (novabrew_id, "insight",
         "Subscribers who receive their first order within 3 days have 2.4x higher retention at 90 days."),
        (novabrew_id, "insight",
         "Referral channel converts at 31% vs 8% for paid ads. Referral program is highest-ROI growth lever."),
        (sub_ids_1["NovaBrew Partnerships"], "context",
         "Blue Ridge Roasters is a specialty roaster in Asheville, NC. They do small-batch single-origin. Good fit for premium tier."),
        (novabrew_id, "context",
         "Series A target: $2M at $10M pre-money. Conversations started with Acme Ventures and Roast Capital."),
    ]

    for project_id, category, content in knowledge_1:
        conn.execute("""
            INSERT INTO user_knowledge (project_id, category, content, source, status)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, category, content, "demo", "approved"))

    # -------------------------------------------------------------------------
    # Demo Project 2: Orbit Marketing (P2, advisory)
    # -------------------------------------------------------------------------
    conn.execute("""
        INSERT INTO projects (name, type, status, priority, description,
                              time_allocation_hrs_week, current_focus, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "Orbit Marketing",
        "advisory",
        "active",
        2,
        "Brand strategy and digital transformation engagement for Orbit Marketing, a mid-size agency transitioning from traditional to AI-augmented services.",
        12.0,
        "Deliver competitive analysis report and finalize AI workflow recommendations",
        json.dumps(["demo", "consulting", "client", "strategy"]),
    ))
    orbit_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Orbit sub-projects
    sub_projects_2 = [
        ("Orbit Competitive Analysis", "research", "active", 1,
         "Deep-dive competitive landscape analysis — 8 competitor profiles, positioning map, gap analysis.",
         5.0, "Complete competitor profiles for Spark Digital and ClearView Agency", orbit_id),
        ("Orbit AI Integration Plan", "advisory", "active", 2,
         "Roadmap for integrating AI tools into Orbit's creative workflow — content generation, analytics, client reporting.",
         4.0, "Draft Phase 1 pilot plan for AI-assisted content creation", orbit_id),
        ("Orbit Workshop Series", "consulting", "active", 3,
         "4-session workshop series to train Orbit's team on AI tools and new workflows.",
         3.0, "Prepare materials for Workshop 1: AI Fundamentals for Creatives", orbit_id),
    ]

    sub_ids_2 = {}
    for name, ptype, status, priority, desc, time_alloc, focus, parent in sub_projects_2:
        conn.execute("""
            INSERT INTO projects (name, type, status, priority, description,
                                  time_allocation_hrs_week, current_focus, parent_id, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, ptype, status, priority, desc, time_alloc, focus, parent, json.dumps(["demo"])))
        sub_ids_2[name] = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Orbit tasks
    tasks_2 = [
        # Top-level Orbit tasks
        (orbit_id, "Deliver Competitive Analysis Report", 1, "in_progress", 10.0,
         "8 competitor profiles, SWOT analysis, positioning recommendations",
         (today + timedelta(days=7)).isoformat()),
        (orbit_id, "Finalize AI Workflow Recommendations", 1, "todo", 6.0,
         "Tool selection matrix + implementation timeline for client review",
         (today + timedelta(days=14)).isoformat()),
        (orbit_id, "Prepare Phase 2 Proposal", 2, "todo", 4.0,
         "Scope and pricing for ongoing advisory relationship", None),
        (orbit_id, "Monthly Stakeholder Update", 2, "todo", 2.0,
         "Executive summary for Orbit CEO and board",
         (today + timedelta(days=30)).isoformat()),

        # Competitive Analysis tasks
        (sub_ids_2["Orbit Competitive Analysis"], "Complete Spark Digital Profile", 1, "in_progress", 3.0,
         "", (today + timedelta(days=4)).isoformat()),
        (sub_ids_2["Orbit Competitive Analysis"], "Complete ClearView Agency Profile", 1, "todo", 3.0,
         "", (today + timedelta(days=6)).isoformat()),
        (sub_ids_2["Orbit Competitive Analysis"], "Build Positioning Map", 2, "todo", 4.0, "", None),

        # AI Integration tasks
        (sub_ids_2["Orbit AI Integration Plan"], "Draft AI Tool Selection Matrix", 1, "in_progress", 4.0, "", None),
        (sub_ids_2["Orbit AI Integration Plan"], "Design Phase 1 Pilot Plan", 2, "todo", 5.0, "", None),

        # Workshop tasks
        (sub_ids_2["Orbit Workshop Series"], "Prepare Workshop 1 Materials", 1, "todo", 6.0,
         "", (today + timedelta(days=10)).isoformat()),
        (sub_ids_2["Orbit Workshop Series"], "Book Workshop Venue and AV", 2, "todo", 1.0, "", None),
    ]

    for project_id, title, priority, status, est_hours, desc, due in tasks_2:
        conn.execute("""
            INSERT INTO tasks (project_id, title, priority, status,
                               estimated_hours, description, due_date, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, title, priority, status, est_hours, desc, due, "ai"))

    # Orbit knowledge entries
    knowledge_2 = [
        (orbit_id, "fact",
         "Orbit Marketing has 45 employees across NYC and Austin offices. Annual revenue ~$8M. Primary verticals: fintech, healthtech, real estate."),
        (orbit_id, "fact",
         "Orbit's CEO is Sarah Chen. Main stakeholder contact is VP of Strategy Marcus Webb."),
        (sub_ids_2["Orbit AI Integration Plan"], "decision",
         "Recommended ChatGPT Enterprise + Midjourney Pro as initial AI stack. Avoids vendor lock-in, team already familiar with ChatGPT."),
        (sub_ids_2["Orbit Workshop Series"], "decision",
         "Workshop series will be 4 sessions over 6 weeks (not 8 sessions) — compressed timeline per client request."),
        (sub_ids_2["Orbit Competitive Analysis"], "insight",
         "Orbit's biggest competitive gap is data analytics. Competitors Spark Digital and ClearView both offer real-time campaign dashboards."),
        (orbit_id, "insight",
         "Team survey shows 62% of Orbit staff are 'excited' about AI tools, 28% 'cautious', 10% 'resistant'. Focus on the cautious middle."),
        (orbit_id, "context",
         "Engagement is fixed-fee: $45K for Phase 1 (3 months). Phase 2 proposal targets $8K/month retainer."),
        (orbit_id, "context",
         "Spark Digital recently won Orbit's former client TrueNorth Financial. This is motivating urgency on Orbit's side."),
    ]

    for project_id, category, content in knowledge_2:
        conn.execute("""
            INSERT INTO user_knowledge (project_id, category, content, source, status)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, category, content, "demo", "approved"))

    # -------------------------------------------------------------------------
    # Cross-project insights
    # -------------------------------------------------------------------------
    insights = [
        ("dependency",
         "Both NovaBrew's Series A prep and Orbit's competitive analysis require polished data visualizations. Consider batching Figma/chart work into a single focused session.",
         "info"),
        ("alert",
         "Combined allocation: NovaBrew (25h) + Orbit (12h) = 37 hrs/week. You're near capacity. If a new engagement comes in, something needs to deprioritize.",
         "warning"),
        ("recommendation",
         "NovaBrew's referral program launch and Orbit's Workshop 1 are both due this month. Front-load the referral program — it's higher leverage and unblocks growth metrics for the Series A deck.",
         "action_required"),
        ("pattern",
         "You've been spending 60% of Orbit hours on research and only 40% on deliverables. Consider time-boxing competitive research to stay on track for the report deadline.",
         "info"),
    ]

    for itype, content, severity in insights:
        conn.execute("""
            INSERT INTO insights (type, content, severity)
            VALUES (?, ?, ?)
        """, (itype, content, severity))

    # -------------------------------------------------------------------------
    # Create demo project directories with sample files
    # -------------------------------------------------------------------------
    demo_files = {
        "novabrew": [
            ("kickoff-notes_novabrew_20260115.md", """# NovaBrew — Project Kickoff Notes
## January 15, 2026

### Vision
Build the most personalized coffee subscription in the US. AI-powered taste matching + local roastery partnerships.

### Key Metrics (Target by Q2 2026)
- 500 active subscribers (currently 200)
- $10K MRR (currently $4.2K)
- 5 roastery partners (currently 2)

### Immediate Priorities
1. Launch referral program — highest-ROI growth channel
2. Onboard Blue Ridge Roasters — first premium-tier partner
3. Ship push notifications in mobile app — 40% of users requested this
"""),
            ("weekly-update_novabrew_20260320.md", """# NovaBrew Weekly Update — March 20, 2026

## Progress
- Referral program design complete, engineering starting Monday
- Blue Ridge Roasters contract in legal review — ETA 1 week
- Mobile app push notification POC working on iOS, Android pending

## Blockers
- Stripe webhook reliability — 3 failed events last week. Investigating.
- Need design review on referral landing page before launch

## Next Week
- Start referral program engineering sprint
- Finalize Blue Ridge partnership
- Prepare cohort retention charts for investor meeting
""")
        ],
        "orbit-marketing": [
            ("engagement-brief_orbit_20260201.md", """# Orbit Marketing — Engagement Brief
## February 1, 2026

### Client
Orbit Marketing — mid-size agency, 45 employees, NYC + Austin
CEO: Sarah Chen | Primary contact: Marcus Webb (VP Strategy)

### Scope
Phase 1 (3 months, $45K fixed fee):
1. Competitive landscape analysis (8 competitor deep-dives)
2. AI integration roadmap and tool recommendations
3. 4-session workshop series for team training

### Success Criteria
- Orbit leadership has clear understanding of competitive position
- AI tool stack selected and Phase 1 pilot designed
- At least 70% of workshop attendees rate sessions ≥4/5
"""),
        ]
    }

    for project_dir, files in demo_files.items():
        dir_path = os.path.join(os.path.dirname(__file__), "projects", project_dir, "raw")
        os.makedirs(dir_path, exist_ok=True)
        for filename, content in files:
            filepath = os.path.join(dir_path, filename)
            if not os.path.exists(filepath):
                with open(filepath, 'w') as f:
                    f.write(content)
                print(f"  Created {filepath}")

    # -------------------------------------------------------------------------
    # Create default chat channel if not exists + welcome message
    # -------------------------------------------------------------------------
    conn.execute(
        "INSERT OR IGNORE INTO chat_channels (id, name, channel_type) VALUES (1, 'General', 'general')"
    )

    # Insert welcome message into chat_history
    welcome_msg = """Welcome to Iuxis! 🧠

I'm your AI Chief of Staff. I've set up two demo projects so you can explore how everything works:

• **NovaBrew** (P1) — A coffee subscription SaaS with sub-projects, tasks, and knowledge entries
• **Orbit Marketing** (P2) — A consulting engagement showing how Iuxis handles client work

**Try these to see what I can do:**
- "What should I work on today?"
- "Generate my morning briefing"
- "Show tasks for NovaBrew"
- "Create a task for Orbit Marketing: Review competitor pricing"
- Click around the dashboard — explore project cards, sub-projects, and the knowledge base

**When you're ready to start with your own projects**, just tell me: **"Ready to start"** — I'll clear the demo data and walk you through setting up your workspace."""

    conn.execute(
        "INSERT INTO chat_history (role, content) VALUES ('assistant', ?)",
        (welcome_msg,)
    )

    conn.commit()
    conn.close()

    print("✅ Demo data seeded: 2 projects, sub-projects, tasks, knowledge, insights")
    print("   Welcome message added to chat history")
    print(f"   Projects: NovaBrew (P1, {len([t for t in tasks_1 if t[0] == novabrew_id])} tasks)")
    print(f"            Orbit Marketing (P2, {len([t for t in tasks_2 if t[0] == orbit_id])} tasks)")
    print("   Open http://localhost:3000 to explore the demo")


if __name__ == "__main__":
    seed_demo()
