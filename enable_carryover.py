#!/usr/bin/env python3
"""
One-time script to enable carryover for all categories.

This script finds the first month with transactions for each category
and enables carryover for that month. This is useful when you want to
enable carryover for all existing categories in your budget.
"""
import sys
import logging
import argparse
from pathlib import Path
import urllib3

# Disable SSL warnings when SSL verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.api.actual import ActualBudgetClient


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
        ]
    )


def main():
    """Enable carryover for all categories."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Enable carryover for all categories')
    parser.add_argument('--no-verify-ssl', action='store_true', 
                       help='Disable SSL certificate verification')
    args = parser.parse_args()
    
    logger = logging.getLogger(__name__)
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("Enable Carryover for All Categories")
    logger.info("=" * 60)
    
    # Load configuration
    try:
        config = get_config()
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        logger.error("Make sure you have created a .env file with your credentials.")
        sys.exit(1)
    
    # Override SSL verification if requested
    verify_ssl = config.actual_verify_ssl
    if args.no_verify_ssl:
        verify_ssl = False
        logger.info("SSL verification disabled via command-line flag")
    
    # Connect to Actual Budget
    with ActualBudgetClient(
        config.actual_url,
        config.actual_password,
        config.actual_file_id,
        verify_ssl
    ) as actual:
        logger.info("Connected to Actual Budget")
        
        # Get all categories
        categories = actual.get_categories()
        logger.info(f"Found {len(categories)} categories")
        
        # Enable carryover for each category
        enabled_count = 0
        skipped_count = 0
        
        for category in categories:
            cat_name = category['name']
            cat_id = category['id']
            
            logger.info(f"Processing category: {cat_name}")
            
            # Get first transaction month
            first_month = actual.get_first_transaction_month_for_category(cat_id)
            
            if first_month:
                logger.info(f"  First transaction: {first_month.strftime('%Y-%m')}")
                
                # Enable carryover
                if actual.enable_category_carryover_for_first_month(cat_id):
                    logger.info(f"  ✅ Carryover enabled for {cat_name}")
                    enabled_count += 1
                else:
                    logger.info(f"  ⏭️  Carryover already enabled or no change needed")
                    skipped_count += 1
            else:
                logger.info(f"  ⏭️  No transactions found, skipping")
                skipped_count += 1
        
        logger.info("=" * 60)
        logger.info(f"✅ Complete: {enabled_count} categories enabled, {skipped_count} skipped")
        logger.info("=" * 60)


if __name__ == '__main__':
    main()
