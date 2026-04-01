"""
APScheduler integration for Iuxis.
Manages automated jobs: briefing, insights, schedule generation, priority reranking.
"""
from __future__ import annotations

from datetime import datetime, date
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

from iuxis.db import load_config, fetch_one, get_connection

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' string to (hour, minute) tuple."""
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


class IuxisScheduler:
    def __init__(self):
        self.conn = get_connection()
        self.scheduler = get_scheduler()
        self._setup_jobs()

    def _setup_jobs(self):
        """Configure all scheduled jobs."""

        # Morning briefing — 5:55 AM daily (ready before 6 AM work start)
        self.scheduler.add_job(
            self._run_morning_briefing,
            CronTrigger(hour=5, minute=55),
            id='morning_briefing',
            replace_existing=True,
            misfire_grace_time=3600  # 1 hour grace
        )

        # Generate daily schedule — 5:57 AM daily
        self.scheduler.add_job(
            self._run_schedule_generation,
            CronTrigger(hour=5, minute=57),
            id='daily_schedule',
            replace_existing=True,
            misfire_grace_time=3600
        )

        # Cross-project insights — every 6 hours
        self.scheduler.add_job(
            self._run_insight_generation,
            CronTrigger(hour='0,6,12,18', minute=0),
            id='insight_generation',
            replace_existing=True,
            misfire_grace_time=3600
        )

        # Priority re-ranking — every 2 hours during work hours
        self.scheduler.add_job(
            self._run_priority_rerank,
            CronTrigger(hour='6-16/2', minute=30),
            id='priority_rerank',
            replace_existing=True,
            misfire_grace_time=1800
        )

        # Memory consolidation — nightly at 2:00 AM
        self.scheduler.add_job(
            self._run_memory_consolidation,
            CronTrigger(hour=2, minute=0),
            id='nightly_consolidation',
            name='Nightly Memory Consolidation',
            replace_existing=True,
            misfire_grace_time=3600  # Allow up to 1hr late if server was down
        )

        # GitHub scanner — daily at 6:00 AM
        self.scheduler.add_job(
            self._run_github_scan,
            CronTrigger(hour=6, minute=0),
            id='github_scan',
            name='Daily GitHub Scan',
            replace_existing=True,
            misfire_grace_time=3600
        )

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Iuxis scheduler started")
            print(f"✓ Scheduler started with {len(self.scheduler.get_jobs())} jobs")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Iuxis scheduler stopped")

    def _run_morning_briefing(self):
        """Generate morning briefing."""
        try:
            from iuxis.briefing_engine import BriefingEngine
            engine = BriefingEngine()
            result = engine.generate_morning_briefing()
            logger.info(f"Morning briefing generated at {result['generated_at']}")
            print(f"[{datetime.now()}] Morning briefing generated")
        except Exception as e:
            logger.error(f"Morning briefing failed: {e}")
            print(f"[{datetime.now()}] Morning briefing failed: {e}")

    def _run_schedule_generation(self):
        """Generate daily schedule."""
        try:
            from iuxis.schedule_generator import ScheduleGenerator
            gen = ScheduleGenerator()
            blocks = gen.generate_daily_schedule()
            logger.info(f"Daily schedule generated: {len(blocks)} blocks")
            print(f"[{datetime.now()}] Daily schedule generated: {len(blocks)} blocks")
        except Exception as e:
            logger.error(f"Schedule generation failed: {e}")
            print(f"[{datetime.now()}] Schedule generation failed: {e}")

    def _run_insight_generation(self):
        """Run cross-project insight analysis."""
        try:
            from iuxis.insight_engine import InsightEngine
            engine = InsightEngine()
            insights = engine.generate_insights()
            logger.info(f"Generated {len(insights)} new insights")
            print(f"[{datetime.now()}] Generated {len(insights)} new insights")
        except Exception as e:
            logger.error(f"Insight generation failed: {e}")
            print(f"[{datetime.now()}] Insight generation failed: {e}")

    def _run_priority_rerank(self):
        """Re-rank task priorities."""
        try:
            from iuxis.priority_engine import PriorityEngine
            engine = PriorityEngine()
            ranked = engine.rank_tasks_for_today()
            logger.info(f"Re-ranked {len(ranked)} tasks")
            print(f"[{datetime.now()}] Re-ranked {len(ranked)} tasks")
        except Exception as e:
            logger.error(f"Priority re-rank failed: {e}")
            print(f"[{datetime.now()}] Priority re-rank failed: {e}")

    def _run_memory_consolidation(self):
        """Run premium memory consolidation (nightly at 2 AM)."""
        try:
            from iuxis.premium.consolidation import run_consolidation_pass
            result = run_consolidation_pass(trigger="scheduled")
            total = result.get('total_entries_consolidated', 0)
            status = result.get('status')
            logger.info(f"Memory consolidation: {status} — {total} entries consolidated")
            print(f"[{datetime.now()}] Memory consolidation: {status} — {total} entries")
        except Exception as e:
            logger.error(f"Memory consolidation failed: {e}")
            print(f"[{datetime.now()}] Memory consolidation failed: {e}")

    def _run_github_scan(self):
        """Scan all projects with GitHub repos configured (daily at 6 AM)."""
        try:
            from iuxis import github_scanner
            # Get all projects with github_repo set
            rows = self.conn.execute("""
                SELECT id, name, github_repo
                FROM projects
                WHERE github_repo IS NOT NULL
            """).fetchall()

            if not rows:
                logger.info("No projects with GitHub repos configured")
                return

            total_commits = 0
            total_issues = 0
            total_branches = 0

            for project_id, project_name, repo in rows:
                try:
                    result = github_scanner.scan_repository(
                        project_id=project_id,
                        repo=repo,
                        backfill_days=1,  # Incremental scan
                    )
                    total_commits += result['commits']
                    total_issues += result['issues']
                    total_branches += result['branches']
                    logger.info(f"Scanned {repo} for {project_name}")
                except Exception as e:
                    logger.error(f"Failed to scan {repo}: {e}")

            logger.info(
                f"GitHub scan complete: {total_commits} commits, "
                f"{total_issues} issues, {total_branches} branches"
            )
            print(
                f"[{datetime.now()}] GitHub scan: "
                f"{total_commits} commits, {total_issues} issues, {total_branches} branches"
            )
        except Exception as e:
            logger.error(f"GitHub scan failed: {e}")
            print(f"[{datetime.now()}] GitHub scan failed: {e}")

    # Manual triggers (called from chat)
    def trigger_briefing(self):
        self._run_morning_briefing()

    def trigger_schedule(self):
        self._run_schedule_generation()

    def trigger_insights(self):
        self._run_insight_generation()

    def trigger_consolidation(self):
        self._run_memory_consolidation()


# ============================================================================
# Legacy setup function for backward compatibility
# ============================================================================

def setup_scheduled_jobs() -> BackgroundScheduler:
    """Configure and start the scheduler with all automated jobs."""
    cfg = load_config()
    scheduler = get_scheduler()
    tz = cfg["user"].get("timezone", "America/New_York")

    # Morning briefing
    h, m = _parse_time(cfg["scheduler"]["morning_briefing"])
    scheduler.add_job(
        _job_morning_briefing,
        CronTrigger(hour=h, minute=m, timezone=tz),
        id="morning_briefing",
        replace_existing=True,
    )

    # Evening review
    h, m = _parse_time(cfg["scheduler"]["evening_review"])
    scheduler.add_job(
        _job_evening_review,
        CronTrigger(hour=h, minute=m, timezone=tz),
        id="evening_review",
        replace_existing=True,
    )

    # Overnight batch analysis
    h, m = _parse_time(cfg["scheduler"]["overnight_batch"])
    scheduler.add_job(
        _job_overnight_analysis,
        CronTrigger(hour=h, minute=m, timezone=tz),
        id="overnight_batch",
        replace_existing=True,
    )

    # Vault reindex
    h, m = _parse_time(cfg["scheduler"]["vault_reindex"])
    scheduler.add_job(
        _job_vault_reindex,
        CronTrigger(hour=h, minute=m, timezone=tz),
        id="vault_reindex",
        replace_existing=True,
    )

    scheduler.start()
    print(f"✓ Scheduler started with {len(scheduler.get_jobs())} jobs")
    return scheduler


# ---------------------------------------------------------------------------
# Legacy Job Functions
# ---------------------------------------------------------------------------

def _job_morning_briefing():
    """Generate the morning briefing."""
    try:
        from iuxis.insight_engine import generate_morning_briefing
        result = generate_morning_briefing()
        print(f"[{datetime.now()}] Morning briefing generated ({len(result)} chars)")
    except Exception as e:
        print(f"[{datetime.now()}] Morning briefing failed: {e}")


def _job_evening_review():
    """Run evening review analysis."""
    try:
        from iuxis.insight_engine import run_pattern_analysis
        result = run_pattern_analysis()
        print(f"[{datetime.now()}] Evening review generated ({len(result)} chars)")
    except Exception as e:
        print(f"[{datetime.now()}] Evening review failed: {e}")


def _job_overnight_analysis():
    """Deep pattern analysis using Opus model."""
    try:
        from iuxis.insight_engine import run_pattern_analysis
        result = run_pattern_analysis()
        print(f"[{datetime.now()}] Overnight analysis complete ({len(result)} chars)")
    except Exception as e:
        print(f"[{datetime.now()}] Overnight analysis failed: {e}")


def _job_vault_reindex():
    """Reindex the Obsidian vault."""
    try:
        from iuxis.obsidian import index_vault
        count = index_vault(verbose=True)
        print(f"[{datetime.now()}] Vault reindexed: {count} files")
    except Exception as e:
        print(f"[{datetime.now()}] Vault reindex failed: {e}")


def run_briefing_if_missed() -> str | None:
    """Check if today's briefing exists; if not, generate it now.
    Called on app startup to handle the laptop-was-sleeping case."""
    today = date.today().isoformat()
    existing = fetch_one(
        """SELECT id FROM insights
           WHERE type = 'recommendation'
             AND content LIKE '%MORNING BRIEFING%'
             AND DATE(created_at) = ?""",
        (today,),
    )

    if existing:
        return None  # Already generated today

    try:
        from iuxis.insight_engine import generate_morning_briefing
        result = generate_morning_briefing()
        print(f"✓ Missed morning briefing generated on startup")
        return result
    except Exception as e:
        print(f"⚠️ Could not generate startup briefing: {e}")
        return None
