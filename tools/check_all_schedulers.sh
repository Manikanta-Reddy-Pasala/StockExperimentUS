#!/bin/bash
# Check All Schedulers Status

echo "=========================================="
echo "Trading System - Complete Status Check"
echo "=========================================="

# Check containers
echo ""
echo "📦 Container Status:"
echo "--------------------"
docker compose ps | grep -E "scheduler|database|trading_system"

# Check data scheduler logs
echo ""
echo "📊 Data Scheduler - Recent Activity:"
echo "------------------------------------"
docker compose logs --tail=10 data_scheduler 2>/dev/null | grep -E "✅|❌|Pipeline|Export" || echo "No recent activity"

# Check ML scheduler logs
echo ""
echo "🤖 ML Scheduler - Recent Activity:"
echo "----------------------------------"
docker compose logs --tail=10 ml_scheduler 2>/dev/null | grep -E "✅|❌|Training|Snapshot" || echo "No recent activity"

# Check database stats
echo ""
echo "💾 Database Statistics:"
echo "----------------------"
docker exec trading_system_db_dev psql -U trader -d trading_system << SQL
SELECT 
    'Stocks' as table_name,
    COUNT(*) as total_records,
    MAX(last_updated) as last_updated
FROM stocks
UNION ALL
SELECT 
    'Historical Data',
    COUNT(*),
    MAX(date)::text
FROM historical_data
UNION ALL
SELECT 
    'Technical Indicators',
    COUNT(*),
    MAX(date)::text
FROM technical_indicators
UNION ALL
SELECT 
    'Daily Snapshots',
    COUNT(*),
    MAX(date)::text
FROM daily_suggested_stocks;
SQL

# Check today's suggested stocks
echo ""
echo "🎯 Today's Suggested Stocks:"
echo "---------------------------"
docker exec trading_system_db_dev psql -U trader -d trading_system -c "
SELECT 
    COUNT(*) as total_picks,
    COUNT(ml_prediction_score) as with_ml_scores,
    ROUND(AVG(ml_prediction_score)::numeric, 3) as avg_ml_score
FROM daily_suggested_stocks
WHERE date = CURRENT_DATE;
"

# Check CSV exports
echo ""
echo "📄 Recent CSV Exports:"
echo "---------------------"
if [ -d "exports" ]; then
    ls -lht exports/*.csv 2>/dev/null | head -5 || echo "No CSV files found"
    echo ""
    echo "Total CSV files: $(ls exports/*.csv 2>/dev/null | wc -l)"
    echo "Disk usage: $(du -sh exports 2>/dev/null | cut -f1)"
else
    echo "⚠️  Exports directory not found"
fi

# Check log files
echo ""
echo "📋 Log File Sizes:"
echo "-----------------"
echo "Data Scheduler: $(du -h logs/data_scheduler.log 2>/dev/null | cut -f1 || echo 'Not found')"
echo "ML Scheduler:   $(du -h logs/scheduler.log 2>/dev/null | cut -f1 || echo 'Not found')"

# Summary
echo ""
echo "=========================================="
echo "📊 Quick Summary"
echo "=========================================="
echo ""

# Count running schedulers
RUNNING_SCHEDULERS=$(docker compose ps | grep -c "scheduler.*Up")
echo "✓ Running Schedulers: $RUNNING_SCHEDULERS/2"

# Check if data is recent
LATEST_STOCK_UPDATE=$(docker exec trading_system_db_dev psql -U trader -d trading_system -t -c "SELECT MAX(last_updated)::date FROM stocks;" 2>/dev/null | tr -d ' ')
LATEST_SNAPSHOT=$(docker exec trading_system_db_dev psql -U trader -d trading_system -t -c "SELECT MAX(date) FROM daily_suggested_stocks;" 2>/dev/null | tr -d ' ')

if [ ! -z "$LATEST_STOCK_UPDATE" ]; then
    echo "✓ Latest Stock Update: $LATEST_STOCK_UPDATE"
fi

if [ ! -z "$LATEST_SNAPSHOT" ]; then
    echo "✓ Latest ML Snapshot:  $LATEST_SNAPSHOT"
fi

echo ""
echo "=========================================="
echo "🔧 Quick Commands:"
echo "=========================================="
echo ""
echo "View live logs:"
echo "  docker compose logs -f data_scheduler"
echo "  docker compose logs -f ml_scheduler"
echo ""
echo "Restart schedulers:"
echo "  docker compose restart data_scheduler ml_scheduler"
echo ""
echo "Run manual tasks:"
echo "  python3 run_pipeline.py       # Data pipeline"
echo "  python3 train_ml_model.py     # ML training"
echo ""
echo "=========================================="
