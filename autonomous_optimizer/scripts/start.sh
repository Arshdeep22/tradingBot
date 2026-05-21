#!/usr/bin/env bash
# Start the autonomous optimizer in a persistent tmux session.
# Usage: ./autonomous_optimizer/scripts/start.sh [--dry-run]

SESSION="trading-agent"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Session '$SESSION' already running. Attach: tmux attach -t $SESSION"
    exit 0
fi

cd "$REPO_ROOT" || exit 1
source .venv/bin/activate 2>/dev/null || true

tmux new-session -d -s "$SESSION" \
    "python -m autonomous_optimizer $*; echo 'AGENT STOPPED — press any key'; read"

echo "Started in tmux session '$SESSION'"
echo "Attach: tmux attach -t $SESSION"
echo "Detach: Ctrl+B then D"
