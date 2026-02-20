#!/usr/bin/env python3
"""
auto_commit.py

Runs inside GitHub Actions 8x/day. Each run:
  1. Checks whether the current UTC time (after an optional random delay)
     falls between 06:00 – 23:00 in a configurable timezone.
  2. Rolls a weighted random dice to decide whether to commit at all,
     so overall commit frequency feels irregular/human.
  3. Sleeps a random 0-30 minute jitter so the final commit timestamp
     doesn't land on a round schedule boundary.
  4. Touches / updates a lightweight activity log file and commits it.

Required env vars (set as GitHub Actions secrets or vars):
  GIT_USER_NAME   – your display name  (e.g. "Jane Doe")
  GIT_USER_EMAIL  – your email         (e.g. "jane@example.com")

Optional env vars:
  LOCAL_TZ        – IANA timezone string, default "America/New_York"
  COMMIT_PROB     – float 0-1, base probability of committing, default 0.72
"""

import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ── Configuration ────────────────────────────────────────────────────────────

LOCAL_TZ    = os.getenv("LOCAL_TZ", "America/New_York")
USER_NAME   = os.environ["GIT_USER_NAME"]
USER_EMAIL  = os.environ["GIT_USER_EMAIL"]

# Base probability that this particular run actually commits.
# Varies slightly per-run to avoid a perfectly uniform distribution.
BASE_PROB = float(os.getenv("COMMIT_PROB", "0.72"))

ACTIVE_HOUR_START = 6   # 06:00 local
ACTIVE_HOUR_END   = 23  # before 23:00 local  (i.e. ≤ 22:59)

MAX_JITTER_SECONDS = 30 * 60  # 30 minutes

# The file we'll touch on each commit so git actually has something to track.
ACTIVITY_FILE = ".github/activity_log.txt"

# Pool of realistic commit messages
COMMIT_MESSAGES = [
    "chore: update activity log",
    "chore: routine maintenance",
    "docs: minor update",
    "fix: small correction",
    "refactor: tidy up",
    "chore: housekeeping",
    "style: formatting",
    "chore: bump log",
    "docs: update notes",
    "chore: periodic update",
    "fix: typo",
    "chore: sync",
    "docs: clarify comment",
    "chore: cleanup",
    "refactor: small improvement",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def local_now() -> datetime:
    return datetime.now(tz=ZoneInfo(LOCAL_TZ))


def should_commit(local_dt: datetime) -> bool:
    """Decide whether to commit based on time-of-day weighted probability."""
    hour = local_dt.hour

    # Outside active window → never commit
    if not (ACTIVE_HOUR_START <= hour < ACTIVE_HOUR_END):
        print(f"[auto_commit] Outside active hours ({hour}:xx local). Skipping.")
        return False

    # Add a tiny per-run random nudge (±0.10) so frequency isn't perfectly uniform
    prob = BASE_PROB + random.uniform(-0.10, 0.10)
    prob = max(0.0, min(1.0, prob))

    roll = random.random()
    decision = roll < prob
    print(f"[auto_commit] Commit probability: {prob:.2f}, roll: {roll:.2f} → {'YES' % () if decision else 'NO'}")
    return decision


def jitter_sleep():
    """Sleep a random amount up to MAX_JITTER_SECONDS."""
    delay = random.randint(0, MAX_JITTER_SECONDS)
    minutes, seconds = divmod(delay, 60)
    print(f"[auto_commit] Sleeping {minutes}m {seconds}s before acting…")
    time.sleep(delay)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"[auto_commit] $ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)
    if result.stdout.strip():
        print(result.stdout.strip())
    return result


def make_commit():
    """Update the activity file and push a commit."""
    # Configure git identity for this run
    run(["git", "config", "user.name",  USER_NAME])
    run(["git", "config", "user.email", USER_EMAIL])

    # Ensure the directory exists
    os.makedirs(os.path.dirname(ACTIVITY_FILE), exist_ok=True)

    # Append a timestamped line
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_local = local_now().strftime("%Y-%m-%d %H:%M %Z")
    entry = f"{now_utc}  ({now_local})\n"

    with open(ACTIVITY_FILE, "a") as fh:
        fh.write(entry)

    run(["git", "add", ACTIVITY_FILE])

    # Check if there's actually something staged (idempotency guard)
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True
    )
    if diff.returncode == 0:
        print("[auto_commit] Nothing to commit (already up to date).")
        return

    message = random.choice(COMMIT_MESSAGES)
    run(["git", "commit", "-m", message])
    run(["git", "push"])
    print(f'[auto_commit] Committed & pushed: "{message}"')


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Seed with something slightly unpredictable
    random.seed(int(time.time() * 1000) % (2**32))

    now = local_now()
    print(f"[auto_commit] Local time: {now.strftime('%Y-%m-%d %H:%M %Z')}")

    if not should_commit(now):
        sys.exit(0)

    # Jitter BEFORE we commit so the actual commit timestamp is offset
    jitter_sleep()

    # Re-check the hour after jitter (could have crossed midnight or end boundary)
    now_after = local_now()
    if not (ACTIVE_HOUR_START <= now_after.hour < ACTIVE_HOUR_END):
        print(f"[auto_commit] Jitter pushed us outside active hours. Skipping.")
        sys.exit(0)

    make_commit()


if __name__ == "__main__":
    main()
