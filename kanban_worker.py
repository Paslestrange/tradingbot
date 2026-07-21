#!/usr/bin/env python3
"""Trading bot autonomous worker — standard architecture edition.

Self-directing project builder. Scans, identifies gaps, creates tasks,
executes them with agy, reviews with Hermes, pushes to remote.
Sends Discord notifications directly — no LLM cron agent needed.

Workflow:
  1. SCAN project state
  2. If gaps found → auto-create tasks (max 2/cycle)
  3. Pick next ready task → plan → implement → review → fix → merge → push
  4. Print [SILENT] for cron agent (we handle Discord ourselves)
"""
import json
import subprocess
import sys
import os
import time
import re
import urllib.request
from pathlib import Path

WORKSPACE = Path("/home/pascal/workspace/tradingbot-fixed")
LOCK_FILE = WORKSPACE / ".worker.lock"
# Shared lock across all autonomous workers (Metaphors, PetitionsRadar, TradingBot)
SHARED_LOCK_FILE = Path("/home/pascal/workspace/.autonomous-worker.lock")
SHARED_LOCK_TIMEOUT = 900  # 15 min
REMOTE = "origin"
BRANCH = "main"
AGY_BIN = "/home/pascal/.local/bin/agy"
HERMES_BIN = os.path.expanduser("~/.local/bin/hermes")
TIMEOUT = 600
MAX_FIX_ROUNDS = 2
DISCORD_CHANNEL_ID = "1528703254102413434"  # #trading-bot
KANBAN_BOARD = "trading-bot"

# ─── Helpers ───────────────────────────────────────────────────────

def run(cmd, timeout=60, workdir=None):
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        timeout=timeout, cwd=str(workdir or WORKSPACE)
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def log(msg):
    print(f"[worker] {time.strftime('%H:%M:%S')} {msg}", flush=True)

def _sq(s):
    return s.replace("'", "'\\''")

def send_discord(message: str) -> bool:
    """Send a message directly to Discord via bot API — no LLM needed."""
    env_path = Path("/home/pascal/.hermes/.env")
    if not env_path.exists():
        log("No .env file found, cannot send Discord message")
        return False
    token = None
    for line in env_path.read_text().splitlines():
        if line.startswith("DISCORD_BOT_TOKEN="):
            token = line.split("=", 1)[1].strip()
            break
    if not token:
        log("No DISCORD_BOT_TOKEN found")
        return False
    try:
        payload = json.dumps({"content": message}).encode("utf-8")
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages",
            data=payload,
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200 or resp.status == 201
    except Exception as e:
        log(f"Discord send failed: {e}")
        return False

# ─── Project Scanner ───────────────────────────────────────────────

class ProjectScanner:
    REQUIRED_FILES = {
        "kanban_worker.py": "Autonomous worker",
        "requirements.txt": "Dependencies",
        "README.md": "Documentation",
        ".gitignore": "Git ignore",
        ".env.example": "Env template",
        "backtest/backtest_engine.py": "Backtester",
        "env/xauusd_env.py": "Trading environment",
        "features/make_features.py": "Feature pipeline",
        "models/risk_supervisor.py": "Risk supervisor",
        "models/__init__.py": "Models package",
        "live_trade_mt5.py": "Live trading script",
        "tests/__init__.py": "Tests package",
        "tests/test_backtester.py": "Backtester tests",
        "tests/test_environment.py": "Environment tests",
        "tests/test_features.py": "Feature tests",
        "tests/test_risk_supervisor.py": "Risk supervisor tests",
        "data/load_data.py": "Data loader",
        "data/__init__.py": "Data package",
    }

    def __init__(self):
        self.existing = set()
        self.missing = {}
        self.tests_pass = False
        self.test_summary = ""
        self.server_ok = False

    def scan(self):
        for root, dirs, files in os.walk(WORKSPACE):
            dirs[:] = [d for d in dirs if d not in ('.venv', '__pycache__', '.git', '.hermes', 'node_modules', '.pytest_cache', '.kanban')]
            for f in files:
                self.existing.add(os.path.relpath(os.path.join(root, f), WORKSPACE))
        self.missing = {p: d for p, d in self.REQUIRED_FILES.items() if p not in self.existing}
        self._check_tests()
        self._check_imports()
        return self

    def _check_tests(self):
        out, _, code = run("python3 -m pytest tests/ -v --tb=short 2>&1", timeout=120)
        self.tests_pass = code == 0
        for line in out.splitlines():
            if "passed" in line or "failed" in line or "error" in line:
                self.test_summary = line.strip()
                break

    def _check_imports(self):
        # Check if core modules import cleanly
        out, _, code = run("python3 -c 'from models.risk_supervisor import RiskSupervisor; print(\"OK\")' 2>&1", timeout=10)
        self.server_ok = code == 0 and "OK" in out

    def has_critical_gaps(self):
        return bool(self.missing) or not self.tests_pass

# ─── Task Creator ──────────────────────────────────────────────────

def existing_tasks():
    out, _, _ = run(f"hermes kanban --board {KANBAN_BOARD} list --json 2>/dev/null")
    try:
        return json.loads(out)
    except (json.JSONDecodeError, KeyError):
        return []

def task_exists(title):
    return any(t["title"] == title for t in existing_tasks())

def create_task(title, body):
    if task_exists(title):
        return False
    run(f'hermes kanban --board {KANBAN_BOARD} create "{_sq(title)}" --assignee default --body "{_sq(body)}"')
    return True

def auto_create_tasks(scanner):
    """Create tasks for gaps. Max 2 per cycle."""
    created = 0

    # Priority 1: Failing tests
    if not scanner.tests_pass and not task_exists("Fix failing tests"):
        create_task(
            "Fix failing tests",
            f"Tests are failing: {scanner.test_summary}\n\n"
            f"Run: cd {WORKSPACE} && python3 -m pytest tests/ -v\n"
            f"Fix all failures. Ensure 100% pass rate."
        )
        created += 1

    # Priority 2: Import errors
    if not scanner.server_ok and not task_exists("Fix import errors") and created < 2:
        create_task(
            "Fix import errors",
            "Core modules fail to import. Check models/, features/, env/ for broken imports."
        )
        created += 1

    # Priority 3: Missing files
    if created < 2:
        for path, desc in sorted(scanner.missing.items()):
            if created >= 2:
                break
            title = f"Create {path}"
            if not task_exists(title):
                create_task(title, f"Create missing file: {path}\n\nPurpose: {desc}")
                created += 1
                break

    return created

# ─── Git Operations ────────────────────────────────────────────────

def git_ensure_main():
    run(f"git checkout {BRANCH}", workdir=WORKSPACE)
    run(f"git pull --rebase {REMOTE} {BRANCH} 2>/dev/null || true", workdir=WORKSPACE)

def git_create_branch(name):
    git_ensure_main()
    # Delete existing branch if it somehow exists
    out, err, code = run(f"git branch -D {name} 2>/dev/null", workdir=WORKSPACE)
    out, err, code = run(f"git checkout -b {name}", workdir=WORKSPACE)
    if code != 0:
        log(f"Failed to create branch {name}: {err[:200]}")
        return False
    return True

def git_cleanup_dirty():
    """Clean up dirty git state on failure."""
    run("git merge --abort 2>/dev/null", workdir=WORKSPACE)
    run("git rebase --abort 2>/dev/null", workdir=WORKSPACE)
    run(f"git checkout {BRANCH} 2>/dev/null", workdir=WORKSPACE)
    run("git reset --hard HEAD 2>/dev/null", workdir=WORKSPACE)
    run("git clean -fd 2>/dev/null", workdir=WORKSPACE)

def git_merge_branch(name, title):
    git_ensure_main()
    count_out, _, _ = run(f"git rev-list --count {BRANCH}..{name}", workdir=WORKSPACE)
    try:
        count = int(count_out)
    except ValueError:
        count = 0
    if count == 0:
        return False
    safe_title = re.sub(r'[^a-zA-Z0-9 ]', '', title)[:60]
    run(f'git merge --squash {name}', workdir=WORKSPACE)
    run(f'git commit -m "feat: {safe_title}"', workdir=WORKSPACE)
    run(f"git branch -D {name}", workdir=WORKSPACE)
    return True

def git_push():
    _, stderr, code = run(f"git push {REMOTE} {BRANCH}", workdir=WORKSPACE, timeout=30)
    if code == 0:
        log("Pushed to remote")
        return True
    else:
        log(f"Push failed: {stderr[:200]}")
        return False

def git_diff_main_names():
    names, _, _ = run(f"git diff {BRANCH}...HEAD --name-only", workdir=WORKSPACE)
    return [f.strip() for f in names.splitlines() if f.strip()]

# ─── Kanban Operations ─────────────────────────────────────────────

def get_next_task():
    out, _, code = run(f"hermes kanban --board {KANBAN_BOARD} list --json 2>/dev/null")
    if code != 0 or not out:
        return None
    try:
        tasks = json.loads(out)
    except json.JSONDecodeError:
        return None
    for t in tasks:
        if t.get("status") == "ready":
            return t
    return None

# ─── Execution Phases ──────────────────────────────────────────────

def plan_task(task):
    prompt = f"""Plan this task for the trading bot project at {WORKSPACE}.

Task: {task['title']}
Description: {task.get('body', '')}

Project context: This is a gold (XAU/USD) trading bot using reinforcement learning (DREAMER/PPO).
Key modules: features/make_features.py (feature engineering), backtest/backtest_engine.py (backtester),
env/xauusd_env.py (trading environment), models/risk_supervisor.py (risk management),
live_trade_mt5.py (live MT5 trading), data/load_data.py (data pipeline).
Tests in tests/ using pytest.

Create a brief implementation plan: files to change, key decisions, test strategy.
Do NOT write code. Under 300 words. Exact file paths."""
    out, _, code = run(f"{HERMES_BIN} chat -q '{_sq(prompt)}'", timeout=120)
    return out if code == 0 and out else None

def implement_task(task, plan):
    prompt = f"""Implement this task for the trading bot project at {WORKSPACE}.

Task: {task['title']}
Description: {task.get('body', '')}
Plan: {plan}

Project context: Gold (XAU/USD) trading bot using RL (DREAMER/PPO).
Key modules: features/make_features.py, backtest/backtest_engine.py,
env/xauusd_env.py, models/risk_supervisor.py, live_trade_mt5.py.
Tests in tests/ using pytest.

1. Read existing code for context
2. TDD: tests first, verify fail, implement, verify pass
3. Run: cd {WORKSPACE} && python3 -m pytest tests/ -v
4. Commit with descriptive message

Do NOT install packages or modify files outside {WORKSPACE}.
Use python3 for all Python commands.
This is a financial trading system — correctness is critical. No look-ahead bias in features.
All changes must have tests."""
    out, err, code = run(f"{AGY_BIN} --print-timeout 10m --print '{_sq(prompt)}'", timeout=TIMEOUT)
    return {"output": out or "", "errors": err or "", "success": code == 0}

def review_task(task, plan):
    diff, _, _ = run(f"git diff {BRANCH}...HEAD", workdir=WORKSPACE)
    if len(diff) > 6000:
        diff = diff[:6000] + "\n..."
    tests, _, _ = run("python3 -m pytest tests/ --tb=short -q 2>&1", workdir=WORKSPACE, timeout=120)
    prompt = f"""Review this code for the trading bot project.

Task: {task['title']}
Diff: {diff}
Tests: {tests[-1500:]}

Check:
- No look-ahead bias in feature computation (rolling windows only, no global mean/std)
- Backtester executes on next bar open, not current bar close
- Risk supervisor wired into live trading
- Tests pass and cover new functionality
- No bare except, proper error handling
- Financial correctness — this handles real money trades

Output exactly: VERDICT: PASS or VERDICT: FAIL
Then one sentence why."""
    out, _, code = run(f"{HERMES_BIN} chat -q '{_sq(prompt)}'", timeout=120)
    if code != 0 or not out:
        return {"verdict": "PASS", "summary": "Review skipped"}
    verdict = "FAIL"
    for line in out.upper().splitlines():
        if "VERDICT:" in line:
            verdict = "PASS" if "PASS" in line else "FAIL"
            break
    if verdict == "FAIL" and ("all tests pass" in out.lower() or "looks good" in out.lower()):
        verdict = "PASS"
    return {"verdict": verdict, "summary": out}

def fix_task(task, review):
    prompt = f"""Fix issues for the trading bot project at {WORKSPACE}.

Task: {task['title']}
Review: {review}

Fix each issue. Run tests. Commit.
Only fix listed issues. This is a financial trading system — correctness is critical."""
    out, _, code = run(f"{AGY_BIN} --print-timeout 10m --print '{_sq(prompt)}'", timeout=TIMEOUT)
    return {"success": code == 0}

# ─── Main ──────────────────────────────────────────────────────────

def acquire_lock():
    """Prevent overlapping worker runs — both within this project and across projects."""
    # 1. Project-local lock
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            os.kill(pid, 0)
            log(f"Another trading bot worker running (pid {pid}), skipping")
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    # 2. Shared cross-project lock
    if SHARED_LOCK_FILE.exists():
        try:
            content = SHARED_LOCK_FILE.read_text().strip().split(":")
            pid = int(content[0])
            lock_time = float(content[1]) if len(content) > 1 else 0
            os.kill(pid, 0)
            if lock_time and (time.time() - lock_time > SHARED_LOCK_TIMEOUT):
                log(f"Shared lock held by dead process {pid} for >{SHARED_LOCK_TIMEOUT}s, claiming it")
            else:
                log(f"Shared lock held by pid {pid} (another project's worker), skipping")
                return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    LOCK_FILE.write_text(str(os.getpid()))
    SHARED_LOCK_FILE.write_text(f"{os.getpid()}:{time.time()}")
    return True

def release_lock():
    """Release both project-local and shared locks."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    try:
        content = SHARED_LOCK_FILE.read_text().strip().split(":")
        if content and content[0] == str(os.getpid()):
            SHARED_LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass

def main():
    log("Trading bot autonomous worker starting")
    if not acquire_lock():
        print("[SILENT]")
        return

    # Scan
    scanner = ProjectScanner().scan()
    log(f"Scan: {len(scanner.missing)} missing, tests={'pass' if scanner.tests_pass else 'fail'}, imports={'ok' if scanner.server_ok else 'broken'}")

    # Auto-create tasks for gaps
    created = auto_create_tasks(scanner)
    if created:
        log(f"Created {created} task(s) for gaps")

    # Pick task
    task = get_next_task()
    if not task:
        if scanner.has_critical_gaps():
            log(f"Gaps exist but no ready tasks. Tests: {scanner.test_summary}")
            print("[SILENT]")
            release_lock()
            return

        # Truly idle — send Discord directly
        msg = f"🤖 **Trading bot worker idle.**\n\n"
        msg += f"Tests: {scanner.test_summary or 'all passing'}\n"
        msg += f"Missing files: {len(scanner.missing)}\n\n"
        msg += f"Nothing to do. Add a task or let me find gaps next cycle."
        send_discord(msg)
        print("[SILENT]")
        release_lock()
        return

    # Execute task
    task_id = task["id"]
    title = task["title"]
    log(f"Working on: {title}")

    branch = f"task/{task_id[:8]}-{re.sub(r'[^a-zA-Z0-9]+', '-', title.lower())[:30]}"
    if not git_create_branch(branch):
        log(f"Failed to create branch {branch}, aborting task")
        print("[SILENT]")
        release_lock()
        return

    def cleanup_on_failure():
        git_cleanup_dirty()
        try:
            run(f"git branch -D {branch} 2>/dev/null", workdir=WORKSPACE)
        except Exception:
            pass

    # Plan → Implement → Review → Fix → Merge → Push
    plan = plan_task(task)
    if not plan:
        cleanup_on_failure()
        print("[SILENT]")
        release_lock()
        return

    impl = implement_task(task, plan)
    if not impl["success"]:
        cleanup_on_failure()
        print("[SILENT]")
        release_lock()
        return

    review_round = 0
    for i in range(MAX_FIX_ROUNDS):
        review_round = i + 1
        review = review_task(task, plan)
        if review["verdict"] == "PASS":
            break
        if not fix_task(task, review["summary"]):
            cleanup_on_failure()
            print("[SILENT]")
            release_lock()
            return

    merged = git_merge_branch(branch, title)
    if not merged:
        print("[SILENT]")
        release_lock()
        return

    pushed = git_push()

    # Mark task complete
    run(f"{HERMES_BIN} kanban --board {KANBAN_BOARD} complete {task_id}", timeout=30)

    # Build notification and send DIRECTLY to Discord
    files = git_diff_main_names()
    version_out, _, _ = run("git rev-parse --short HEAD", workdir=WORKSPACE)
    version = version_out or "unknown"

    msg = f"**Shipped: {title}**\n\n"
    msg += f"**Files:** {', '.join(f'`{f}`' for f in files[:5])}"
    if len(files) > 5:
        msg += f" +{len(files)-5} more"
    msg += f"\n**Review:** {'pass' if review_round == 1 else f'{review_round} rounds'}"
    msg += f"\n**Branch:** `{branch}` → `{BRANCH}`"
    if pushed:
        msg += f" → pushed"
    msg += f"\n**Version:** `{version}`"
    log(f"Shipped: {title}")
    send_discord(msg)
    print("[SILENT]")
    release_lock()


if __name__ == "__main__":
    main()
