"""Date extraction from filenames — flexible format support.

Handles varied date formats in filenames so the ingestion engine can
sort files chronologically and prioritize recent content.

Supported formats (examples):
    2026-02-24-board-notes.md           → 2026-02-24
    2026_02_24_board_notes.md           → 2026-02-24
    20260224-meeting.md                 → 2026-02-24
    feb-24-2026-notes.md                → 2026-02-24
    24-feb-2026-update.md               → 2026-02-24
    Feb24-notes.md                      → 2026-02-24 (assumes current year)
    2026-02-24T13-31-37-screenshot.png  → 2026-02-24 13:31:37
    Screenshot_2026-02-24_at_13_31_37   → 2026-02-24 13:31:37
    meeting-notes-02-24-2026.md         → 2026-02-24
    Q1-2026-strategy.md                 → 2026-03-31 (end of Q1)
    notes-2026.02.24.md                 → 2026-02-24
"""

import re
from datetime import datetime, date
from typing import Optional


# ---------------------------------------------------------------------------
# Month name lookups
# ---------------------------------------------------------------------------

MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Quarter end dates
QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def extract_date_from_filename(filename: str) -> Optional[datetime]:
    """Extract the most likely date/timestamp from a filename.
    
    Tries multiple patterns in priority order. Returns datetime on success,
    None if no date found.
    
    Args:
        filename: Just the filename (not full path), with or without extension
        
    Returns:
        datetime object or None
    """
    # Strip extension and work with lowercase
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    name_lower = name.lower()

    # Normalize separators: replace underscores and dots with hyphens for matching
    # But keep original for specific patterns
    normalized = name.replace("_", "-").replace(".", "-")
    normalized_lower = normalized.lower()

    # --- Pattern 1: ISO-style with optional timestamp ---
    # 2026-02-24T13-31-37, 2026-02-24-13-31-37, Screenshot-2026-02-24-at-13-31-37
    m = re.search(
        r'(\d{4})-(\d{2})-(\d{2})(?:[T\-](?:at-)?(\d{2})-(\d{2})(?:-(\d{2}))?)?',
        normalized
    )
    if m:
        try:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hour = int(m.group(4)) if m.group(4) else 0
            minute = int(m.group(5)) if m.group(5) else 0
            second = int(m.group(6)) if m.group(6) else 0
            if _valid_date(year, month, day) and _valid_time(hour, minute, second):
                return datetime(year, month, day, hour, minute, second)
        except (ValueError, TypeError):
            pass

    # --- Pattern 2: Compact date YYYYMMDD ---
    # 20260224-meeting.md
    m = re.search(r'(\d{4})(\d{2})(\d{2})', normalized)
    if m:
        try:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if _valid_date(year, month, day):
                return datetime(year, month, day)
        except ValueError:
            pass

    # --- Pattern 3: Month name + day + year ---
    # feb-24-2026, february-24-2026, Feb24-2026
    m = re.search(
        r'([a-z]{3,9})-?(\d{1,2})-?(\d{4})',
        normalized_lower
    )
    if m:
        month_str, day_str, year_str = m.group(1), m.group(2), m.group(3)
        month = MONTH_NAMES.get(month_str)
        if month:
            try:
                year, day = int(year_str), int(day_str)
                if _valid_date(year, month, day):
                    return datetime(year, month, day)
            except ValueError:
                pass

    # --- Pattern 4: Day + month name + year ---
    # 24-feb-2026, 24-february-2026
    m = re.search(
        r'(\d{1,2})-([a-z]{3,9})-(\d{4})',
        normalized_lower
    )
    if m:
        day_str, month_str, year_str = m.group(1), m.group(2), m.group(3)
        month = MONTH_NAMES.get(month_str)
        if month:
            try:
                year, day = int(year_str), int(day_str)
                if _valid_date(year, month, day):
                    return datetime(year, month, day)
            except ValueError:
                pass

    # --- Pattern 5: Month name + day (no year — assume current year) ---
    # Feb24-notes, mar-15-update
    m = re.search(
        r'([a-z]{3,9})-?(\d{1,2})(?!\d)',
        normalized_lower
    )
    if m:
        month_str, day_str = m.group(1), m.group(2)
        month = MONTH_NAMES.get(month_str)
        if month:
            try:
                day = int(day_str)
                year = date.today().year
                if _valid_date(year, month, day):
                    return datetime(year, month, day)
            except ValueError:
                pass

    # --- Pattern 6: US-style MM-DD-YYYY ---
    # 02-24-2026
    m = re.search(r'(\d{2})-(\d{2})-(\d{4})', normalized)
    if m:
        try:
            a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # Disambiguate: if first number > 12, it's DD-MM-YYYY
            if a <= 12 and _valid_date(year, a, b):
                return datetime(year, a, b)  # MM-DD-YYYY
            elif b <= 12 and _valid_date(year, b, a):
                return datetime(year, b, a)  # DD-MM-YYYY
        except ValueError:
            pass

    # --- Pattern 7: Quarter reference ---
    # Q1-2026, q3-2026
    m = re.search(r'q(\d)-(\d{4})', normalized_lower)
    if m:
        try:
            quarter, year = int(m.group(1)), int(m.group(2))
            if 1 <= quarter <= 4:
                month, day = QUARTER_END[quarter]
                return datetime(year, month, day)
        except (ValueError, KeyError):
            pass

    # --- Pattern 8: Year-month only ---
    # 2026-02-strategy.md (no day)
    m = re.search(r'(\d{4})-(\d{2})(?!\d)', normalized)
    if m:
        try:
            year, month = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12 and 2020 <= year <= 2030:
                return datetime(year, month, 1)
        except ValueError:
            pass

    return None


# ---------------------------------------------------------------------------
# Sorting helper
# ---------------------------------------------------------------------------

def sort_files_chronologically(filepaths: list[str]) -> list[str]:
    """Sort file paths by extracted date, oldest first.
    
    Files without dates are placed at the beginning (treated as undated/oldest).
    
    Returns:
        Sorted list of file paths.
    """
    import os

    def sort_key(filepath):
        filename = os.path.basename(filepath)
        dt = extract_date_from_filename(filename)
        if dt:
            return (1, dt)  # Dated files: sort by date
        else:
            return (0, datetime.min)  # Undated files: go first

    return sorted(filepaths, key=sort_key)


def get_file_date_label(filepath: str) -> str:
    """Get a human-readable date label for a file, or 'undated'."""
    import os
    dt = extract_date_from_filename(os.path.basename(filepath))
    if dt:
        if dt.hour or dt.minute:
            return dt.strftime("%Y-%m-%d %H:%M")
        return dt.strftime("%Y-%m-%d")
    return "undated"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _valid_date(year: int, month: int, day: int) -> bool:
    """Check if year/month/day form a valid date in a reasonable range."""
    if year < 2020 or year > 2030:
        return False
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


def _valid_time(hour: int, minute: int, second: int) -> bool:
    """Check if hour/minute/second are valid."""
    return 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_cases = [
        ("2026-02-24-board-notes.md", "2026-02-24"),
        ("2026_02_24_board_notes.md", "2026-02-24"),
        ("20260224-meeting.md", "2026-02-24"),
        ("feb-24-2026-notes.md", "2026-02-24"),
        ("24-feb-2026-update.md", "2026-02-24"),
        ("Feb24-notes.md", f"{date.today().year}-02-24"),
        ("2026-02-24T13-31-37-screenshot.png", "2026-02-24 13:31:37"),
        ("Screenshot_2026-02-24_at_13_31_37.png", "2026-02-24 13:31:37"),
        ("meeting-notes-02-24-2026.md", "2026-02-24"),
        ("Q1-2026-strategy.md", "2026-03-31"),
        ("notes-2026.02.24.md", "2026-02-24"),
        ("random-notes.md", "None"),
        ("2026-02-strategy.md", "2026-02-01"),
    ]

    print("🧪 Date extraction tests:\n")
    passed = 0
    for filename, expected in test_cases:
        result = extract_date_from_filename(filename)
        result_str = result.strftime("%Y-%m-%d %H:%M:%S").replace(" 00:00:00", "") if result else "None"
        # Normalize expected for comparison
        expected_norm = expected.replace(" 00:00:00", "")
        status = "✅" if result_str == expected_norm else "❌"
        if status == "✅":
            passed += 1
        print(f"  {status} {filename:50s} → {result_str:20s} (expected: {expected_norm})")

    print(f"\n  {passed}/{len(test_cases)} passed")
