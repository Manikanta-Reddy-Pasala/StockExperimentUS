#!/usr/bin/env python3
"""
Run Data Pipeline - Called by Scheduler
Uses the same pipeline_saga as startup for consistent behavior
"""

import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.services.data.pipeline_saga import get_pipeline_saga

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pipeline.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Run the complete data pipeline."""
    try:
        logger.info("=" * 80)
        logger.info("🚀 Starting Data Pipeline (Scheduled Run)")
        logger.info("=" * 80)

        # Use the same pipeline_saga as startup
        # This ensures both use the SAME logic:
        # - Last trading day checking
        # - API response classification
        # - Retry with exponential backoff
        # - Placeholder records for holidays/weekends
        pipeline_saga = get_pipeline_saga()
        results = pipeline_saga.run_pipeline()

        if results.get('success'):
            logger.info("✅ Data pipeline completed successfully!")
            logger.info(f"⏱️  Total duration: {results.get('total_duration', 0):.1f}s")
            logger.info(f"📊 Steps completed: {len(results.get('steps_completed', []))}")
            logger.info(f"📈 Total records: {results.get('total_records_processed', 0)}")
            sys.exit(0)
        else:
            logger.error("❌ Data pipeline failed!")
            logger.error(f"Error: {results.get('error', 'Unknown error')}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Pipeline execution error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
