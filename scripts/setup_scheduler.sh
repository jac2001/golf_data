#!/bin/bash
#
# Golf Data Scheduler Setup
# =========================
# Installs/uninstalls launchd jobs for automated data refresh on macOS.
#
# Usage:
#   ./scripts/setup_scheduler.sh install    # Install all scheduled jobs
#   ./scripts/setup_scheduler.sh uninstall  # Remove all scheduled jobs
#   ./scripts/setup_scheduler.sh status     # Check job status
#

PROJECT_ROOT="/Users/jacklegnon/Desktop/golf_data"
PLIST_DIR="$HOME/Library/LaunchAgents"
PYTHON_PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
LOG_DIR="$PROJECT_ROOT/logs"

# Create logs directory
mkdir -p "$LOG_DIR"

create_plist() {
    local name=$1
    local schedule=$2
    local hour=$3
    local minute=$4
    local weekday=$5  # 0=Sunday, 1=Monday, etc. Use "*" for daily

    local plist_file="$PLIST_DIR/com.golfdata.$name.plist"

    cat > "$plist_file" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.golfdata.$name</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$PROJECT_ROOT/scripts/scheduled_refresh.py</string>
        <string>--schedule</string>
        <string>$schedule</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_ROOT</string>
    <key>StartCalendarInterval</key>
EOF

    if [ "$weekday" = "*" ]; then
        cat >> "$plist_file" << EOF
    <dict>
        <key>Hour</key>
        <integer>$hour</integer>
        <key>Minute</key>
        <integer>$minute</integer>
    </dict>
EOF
    else
        cat >> "$plist_file" << EOF
    <dict>
        <key>Weekday</key>
        <integer>$weekday</integer>
        <key>Hour</key>
        <integer>$hour</integer>
        <key>Minute</key>
        <integer>$minute</integer>
    </dict>
EOF
    fi

    cat >> "$plist_file" << EOF
    <key>StandardOutPath</key>
    <string>$LOG_DIR/$name.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/$name.error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

    echo "Created: $plist_file"
}

install_jobs() {
    echo "Installing Golf Data scheduled jobs..."
    echo ""

    mkdir -p "$PLIST_DIR"

    # Monday 6:00 AM - Post-tournament refresh
    create_plist "monday" "monday" 6 0 1

    # Tuesday 6:00 AM - Tournament prep
    create_plist "tuesday-morning" "tuesday-morning" 6 0 2

    # Tuesday 6:00 PM - Odds refresh
    create_plist "tuesday-evening" "tuesday-evening" 18 0 2

    # Wednesday 6:00 AM - Final prep
    create_plist "wednesday-morning" "wednesday-morning" 6 0 3

    # Wednesday 6:00 PM - Final odds
    create_plist "wednesday-evening" "wednesday-evening" 18 0 3

    # Thursday-Sunday live updates (using multiple plists)
    # 8 AM
    for day in 4 5 6 0; do
        day_name=$([ $day -eq 0 ] && echo "sunday" || echo "day$day")
        create_plist "live-${day_name}-8am" "live" 8 0 $day
    done

    # 2 PM
    for day in 4 5 6 0; do
        day_name=$([ $day -eq 0 ] && echo "sunday" || echo "day$day")
        create_plist "live-${day_name}-2pm" "live" 14 0 $day
    done

    # 8 PM
    for day in 4 5 6 0; do
        day_name=$([ $day -eq 0 ] && echo "sunday" || echo "day$day")
        create_plist "live-${day_name}-8pm" "live" 20 0 $day
    done

    # Sunday 9 PM - Post-tournament refresh (first attempt)
    create_plist "post-sunday-9pm" "post-tournament" 21 0 0

    # Sunday 11 PM - Record results
    create_plist "record" "record" 23 0 0

    # Monday 8 AM - Post-tournament fallback (if Mac was asleep Sunday)
    create_plist "post-monday-8am" "post-tournament" 8 0 1

    echo ""
    echo "Loading jobs..."

    for plist in "$PLIST_DIR"/com.golfdata.*.plist; do
        if [ -f "$plist" ]; then
            launchctl load "$plist" 2>/dev/null
            echo "Loaded: $(basename "$plist")"
        fi
    done

    echo ""
    echo "✓ Installation complete!"
    echo ""
    echo "Jobs will run automatically on schedule."
    echo "View logs in: $LOG_DIR"
}

uninstall_jobs() {
    echo "Uninstalling Golf Data scheduled jobs..."
    echo ""

    for plist in "$PLIST_DIR"/com.golfdata.*.plist; do
        if [ -f "$plist" ]; then
            launchctl unload "$plist" 2>/dev/null
            rm "$plist"
            echo "Removed: $(basename "$plist")"
        fi
    done

    echo ""
    echo "✓ All jobs removed."
}

status_jobs() {
    echo "Golf Data Scheduled Jobs Status"
    echo "================================"
    echo ""

    local found=0
    for plist in "$PLIST_DIR"/com.golfdata.*.plist; do
        if [ -f "$plist" ]; then
            found=1
            local name=$(basename "$plist" .plist)
            local status=$(launchctl list | grep "$name" > /dev/null && echo "✓ Running" || echo "○ Loaded")
            echo "$status: $name"
        fi
    done

    if [ $found -eq 0 ]; then
        echo "No Golf Data jobs installed."
        echo ""
        echo "Run: ./scripts/setup_scheduler.sh install"
    fi

    echo ""
    echo "Recent logs:"
    ls -lt "$LOG_DIR"/*.log 2>/dev/null | head -5

    echo ""
    echo "Last run history:"
    if [ -f "$LOG_DIR/scheduler_history.json" ]; then
        tail -20 "$LOG_DIR/scheduler_history.json" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, list) and data:
        for entry in data[-3:]:
            ts = entry.get('timestamp', 'Unknown')[:19]
            sched = entry.get('schedule', 'Unknown')
            success = entry.get('success_count', 0)
            total = entry.get('total_count', 0)
            print(f'  {ts} | {sched}: {success}/{total} succeeded')
except:
    print('  No history available')
" 2>/dev/null || echo "  No history available"
    else
        echo "  No history yet"
    fi
}

case "$1" in
    install)
        install_jobs
        ;;
    uninstall)
        uninstall_jobs
        ;;
    status)
        status_jobs
        ;;
    *)
        echo "Usage: $0 {install|uninstall|status}"
        echo ""
        echo "Commands:"
        echo "  install    - Install all scheduled jobs"
        echo "  uninstall  - Remove all scheduled jobs"
        echo "  status     - Check job status and recent runs"
        exit 1
        ;;
esac
