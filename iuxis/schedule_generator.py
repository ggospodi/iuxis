"""
Schedule Generator for Iuxis.
Creates daily time blocks based on task priorities and project allocations.
Work window: 6:00 AM – 4:00 PM (configurable).
"""
from datetime import date, datetime, timedelta
from iuxis.priority_engine import PriorityEngine
from iuxis.db import get_connection, fetch_all, execute


class ScheduleGenerator:
    def __init__(self):
        self.conn = get_connection()
        self.work_start = 6   # 6 AM
        self.work_end = 16    # 4 PM
        self.block_duration = 120  # 2-hour blocks (minutes)
        self.break_duration = 15   # minutes between blocks

    def generate_daily_schedule(self) -> list[dict]:
        """
        Generate today's schedule as time blocks.
        Returns list of schedule blocks ready for DB insertion.
        """
        today = date.today()

        # Get ranked tasks
        engine = PriorityEngine()
        ranked_tasks = engine.rank_tasks_for_today()

        # Get project time allocations (weekly → daily)
        allocations = self._get_daily_allocations()

        # Build time blocks
        blocks = []
        current_time = datetime.combine(today, datetime.min.time().replace(hour=self.work_start))
        end_time = datetime.combine(today, datetime.min.time().replace(hour=self.work_end))

        task_index = 0
        projects_scheduled = {}  # project_name → hours_scheduled_today

        while current_time + timedelta(minutes=self.block_duration) <= end_time and task_index < len(ranked_tasks):
            task = ranked_tasks[task_index]
            project = task.get('project', 'General')

            # Check if project has remaining daily allocation
            daily_alloc = allocations.get(project, 2.0)  # default 2h/day
            scheduled = projects_scheduled.get(project, 0)

            if scheduled >= daily_alloc:
                # Skip this task, try next one
                task_index += 1
                continue

            # Create block
            block_end = current_time + timedelta(minutes=self.block_duration)
            est_hours = task.get('estimated_hours') or (self.block_duration / 60)

            block = {
                'project_name': project,
                'task_title': task['title'],
                'task_id': task['id'],
                'start_time': current_time.strftime('%H:%M'),
                'end_time': block_end.strftime('%H:%M'),
                'block_type': 'deep_work',
                'status': 'planned',
                'date': today.isoformat()
            }
            blocks.append(block)

            # Track allocation
            projects_scheduled[project] = scheduled + (self.block_duration / 60)
            current_time = block_end + timedelta(minutes=self.break_duration)
            task_index += 1

        # Save to DB
        self._save_schedule(blocks, today)

        return blocks

    def _get_daily_allocations(self) -> dict:
        """Convert weekly project allocations to daily (÷5 work days)."""
        rows = fetch_all(
            """SELECT name, time_allocation_hrs_week
            FROM projects
            WHERE parent_id IS NULL AND status = 'active'"""
        )

        return {
            row.get("name"): (row.get("time_allocation_hrs_week", 0) / 5.0)
            for row in rows
            if row.get("time_allocation_hrs_week")
        }

    def _save_schedule(self, blocks: list[dict], today: date):
        """Save generated schedule blocks to DB."""
        # Clear today's planned (non-completed) blocks first
        execute(
            """DELETE FROM schedule_blocks
            WHERE date = ? AND status = 'planned'""",
            (today.isoformat(),)
        )

        for block in blocks:
            # Find project ID
            proj_rows = fetch_all(
                "SELECT id FROM projects WHERE name = ? LIMIT 1",
                (block['project_name'],)
            )
            project_id = proj_rows[0].get("id") if proj_rows else None

            execute(
                """INSERT INTO schedule_blocks
                (project_id, task_id, start_time, end_time, block_type, status, date)
                VALUES (?, ?, ?, ?, ?, 'planned', ?)""",
                (
                    project_id,
                    block.get('task_id'),
                    block['start_time'],
                    block['end_time'],
                    block['block_type'],
                    block['date']
                )
            )

    def format_schedule(self, blocks: list[dict]) -> str:
        """Format schedule for display."""
        if not blocks:
            return "No schedule generated yet. Try: 'generate schedule'"

        lines = [f"**📅 Schedule for {blocks[0]['date']}**\n"]
        for b in blocks:
            lines.append(
                f"**{b['start_time']}–{b['end_time']}** | "
                f"{b['project_name']} — {b['task_title']}"
            )
        return "\n".join(lines)
