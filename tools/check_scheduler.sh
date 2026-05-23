#!/bin/bash
# Check Scheduler Status

echo "=========================================="
echo "Trading System Scheduler Status"
echo "=========================================="

# Check if scheduler container is running
echo ""
echo "📦 Container Status:"
docker compose ps scheduler

# Check recent logs
echo ""
echo "📋 Recent Logs (last 20 lines):"
docker compose logs --tail=20 scheduler

# Check daily snapshots in database
echo ""
echo "💾 Recent Daily Snapshots:"
docker exec trading_system_db_dev psql -U trader -d trading_system -c "
SELECT 
    date, 
    COUNT(*) as total_stocks,
    COUNT(ml_prediction_score) as with_ml_scores,
    ROUND(AVG(ml_prediction_score)::numeric, 3) as avg_ml_score,
    ROUND(AVG(ml_confidence)::numeric, 3) as avg_confidence,
    ROUND(AVG(ml_risk_score)::numeric, 3) as avg_risk_score
FROM daily_suggested_stocks
GROUP BY date
ORDER BY date DESC
LIMIT 7;
"

# Check scheduler log file
echo ""
echo "📄 Scheduler Log File:"
if [ -f "logs/scheduler.log" ]; then
    echo "Last 10 lines from logs/scheduler.log:"
    tail -n 10 logs/scheduler.log
else
    echo "⚠️  Log file not found at logs/scheduler.log"
fi

echo ""
echo "=========================================="
echo "To view live logs:"
echo "  docker compose logs -f scheduler"
echo ""
echo "To restart scheduler:"
echo "  docker compose restart scheduler"
echo "=========================================="
