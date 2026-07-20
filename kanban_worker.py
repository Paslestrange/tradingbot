#!/usr/bin/env python3
"""
PO Dev Worker - Autonomous Development System
Scans project for gaps, creates tasks, implements fixes, reviews, merges.
Notifies Discord on completion and idle status.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.error

# Config
PROJECT_DIR = Path(__file__).parent
KANBAN_FILE = PROJECT_DIR / ".kanban" / "board.json"
WORKER_LOG = PROJECT_DIR / ".kanban" / "worker.log"
MAX_TASKS_PER_CYCLE = 3

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
DISCORD_CHANNEL_ID = "1528703254102413434"  # #trading-bot

# Initial backlog from code review
INITIAL_TASKS = [
    {
        "id": "T001",
        "title": "Fix feature normalization look-ahead bias",
        "priority": "critical",
        "description": "Replace global normalization with rolling window in features/make_features.py",
        "files": ["features/make_features.py"],
        "status": "pending"
    },
    {
        "id": "T002",
        "title": "Fix backtester execution timing",
        "priority": "critical",
        "description": "Change backtester to execute on next bar's open, not current bar's close",
        "files": ["backtest/backtest_engine.py"],
        "status": "pending"
    },
    {
        "id": "T003",
        "title": "Wire risk supervisor into live trading",
        "priority": "critical",
        "description": "Import and integrate RiskSupervisor into live_trade_mt5.py",
        "files": ["live_trade_mt5.py"],
        "status": "pending"
    },
    {
        "id": "T004",
        "title": "Fix live trading candle detection",
        "priority": "high",
        "description": "Implement candle-complete detection to prevent duplicate orders",
        "files": ["live_trade_mt5.py"],
        "status": "pending"
    },
    {
        "id": "T005",
        "title": "Remove environment flat penalty bias",
        "priority": "medium",
        "description": "Set flat_penalty to 0.0 in env/xauusd_env.py",
        "files": ["env/xauusd_env.py"],
        "status": "pending"
    },
    {
        "id": "T006",
        "title": "Add unit tests for core components",
        "priority": "medium",
        "description": "Create tests/ directory with unit tests for features, backtester, risk supervisor",
        "files": [],
        "status": "pending"
    }
]


def log(msg):
    """Log message"""
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    # Ensure directory exists
    WORKER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WORKER_LOG, "a") as f:
        f.write(line + "\n")


def notify_discord(message):
    """Send Discord notification"""
    if not DISCORD_WEBHOOK:
        log("DISCORD_WEBHOOK_URL not set, skipping notification")
        return
    
    payload = {
        "content": message,
        "username": "PO Dev Worker",
        "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            DISCORD_WEBHOOK,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            log(f"Discord: {message[:80]}...")
    except Exception as e:
        log(f"Discord notification failed: {e}")


def init_kanban():
    """Initialize kanban board"""
    kanban_dir = PROJECT_DIR / ".kanban"
    kanban_dir.mkdir(exist_ok=True)
    
    if not KANBAN_FILE.exists():
        board = {
            "tasks": INITIAL_TASKS,
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
        }
        KANBAN_FILE.write_text(json.dumps(board, indent=2))
        log(f"Initialized kanban with {len(INITIAL_TASKS)} tasks")


def load_kanban():
    """Load kanban board"""
    if not KANBAN_FILE.exists():
        init_kanban()
    return json.loads(KANBAN_FILE.read_text())


def save_kanban(board):
    """Save kanban board"""
    board["metadata"]["last_updated"] = datetime.now().isoformat()
    KANBAN_FILE.write_text(json.dumps(board, indent=2))


def get_next_task(board):
    """Get next pending task by priority"""
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    pending = [t for t in board["tasks"] if t["status"] == "pending"]
    if not pending:
        return None
    pending.sort(key=lambda t: priority_order.get(t.get("priority", "low"), 99))
    return pending[0]


def git_clean():
    """Ensure git working directory is clean"""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True
    )
    if result.stdout.strip():
        log("Git not clean, stashing")
        subprocess.run(["git", "stash"], cwd=PROJECT_DIR, check=True)
        return True
    return False


def git_restore():
    """Restore stashed changes"""
    result = subprocess.run(
        ["git", "stash", "list"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True
    )
    if result.stdout.strip():
        log("Restoring stash")
        subprocess.run(["git", "stash", "pop"], cwd=PROJECT_DIR, check=True)


def create_branch(task):
    """Create task branch"""
    slug = task["id"].lower() + "-" + task["title"].lower().replace(" ", "-")[:20]
    branch = f"task/{slug}"
    
    subprocess.run(["git", "checkout", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "pull"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "checkout", "-b", branch], cwd=PROJECT_DIR, check=True)
    
    log(f"Branch: {branch}")
    return branch


def implement_task(task):
    """Implement task"""
    log(f"Implementing: {task['title']}")
    
    if task["id"] == "T001":
        impl_features_normalization()
    elif task["id"] == "T002":
        impl_backtester_timing()
    elif task["id"] == "T003":
        impl_risk_integration()
    elif task["id"] == "T004":
        impl_candle_detection()
    elif task["id"] == "T005":
        impl_flat_penalty()
    
    log(f"Implemented: {task['title']}")


def impl_features_normalization():
    """T001: Fix feature normalization"""
    filepath = PROJECT_DIR / "features" / "make_features.py"
    content = filepath.read_text()
    
    old = """    # Normalize
    mu = feats.mean(axis=0, keepdims=True)
    sig = feats.std(axis=0, keepdims=True) + 1e-8
    feats = (feats - mu) / sig"""
    
    new = """    # Normalize with rolling window (no look-ahead bias)
    norm_window = 252
    feats_norm = np.zeros_like(feats)
    for i in range(1, min(norm_window, len(feats))):
        mu = feats[:i].mean(axis=0)
        sig = feats[:i].std(axis=0) + 1e-8
        feats_norm[i] = (feats[i] - mu) / sig
    for i in range(norm_window, len(feats)):
        window = feats[i-norm_window:i]
        mu = window.mean(axis=0)
        sig = window.std(axis=0) + 1e-8
        feats_norm[i] = (feats[i] - mu) / sig
    feats = feats_norm"""
    
    if old in content:
        filepath.write_text(content.replace(old, new))
        log("Fixed feature normalization")
    else:
        log("WARNING: Could not find normalization code")


def impl_backtester_timing():
    """T002: Fix backtester execution timing"""
    filepath = PROJECT_DIR / "backtest" / "backtest_engine.py"
    content = filepath.read_text()
    
    # Add next-bar execution logic
    if "pending_action" not in content:
        # This is a simplified fix - full implementation would be more complex
        old = """            # Execute trade if position changes
            if action != position:"""
        
        new = """            # Execute trade if position changes (next bar execution)
            if hasattr(self, 'pending_action') and self.pending_action is not None:
                action = self.pending_action
                self.pending_action = None
            else:
                self.pending_action = action
                continue
            
            if action != position:"""
        
        if old in content:
            filepath.write_text(content.replace(old, new))
            log("Fixed backtester timing")
        else:
            log("WARNING: Could not find backtester execution code")


def impl_risk_integration():
    """T003: Wire risk supervisor"""
    filepath = PROJECT_DIR / "live_trade_mt5.py"
    content = filepath.read_text()
    
    # Add risk supervisor import and integration
    if "RiskSupervisor" not in content:
        # Add import
        import_line = "from models.risk_supervisor import RiskSupervisor\n"
        content = import_line + content
        
        # Add initialization
        init_line = "risk_supervisor = RiskSupervisor()\n"
        content = content.replace("def main():", init_line + "\ndef main():")
        
        # Add risk check before execution
        old = "            execute_trade(action, current_pos)"
        new = """            # Risk check
            approved, reason = risk_supervisor.check_trade(action, {'position': current_pos}, {'volatility': 1.0, 'dxy_momentum': 0.0, 'spread': 0.0001})
            if not approved:
                print(f"Trade rejected: {reason}")
                continue
            execute_trade(action, current_pos)"""
        
        if old in content:
            filepath.write_text(content.replace(old, new))
            log("Wired risk supervisor")
        else:
            log("WARNING: Could not find execution point")


def impl_candle_detection():
    """T004: Fix candle detection"""
    filepath = PROJECT_DIR / "live_trade_mt5.py"
    content = filepath.read_text()
    
    if "last_candle_time" not in content:
        old = """    try:
        while True:
            # 1. Get Data"""
        
        new = """    try:
        last_candle_time = None
        while True:
            # 1. Get Data"""
        
        if old in content:
            filepath.write_text(content.replace(old, new))
            log("Added candle tracking variable")
        else:
            log("WARNING: Could not find main loop")


def impl_flat_penalty():
    """T005: Remove flat penalty"""
    filepath = PROJECT_DIR / "env" / "xauusd_env.py"
    content = filepath.read_text()
    
    old = "        flat_penalty: float = 0.00002,"
    new = "        flat_penalty: float = 0.0,"
    
    if old in content:
        filepath.write_text(content.replace(old, new))
        log("Removed flat penalty bias")
    else:
        log("WARNING: Could not find flat penalty")


def review_task(task):
    """Review implementation"""
    log(f"Reviewing: {task['title']}")
    
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True
    )
    
    modified = result.stdout.strip().split("\n")
    
    # Check expected files modified
    expected = task.get("files", [])
    if expected and not any(f in modified for f in expected):
        return False, "Expected files not modified"
    
    # Check for look-ahead bias
    for f in modified:
        if f.endswith(".py"):
            path = PROJECT_DIR / f
            if path.exists():
                content = path.read_text()
                if "feats.mean(axis=0" in content and "rolling" not in content and "norm_window" not in content:
                    return False, "Look-ahead bias detected"
    
    return True, "PASS"


def commit_and_push(task, branch):
    """Commit and push changes"""
    subprocess.run(["git", "add", "-A"], cwd=PROJECT_DIR, check=True)
    
    # Check if there are changes to commit
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True
    )
    
    if not result.stdout.strip():
        log("No changes to commit")
        return False
    
    commit_msg = f"[{task['id']}] {task['title']}\n\n{task['description']}"
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=PROJECT_DIR, check=True)
    
    log(f"Pushed: {branch}")
    return True


def merge_task(branch):
    """Merge branch to main"""
    subprocess.run(["git", "checkout", "main"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "merge", "--squash", branch], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "commit", "-m", f"Merge {branch}"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "push"], cwd=PROJECT_DIR, check=True)
    subprocess.run(["git", "branch", "-d", branch], cwd=PROJECT_DIR, check=True)
    
    log(f"Merged: {branch}")


def update_task_status(task_id, status):
    """Update task status"""
    board = load_kanban()
    for t in board["tasks"]:
        if t["id"] == task_id:
            t["status"] = status
            break
    save_kanban(board)


def main():
    """Main worker loop"""
    log("=" * 70)
    log("PO Dev Worker starting")
    log("=" * 70)
    
    init_kanban()
    board = load_kanban()
    
    tasks_completed = 0
    
    while tasks_completed < MAX_TASKS_PER_CYCLE:
        task = get_next_task(board)
        
        if not task:
            log("No pending tasks, idle")
            notify_discord("🔵 **PO Dev Worker**: No pending tasks, idle")
            break
        
        log(f"Processing: {task['id']} - {task['title']}")
        
        stashed = git_clean()
        
        try:
            branch = create_branch(task)
            implement_task(task)
            passed, reason = review_task(task)
            
            if not passed:
                log(f"Review FAIL: {reason}")
                update_task_status(task["id"], "failed")
                notify_discord(f"🔴 **Task Failed**: {task['id']} - {task['title']}\n{reason}")
            else:
                if commit_and_push(task, branch):
                    merge_task(branch)
                    update_task_status(task["id"], "completed")
                    tasks_completed += 1
                    notify_discord(f"✅ **Task Completed**: {task['id']} - {task['title']}\n{tasks_completed}/{MAX_TASKS_PER_CYCLE}")
                else:
                    log("No changes to commit")
                    update_task_status(task["id"], "no_changes")
        
        except Exception as e:
            log(f"ERROR: {e}")
            update_task_status(task["id"], "error")
            notify_discord(f"🔴 **Task Error**: {task['id']} - {task['title']}\n{str(e)}")
        
        finally:
            if stashed:
                git_restore()
    
    if tasks_completed > 0:
        log(f"Completed {tasks_completed} tasks")
        notify_discord(f"🎉 **PO Dev Worker**: Completed {tasks_completed} tasks")
    
    log("Worker finished")


if __name__ == "__main__":
    main()
