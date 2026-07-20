#!/usr/bin/env bash
# Daily PO report for trading-bot board
# Run at 20:00 UTC

BOARD="trading-bot"
DISCORD_CHANNEL="1528703254102413434"  # #trading-bot

echo "📊 **Trading Bot PO Daily Report**"
echo ""

# Get task counts by status
TOTAL=$(hermes kanban --board $BOARD list 2>/dev/null | wc -l)
RUNNING=$(hermes kanban --board $BOARD list 2>/dev/null | grep "running" | wc -l)
READY=$(hermes kanban --board $BOARD list 2>/dev/null | grep "ready" | wc -l)
DONE=$(hermes kanban --board $BOARD list 2>/dev/null | grep "done" | wc -l)
BLOCKED=$(hermes kanban --board $BOARD list 2>/dev/null | grep "blocked" | wc -l)

echo "**Task Status:**"
echo "- Running: $RUNNING"
echo "- Ready: $READY"
echo "- Done: $DONE"
echo "- Blocked: $BLOCKED"
echo ""

# List completed tasks in last 24h
echo "**Completed Today:**"
hermes kanban --board $BOARD list 2>/dev/null | grep "done" | head -10
echo ""

# List blocked tasks
if [ $BLOCKED -gt 0 ]; then
    echo "**Blocked Tasks:**"
    hermes kanban --board $BOARD list 2>/dev/null | grep "blocked" | head -5
    echo ""
fi

# Git activity
cd /home/pascal/workspace/tradingbot-fixed
echo "**Git Activity (24h):**"
git log --oneline --since="24 hours ago" 2>/dev/null | head -10
echo ""

# Worker status
echo "**Worker Status:**"
ps aux | grep "work kanban task" | grep -v grep | wc -l
echo " workers active"
