#!/bin/bash

#
# Gaming-Specific PostgreSQL Metrics Collection for Hokm Server
# This script collects and analyzes gaming-specific database metrics
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORTS_DIR="${SCRIPT_DIR}/../reports/gaming"
METRICS_FILE="${SCRIPT_DIR}/../logs/gaming-metrics.log"

# Database connection
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-hokm_game}"
DB_USER="${DB_USER:-postgres}"

# Gaming-specific thresholds
MAX_ACTIVE_GAMES=${MAX_ACTIVE_GAMES:-200}
MAX_CONCURRENT_PLAYERS=${MAX_CONCURRENT_PLAYERS:-1000}
MAX_GAME_DURATION_HOURS=${MAX_GAME_DURATION_HOURS:-2}
MIN_MOVES_PER_MINUTE=${MIN_MOVES_PER_MINUTE:-10}

# Alert settings
ALERT_WEBHOOK="${ALERT_WEBHOOK:-}"
ALERT_EMAIL="${ALERT_EMAIL:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        ERROR) echo -e "${RED}[$timestamp] ERROR: $message${NC}" ;;
        WARN)  echo -e "${YELLOW}[$timestamp] WARN: $message${NC}" ;;
        INFO)  echo -e "${BLUE}[$timestamp] INFO: $message${NC}" ;;
        SUCCESS) echo -e "${GREEN}[$timestamp] SUCCESS: $message${NC}" ;;
        GAMING) echo -e "${PURPLE}[$timestamp] GAMING: $message${NC}" ;;
        METRICS) echo -e "${CYAN}[$timestamp] METRICS: $message${NC}" ;;
    esac
    
    # Log to file
    mkdir -p "$(dirname "$METRICS_FILE")"
    echo "[$timestamp] $level: $message" >> "$METRICS_FILE"
}

# Execute database query
query_db() {
    local query="$1"
    PGPASSWORD="${DB_PASSWORD:-}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -A -c "$query" 2>/dev/null
}

# Collect gaming metrics
collect_gaming_metrics() {
    log GAMING "Collecting gaming-specific metrics..."
    
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local metrics_json=""
    
    # Active games count
    local active_games
    active_games=$(query_db "SELECT COUNT(*) FROM game_sessions WHERE status IN ('waiting', 'active', 'playing');")
    if [ -z "$active_games" ]; then active_games=0; fi
    log METRICS "Active games: $active_games"
    
    # Online players count
    local online_players
    online_players=$(query_db "SELECT COUNT(DISTINCT player_id) FROM websocket_connections WHERE status = 'connected' AND last_ping > NOW() - INTERVAL '5 minutes';")
    if [ -z "$online_players" ]; then online_players=0; fi
    log METRICS "Online players: $online_players"
    
    # Games per hour
    local games_per_hour
    games_per_hour=$(query_db "SELECT COUNT(*) FROM game_sessions WHERE created_at > NOW() - INTERVAL '1 hour';")
    if [ -z "$games_per_hour" ]; then games_per_hour=0; fi
    log METRICS "Games started in last hour: $games_per_hour"
    
    # Average game duration
    local avg_game_duration
    avg_game_duration=$(query_db "SELECT EXTRACT(EPOCH FROM AVG(finished_at - created_at))/60 FROM game_sessions WHERE finished_at IS NOT NULL AND finished_at > NOW() - INTERVAL '24 hours';")
    if [ -z "$avg_game_duration" ]; then avg_game_duration=0; fi
    log METRICS "Average game duration (minutes): ${avg_game_duration%.*}"
    
    # Moves per minute
    local moves_per_minute
    moves_per_minute=$(query_db "SELECT COUNT(*) FROM game_moves WHERE created_at > NOW() - INTERVAL '1 minute';")
    if [ -z "$moves_per_minute" ]; then moves_per_minute=0; fi
    log METRICS "Moves in last minute: $moves_per_minute"
    
    # Long-running games
    local long_games
    long_games=$(query_db "SELECT COUNT(*) FROM game_sessions WHERE status IN ('active', 'playing') AND created_at < NOW() - INTERVAL '${MAX_GAME_DURATION_HOURS} hours';")
    if [ -z "$long_games" ]; then long_games=0; fi
    log METRICS "Long-running games (>${MAX_GAME_DURATION_HOURS}h): $long_games"
    
    # Room occupancy
    local room_occupancy
    room_occupancy=$(query_db "SELECT ROUND(AVG(CASE WHEN player_count > 0 THEN player_count::float / max_players * 100 ELSE 0 END), 2) FROM game_rooms WHERE status = 'active';")
    if [ -z "$room_occupancy" ]; then room_occupancy=0; fi
    log METRICS "Average room occupancy: ${room_occupancy}%"
    
    # Top players by games played today
    local top_players
    top_players=$(query_db "SELECT player_id, COUNT(*) as games_played FROM game_sessions WHERE created_at > CURRENT_DATE GROUP BY player_id ORDER BY games_played DESC LIMIT 5;")
    
    # Database query performance for gaming tables
    local game_query_performance
    game_query_performance=$(query_db "
        SELECT 
            LEFT(query, 50) as query_preview,
            calls,
            ROUND(total_exec_time/1000, 2) as total_time_seconds,
            ROUND(mean_exec_time/1000, 4) as avg_time_seconds
        FROM pg_stat_statements 
        WHERE query ILIKE '%game_%' OR query ILIKE '%player%' OR query ILIKE '%websocket%'
        ORDER BY total_exec_time DESC 
        LIMIT 10;
    ")
    
    # Table sizes for gaming tables
    local table_sizes
    table_sizes=$(query_db "
        SELECT 
            schemaname,
            tablename,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
        FROM pg_tables 
        WHERE tablename LIKE 'game_%' OR tablename LIKE 'player_%' OR tablename LIKE 'websocket_%'
        ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
    ")
    
    # Store metrics in JSON format
    metrics_json=$(cat <<EOF
{
    "timestamp": "$timestamp",
    "active_games": $active_games,
    "online_players": $online_players,
    "games_per_hour": $games_per_hour,
    "avg_game_duration_minutes": ${avg_game_duration%.*},
    "moves_per_minute": $moves_per_minute,
    "long_running_games": $long_games,
    "room_occupancy_percent": $room_occupancy,
    "database_health": {
        "connections": $(query_db "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$DB_NAME';"),
        "cache_hit_ratio": $(query_db "SELECT ROUND(100.0 * sum(blks_hit) / NULLIF(sum(blks_hit) + sum(blks_read), 0), 2) FROM pg_stat_database WHERE datname = '$DB_NAME';"),
        "database_size_mb": $(query_db "SELECT ROUND(pg_database_size('$DB_NAME') / 1024.0 / 1024.0, 2);")
    }
}
EOF
    )
    
    # Save metrics to file
    mkdir -p "$REPORTS_DIR"
    echo "$metrics_json" > "$REPORTS_DIR/latest_metrics.json"
    echo "$metrics_json" >> "$REPORTS_DIR/metrics_history.jsonl"
    
    log SUCCESS "Gaming metrics collected and saved"
    
    # Check for alerts
    check_gaming_alerts "$active_games" "$online_players" "$long_games" "$moves_per_minute"
}

# Check for gaming-specific alerts
check_gaming_alerts() {
    local active_games="$1"
    local online_players="$2"
    local long_games="$3"
    local moves_per_minute="$4"
    
    log GAMING "Checking gaming alerts..."
    
    # High active games alert
    if [ "$active_games" -gt "$MAX_ACTIVE_GAMES" ]; then
        send_alert "HIGH_ACTIVE_GAMES" "WARNING" "High number of active games: $active_games (threshold: $MAX_ACTIVE_GAMES)"
    fi
    
    # High concurrent players alert
    if [ "$online_players" -gt "$MAX_CONCURRENT_PLAYERS" ]; then
        send_alert "HIGH_CONCURRENT_PLAYERS" "WARNING" "High number of concurrent players: $online_players (threshold: $MAX_CONCURRENT_PLAYERS)"
    fi
    
    # Long-running games alert
    if [ "$long_games" -gt 0 ]; then
        send_alert "LONG_RUNNING_GAMES" "INFO" "Long-running games detected: $long_games games running for more than ${MAX_GAME_DURATION_HOURS} hours"
    fi
    
    # Low activity alert
    if [ "$moves_per_minute" -lt "$MIN_MOVES_PER_MINUTE" ]; then
        send_alert "LOW_ACTIVITY" "INFO" "Low gaming activity: $moves_per_minute moves/minute (threshold: $MIN_MOVES_PER_MINUTE)"
    fi
    
    # Very high activity alert
    if [ "$moves_per_minute" -gt 500 ]; then
        send_alert "VERY_HIGH_ACTIVITY" "WARNING" "Very high gaming activity: $moves_per_minute moves/minute - may impact performance"
    fi
}

# Send alert notification
send_alert() {
    local alert_type="$1"
    local severity="$2"
    local message="$3"
    
    log WARN "ALERT [$severity] $alert_type: $message"
    
    # Send webhook notification
    if [ -n "$ALERT_WEBHOOK" ]; then
        local payload=$(cat <<EOF
{
    "text": "🎮 Gaming Alert: $message",
    "attachments": [
        {
            "color": $([ "$severity" = "CRITICAL" ] && echo '"danger"' || [ "$severity" = "WARNING" ] && echo '"warning"' || echo '"good"'),
            "fields": [
                {
                    "title": "Alert Type",
                    "value": "$alert_type",
                    "short": true
                },
                {
                    "title": "Severity",
                    "value": "$severity",
                    "short": true
                },
                {
                    "title": "Database",
                    "value": "$DB_NAME on $DB_HOST",
                    "short": false
                }
            ],
            "footer": "Hokm Gaming Monitor",
            "ts": $(date +%s)
        }
    ]
}
EOF
        )
        
        curl -X POST -H 'Content-type: application/json' \
            --data "$payload" \
            "$ALERT_WEBHOOK" >/dev/null 2>&1 || true
    fi
    
    # Send email notification
    if [ -n "$ALERT_EMAIL" ] && command -v mail >/dev/null 2>&1; then
        echo -e "Gaming Alert: $message\n\nAlert Type: $alert_type\nSeverity: $severity\nTime: $(date)\nDatabase: $DB_NAME on $DB_HOST" | \
            mail -s "🎮 Hokm Gaming Alert - $severity" "$ALERT_EMAIL" || true
    fi
}

# Generate gaming performance report
generate_gaming_report() {
    log GAMING "Generating gaming performance report..."
    
    local report_file="$REPORTS_DIR/gaming_report_$(date +%Y%m%d_%H%M%S).html"
    
    # Get latest metrics
    local latest_metrics="$REPORTS_DIR/latest_metrics.json"
    if [ ! -f "$latest_metrics" ]; then
        log ERROR "No metrics file found. Run collect first."
        return 1
    fi
    
    # Generate HTML report
    cat > "$report_file" << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hokm Gaming Performance Report</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0; padding: 20px; background-color: #f5f5f5;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px;
            text-align: center;
        }
        .header h1 { margin: 0; font-size: 2.5em; }
        .header p { margin: 10px 0 0 0; opacity: 0.9; }
        .metrics-grid { 
            display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px; margin-bottom: 30px;
        }
        .metric-card { 
            background: white; padding: 25px; border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center;
        }
        .metric-value { 
            font-size: 2.5em; font-weight: bold; color: #667eea;
            margin: 10px 0;
        }
        .metric-label { color: #666; font-size: 0.9em; text-transform: uppercase; }
        .section { 
            background: white; padding: 30px; border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 30px;
        }
        .section h2 { 
            color: #333; margin-top: 0; padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }
        .table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        .table th, .table td { 
            padding: 12px; text-align: left; border-bottom: 1px solid #eee;
        }
        .table th { background-color: #f8f9fa; font-weight: 600; }
        .status-good { color: #28a745; }
        .status-warning { color: #ffc107; }
        .status-danger { color: #dc3545; }
        .chart-placeholder { 
            height: 200px; background: #f8f9fa; border-radius: 5px;
            display: flex; align-items: center; justify-content: center;
            color: #666; font-style: italic;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎮 Hokm Gaming Performance Report</h1>
            <p>Real-time gaming metrics and database performance analysis</p>
            <p>Generated: <span id="timestamp"></span></p>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Active Games</div>
                <div class="metric-value" id="active-games">-</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Online Players</div>
                <div class="metric-value" id="online-players">-</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Games/Hour</div>
                <div class="metric-value" id="games-per-hour">-</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Avg Game Duration</div>
                <div class="metric-value" id="avg-duration">-</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Moves/Minute</div>
                <div class="metric-value" id="moves-per-minute">-</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Room Occupancy</div>
                <div class="metric-value" id="room-occupancy">-</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📊 Database Health</h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">Connections</div>
                    <div class="metric-value" id="db-connections">-</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Cache Hit Ratio</div>
                    <div class="metric-value" id="cache-hit-ratio">-</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Database Size</div>
                    <div class="metric-value" id="db-size">-</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>🎯 Gaming Activity Trends</h2>
            <div class="chart-placeholder">
                Gaming activity charts would be displayed here
                <br>Connect to Grafana for real-time visualization
            </div>
        </div>
        
        <div class="section">
            <h2>⚠️ Alerts & Recommendations</h2>
            <div id="alerts-section">
                <p>No critical alerts detected.</p>
            </div>
        </div>
        
        <div class="section">
            <h2>🔧 Performance Insights</h2>
            <ul>
                <li>Monitor active games to ensure they don't exceed server capacity</li>
                <li>Track player engagement through moves per minute</li>
                <li>Identify long-running games that may need intervention</li>
                <li>Optimize database queries for gaming tables</li>
                <li>Scale resources based on concurrent player trends</li>
            </ul>
        </div>
    </div>
    
    <script>
        // Load and display metrics
        fetch('./latest_metrics.json')
            .then(response => response.json())
            .then(data => {
                document.getElementById('timestamp').textContent = data.timestamp;
                document.getElementById('active-games').textContent = data.active_games;
                document.getElementById('online-players').textContent = data.online_players;
                document.getElementById('games-per-hour').textContent = data.games_per_hour;
                document.getElementById('avg-duration').textContent = data.avg_game_duration_minutes + ' min';
                document.getElementById('moves-per-minute').textContent = data.moves_per_minute;
                document.getElementById('room-occupancy').textContent = data.room_occupancy_percent + '%';
                
                // Database health
                document.getElementById('db-connections').textContent = data.database_health.connections;
                document.getElementById('cache-hit-ratio').textContent = data.database_health.cache_hit_ratio + '%';
                document.getElementById('db-size').textContent = data.database_health.database_size_mb + ' MB';
                
                // Check for alerts
                const alerts = [];
                if (data.active_games > 200) alerts.push('High number of active games');
                if (data.online_players > 1000) alerts.push('High concurrent player count');
                if (data.database_health.cache_hit_ratio < 95) alerts.push('Low cache hit ratio');
                
                if (alerts.length > 0) {
                    document.getElementById('alerts-section').innerHTML = 
                        '<ul>' + alerts.map(alert => `<li class="status-warning">${alert}</li>`).join('') + '</ul>';
                }
            })
            .catch(error => {
                console.error('Error loading metrics:', error);
                document.getElementById('timestamp').textContent = 'Error loading data';
            });
    </script>
</body>
</html>
EOF
    
    log SUCCESS "Gaming report generated: $report_file"
    echo "Report available at: file://$report_file"
}

# Show real-time gaming dashboard
show_dashboard() {
    clear
    echo -e "${PURPLE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║                   🎮 HOKM GAMING DASHBOARD                    ║${NC}"
    echo -e "${PURPLE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo
    
    while true; do
        # Get current metrics
        local active_games=$(query_db "SELECT COUNT(*) FROM game_sessions WHERE status IN ('waiting', 'active', 'playing');" 2>/dev/null || echo "0")
        local online_players=$(query_db "SELECT COUNT(DISTINCT player_id) FROM websocket_connections WHERE status = 'connected' AND last_ping > NOW() - INTERVAL '5 minutes';" 2>/dev/null || echo "0")
        local moves_per_minute=$(query_db "SELECT COUNT(*) FROM game_moves WHERE created_at > NOW() - INTERVAL '1 minute';" 2>/dev/null || echo "0")
        local db_connections=$(query_db "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$DB_NAME';" 2>/dev/null || echo "0")
        
        # Display metrics
        echo -e "${CYAN}┌─────────────────────────────────────────────────────────────┐${NC}"
        echo -e "${CYAN}│ Real-time Gaming Metrics - $(date '+%Y-%m-%d %H:%M:%S')       │${NC}"
        echo -e "${CYAN}├─────────────────────────────────────────────────────────────┤${NC}"
        printf "${CYAN}│${NC} %-25s ${GREEN}%10s${NC} ${CYAN}│${NC}\n" "Active Games:" "$active_games"
        printf "${CYAN}│${NC} %-25s ${GREEN}%10s${NC} ${CYAN}│${NC}\n" "Online Players:" "$online_players"
        printf "${CYAN}│${NC} %-25s ${GREEN}%10s${NC} ${CYAN}│${NC}\n" "Moves/Minute:" "$moves_per_minute"
        printf "${CYAN}│${NC} %-25s ${GREEN}%10s${NC} ${CYAN}│${NC}\n" "DB Connections:" "$db_connections"
        echo -e "${CYAN}└─────────────────────────────────────────────────────────────┘${NC}"
        echo
        
        # Color-coded status
        local status="NORMAL"
        local status_color="$GREEN"
        
        if [ "$active_games" -gt "$MAX_ACTIVE_GAMES" ] || [ "$online_players" -gt "$MAX_CONCURRENT_PLAYERS" ]; then
            status="HIGH LOAD"
            status_color="$YELLOW"
        fi
        
        if [ "$db_connections" -gt 100 ]; then
            status="CRITICAL"
            status_color="$RED"
        fi
        
        echo -e "Server Status: ${status_color}$status${NC}"
        echo -e "Press ${YELLOW}Ctrl+C${NC} to exit dashboard"
        echo
        
        sleep 5
        # Clear the metrics section for refresh
        echo -e "\033[10A\033[J"
    done
}

# Main function
main() {
    local action="${1:-collect}"
    
    case $action in
        collect)
            collect_gaming_metrics
            ;;
        report)
            generate_gaming_report
            ;;
        dashboard)
            show_dashboard
            ;;
        alerts)
            log GAMING "Checking gaming alerts..."
            # Run collection first to get fresh data
            collect_gaming_metrics
            ;;
        setup)
            log GAMING "Setting up gaming metrics collection..."
            mkdir -p "$REPORTS_DIR"
            mkdir -p "$(dirname "$METRICS_FILE")"
            
            # Create database tables if they don't exist (example schema)
            query_db "
            CREATE TABLE IF NOT EXISTS gaming_metrics_log (
                id SERIAL PRIMARY KEY,
                metric_name VARCHAR(100) NOT NULL,
                metric_value NUMERIC NOT NULL,
                labels JSONB,
                recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_gaming_metrics_name_time 
            ON gaming_metrics_log(metric_name, recorded_at DESC);
            " 2>/dev/null || true
            
            log SUCCESS "Gaming metrics setup completed"
            ;;
        *)
            echo "Usage: $0 {collect|report|dashboard|alerts|setup}"
            echo ""
            echo "Gaming Metrics Collection for Hokm Server"
            echo ""
            echo "Commands:"
            echo "  collect    - Collect current gaming metrics"
            echo "  report     - Generate HTML performance report"
            echo "  dashboard  - Show real-time gaming dashboard"
            echo "  alerts     - Check for gaming-specific alerts"
            echo "  setup      - Setup gaming metrics infrastructure"
            echo ""
            echo "Environment Variables:"
            echo "  DB_HOST    - Database host (default: localhost)"
            echo "  DB_PORT    - Database port (default: 5432)"
            echo "  DB_NAME    - Database name (default: hokm_game)"
            echo "  DB_USER    - Database user (default: postgres)"
            echo "  ALERT_WEBHOOK - Slack webhook URL for alerts"
            echo "  ALERT_EMAIL   - Email address for alerts"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
