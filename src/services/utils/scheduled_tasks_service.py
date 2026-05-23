"""
Scheduled Tasks Service

Manages background tasks and cron-like scheduling for the trading system.
Handles daily symbol refresh, data cleanup, and other maintenance tasks.
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
import schedule
from threading import Thread

logger = logging.getLogger(__name__)

try:
    from .symbol_database_service import get_symbol_database_service
    from .fyers_symbol_service import get_fyers_symbol_service
except ImportError:
    from services.symbol_database_service import get_symbol_database_service
    from services.fyers_symbol_service import get_fyers_symbol_service


class ScheduledTasksService:
    """Service to manage scheduled background tasks."""

    def __init__(self):
        self.is_running = False
        self.scheduler_thread = None
        self.task_history = []
        self.max_history = 100

    def start_scheduler(self):
        """Start the background scheduler."""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return

        logger.info("Starting scheduled tasks service")
        self.is_running = True

        # Schedule daily tasks
        self._setup_scheduled_tasks()

        # Start scheduler in background thread
        self.scheduler_thread = Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()

        logger.info("Scheduled tasks service started successfully")

    def stop_scheduler(self):
        """Stop the background scheduler."""
        if not self.is_running:
            return

        logger.info("Stopping scheduled tasks service")
        self.is_running = False

        # Clear all scheduled jobs
        schedule.clear()

        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)

        logger.info("Scheduled tasks service stopped")

    def _setup_scheduled_tasks(self):
        """Setup all scheduled tasks."""

        # Daily symbol refresh at 6:30 AM (after market close in India)
        schedule.every().day.at("06:30").do(
            self._run_with_logging,
            task_name="daily_symbol_refresh",
            task_func=self._daily_symbol_refresh
        )

        # Weekly database cleanup on Sunday at 2:00 AM
        schedule.every().sunday.at("02:00").do(
            self._run_with_logging,
            task_name="weekly_cleanup",
            task_func=self._weekly_cleanup
        )

        # Health check every hour
        schedule.every().hour.do(
            self._run_with_logging,
            task_name="health_check",
            task_func=self._health_check
        )

        logger.info("Scheduled tasks configured:")
        logger.info("  • Daily symbol refresh: 6:30 AM")
        logger.info("  • Weekly cleanup: Sunday 2:00 AM")
        logger.info("  • Health check: Every hour")

    def _run_scheduler(self):
        """Run the scheduler loop."""
        logger.info("Scheduler loop started")

        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(60)

        logger.info("Scheduler loop stopped")

    def _run_with_logging(self, task_name: str, task_func: Callable):
        """Wrapper to run tasks with proper logging and error handling."""
        start_time = datetime.utcnow()

        try:
            logger.info(f"Starting scheduled task: {task_name}")

            result = task_func()

            duration = (datetime.utcnow() - start_time).total_seconds()

            # Record task history
            task_record = {
                'task_name': task_name,
                'start_time': start_time.isoformat(),
                'duration_seconds': duration,
                'status': 'success',
                'result': result,
                'error': None
            }

            self._add_task_history(task_record)

            logger.info(f"Completed scheduled task '{task_name}' in {duration:.2f}s")

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()

            # Record failed task
            task_record = {
                'task_name': task_name,
                'start_time': start_time.isoformat(),
                'duration_seconds': duration,
                'status': 'failed',
                'result': None,
                'error': str(e)
            }

            self._add_task_history(task_record)

            logger.error(f"Failed scheduled task '{task_name}' after {duration:.2f}s: {e}")

    def _add_task_history(self, task_record: Dict[str, Any]):
        """Add task record to history with size limit."""
        self.task_history.append(task_record)

        # Keep only the most recent records
        if len(self.task_history) > self.max_history:
            self.task_history = self.task_history[-self.max_history:]

    def _daily_symbol_refresh(self) -> Dict[str, Any]:
        """Daily task to refresh symbol data from Fyers."""
        logger.info("Starting daily symbol refresh")

        try:
            # Get symbol service
            symbol_service = get_fyers_symbol_service()

            # Force refresh CSV cache from Fyers
            symbol_service.refresh_all_symbols(sync_to_database=True)

            # Get database service for statistics
            db_service = get_symbol_database_service()
            stats = db_service.get_database_stats()

            result = {
                'task': 'daily_symbol_refresh',
                'total_symbols': stats.get('total_symbols', 0),
                'nse_symbols': stats.get('nse_symbols', 0),
                'bse_symbols': stats.get('bse_symbols', 0),
                'last_updated': stats.get('last_updated', None)
            }

            logger.info(f"Daily symbol refresh completed: {result}")
            return result

        except Exception as e:
            logger.error(f"Error in daily symbol refresh: {e}")
            raise

    def _weekly_cleanup(self) -> Dict[str, Any]:
        """Weekly task to cleanup old data."""
        logger.info("Starting weekly cleanup")

        try:
            db_service = get_symbol_database_service()

            # Cleanup symbols inactive for more than 90 days
            deleted_count = db_service.cleanup_old_symbols(days_old=90)

            result = {
                'task': 'weekly_cleanup',
                'deleted_symbols': deleted_count,
                'cleanup_date': datetime.utcnow().isoformat()
            }

            logger.info(f"Weekly cleanup completed: {result}")
            return result

        except Exception as e:
            logger.error(f"Error in weekly cleanup: {e}")
            raise

    def _health_check(self) -> Dict[str, Any]:
        """Hourly health check task."""
        try:
            # Check database connectivity
            db_service = get_symbol_database_service()
            stats = db_service.get_database_stats()

            # Check symbol service
            symbol_service = get_fyers_symbol_service()

            result = {
                'task': 'health_check',
                'timestamp': datetime.utcnow().isoformat(),
                'database_connected': stats.get('total_symbols', 0) >= 0,
                'symbol_service_active': True,
                'total_symbols': stats.get('total_symbols', 0)
            }

            return result

        except Exception as e:
            logger.warning(f"Health check found issues: {e}")
            return {
                'task': 'health_check',
                'timestamp': datetime.utcnow().isoformat(),
                'database_connected': False,
                'symbol_service_active': False,
                'error': str(e)
            }

    def trigger_symbol_refresh_now(self) -> Dict[str, Any]:
        """Manually trigger symbol refresh immediately."""
        logger.info("Manual symbol refresh triggered")
        return self._run_with_logging("manual_symbol_refresh", self._daily_symbol_refresh)

    def get_task_history(self, limit: int = 20) -> list:
        """Get recent task execution history."""
        return self.task_history[-limit:] if limit else self.task_history

    def get_next_scheduled_tasks(self) -> list:
        """Get list of next scheduled tasks."""
        try:
            jobs = schedule.jobs
            next_tasks = []

            for job in jobs:
                next_run = job.next_run
                if next_run:
                    next_tasks.append({
                        'task_name': str(job.job_func).split('.')[-1] if hasattr(job.job_func, '__name__') else 'unknown',
                        'next_run': next_run.isoformat(),
                        'interval': str(job.interval),
                        'unit': job.unit
                    })

            # Sort by next run time
            next_tasks.sort(key=lambda x: x['next_run'])
            return next_tasks

        except Exception as e:
            logger.error(f"Error getting scheduled tasks: {e}")
            return []

    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status and statistics."""
        recent_tasks = self.get_task_history(limit=10)
        next_tasks = self.get_next_scheduled_tasks()

        # Calculate success rate
        success_count = len([t for t in recent_tasks if t.get('status') == 'success'])
        total_count = len(recent_tasks)
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0

        return {
            'is_running': self.is_running,
            'total_jobs_scheduled': len(schedule.jobs),
            'recent_tasks_count': total_count,
            'recent_success_rate': round(success_rate, 2),
            'next_tasks': next_tasks[:5],  # Next 5 tasks
            'last_task': recent_tasks[-1] if recent_tasks else None
        }


# Global service instance
_scheduled_tasks_service = None

def get_scheduled_tasks_service() -> ScheduledTasksService:
    """Get the global scheduled tasks service instance."""
    global _scheduled_tasks_service
    if _scheduled_tasks_service is None:
        _scheduled_tasks_service = ScheduledTasksService()
    return _scheduled_tasks_service

def start_background_scheduler():
    """Convenience function to start the background scheduler."""
    service = get_scheduled_tasks_service()
    service.start_scheduler()

def stop_background_scheduler():
    """Convenience function to stop the background scheduler."""
    service = get_scheduled_tasks_service()
    service.stop_scheduler()