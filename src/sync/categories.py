"""Category synchronization between SevDesk and Actual Budget."""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Config

from src.storage.database import Database
from src.api.sevdesk import SevDeskClient
from src.api.actual import ActualBudgetClient


def sync_categories(config: 'Config', dry_run: bool = False) -> dict:
    """
    Stage 2: Sync cost centers from SevDesk to Actual Budget categories.
    
    Categories are matched by name (case-insensitive) and linked by ID in the database.
    This allows users to manually reorganize categories in Actual Budget - the sync
    will not move them back. New categories are created in "SevDesk Categories" group.
    
    Args:
        config: Application configuration
        dry_run: If True, only show what would be synced without making changes
    
    Returns:
        Dict with sync statistics: {'synced': int, 'created': int}
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Category Synchronization")
    logger.info("=" * 60)
    
    db = Database(config.db_path)
    sevdesk = SevDeskClient(config.sevdesk_api_key)
    
    # Fetch cost centers from SevDesk
    logger.info("Fetching cost centers from SevDesk...")
    cost_centers = sevdesk.get_cost_centers()
    logger.info(f"Found {len(cost_centers)} cost centers")
    
    if dry_run:
        logger.info("DRY RUN - Would sync the following cost centers:")
        for cc in cost_centers[:10]:  # Show first 10
            logger.info(f"  - {cc.get('name')} (ID: {cc.get('id')})")
        if len(cost_centers) > 10:
            logger.info(f"  ... and {len(cost_centers) - 10} more")
        return {'synced': 0, 'created': 0}
    
    # Connect to Actual Budget
    with ActualBudgetClient(
        config.actual_url,
        config.actual_password,
        config.actual_file_id,
        config.actual_verify_ssl
    ) as actual:
        logger.info("Connected to Actual Budget")
        
        # Ensure category groups exist
        default_group = actual.get_or_create_category_group("SevDesk Categories")
        income_group = actual.get_or_create_category_group("Income")
        logger.info(f"Using groups - Expense: {default_group}, Income: {income_group}")
        
        # Get existing categories from Actual Budget
        categories = actual.get_categories()
        category_by_name = {c['name'].lower(): c for c in categories}
        logger.info(f"Found {len(categories)} existing categories in Actual Budget")
        
        # Log income categories configuration
        logger.info(f"Income categories: {', '.join(config.income_categories)}")
        
        sync_id = db.start_sync('categories')
        synced = 0
        created = 0
        
        try:
            for cc in cost_centers:
                cc_id = str(cc.get('id'))
                cc_name = cc.get('name', 'Unknown')
                
                # Check if already mapped in database (ID-based lookup!)
                existing_mapping = db.get_category_mapping(cc_id)
                if existing_mapping:
                    logger.debug(f"Cost center '{cc_name}' already mapped (ID: {cc_id})")
                    synced += 1
                    continue
                
                # Check if category exists in Actual Budget (by name, case-insensitive)
                # If it exists anywhere, use it - don't move it between groups
                existing_cat = category_by_name.get(cc_name.lower())
                if existing_cat:
                    logger.info(f"Found existing category: {cc_name} (in group {existing_cat.get('group_id', 'unknown')})")
                    
                    # Check if this should be an income category and update if needed
                    is_income_cat = cc_name in config.income_categories
                    if is_income_cat:
                        needs_update = False
                        if not existing_cat['is_income']:
                            logger.info(f"  ➡️  Setting {cc_name} as income category")
                            needs_update = True
                        if existing_cat.get('group_id') != income_group:
                            logger.info(f"  ➡️  Moving {cc_name} to Income group")
                            needs_update = True
                        
                        if needs_update:
                            from actual.database import Categories
                            from sqlalchemy import select
                            stmt = select(Categories).where(Categories.id == existing_cat['id'])
                            cat_obj = actual._actual.session.execute(stmt).scalar_one_or_none()
                            if cat_obj:
                                cat_obj.is_income = 1
                                cat_obj.cat_group = income_group  # Move to Income group (field is cat_group, not group_id)
                                actual._actual.session.flush()
                                actual._actual.commit()  # Commit the changes immediately
                    
                    # Enable carryover for this category's first month with transactions
                    logger.info(f"  🔄 Enabling carryover for {cc_name}")
                    actual.enable_category_carryover_for_first_month(existing_cat['id'])
                    
                    db.save_category_mapping(
                        sevdesk_id=cc_id,
                        actual_id=existing_cat['id'],
                        sevdesk_name=cc_name,
                        actual_name=existing_cat['name']
                    )
                    synced += 1
                    continue
                
                # Category doesn't exist - create it
                # Determine if this should be an income category
                is_income = cc_name in config.income_categories
                target_group = income_group if is_income else default_group
                
                logger.info(f"Creating new category: {cc_name} ({'income' if is_income else 'expense'}, group: {target_group})")
                category = actual.create_category(cc_name, target_group, is_income=is_income)
                db.save_category_mapping(
                    sevdesk_id=cc_id,
                    actual_id=category['id'],
                    sevdesk_name=cc_name,
                    actual_name=category['name']
                )
                created += 1
            
            # Check and extend carryover for all categories (automatic maintenance)
            logger.info("-" * 60)
            logger.info("Checking carryover settings...")
            carryover_stats = actual.check_and_extend_carryover(months_ahead=12)
            if carryover_stats['extended'] > 0:
                logger.info(f"🔄 Extended carryover for {carryover_stats['extended']} categories")
            else:
                logger.info(f"✅ Carryover already set for next 12+ months ({carryover_stats['already_ok']} categories OK)")
            
            db.complete_sync(
                sync_id,
                status='completed',
                items_processed=len(cost_centers),
                items_synced=synced
            )
            
            logger.info("=" * 60)
            logger.info(f"✅ Stage 2 Complete: {synced} categories synced, {created} created")
            logger.info("=" * 60)
            
            return {'synced': synced, 'created': created}
            
        except Exception as e:
            db.complete_sync(
                sync_id,
                status='failed',
                items_processed=len(cost_centers),
                items_synced=synced,
                error_message=str(e)
            )
            logger.error(f"Category sync failed: {e}")
            raise
