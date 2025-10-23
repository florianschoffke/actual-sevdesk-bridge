"""Configuration management for the sync application."""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Application configuration."""
    
    def __init__(self, env_file: Optional[Path] = None):
        """
        Initialize configuration.
        
        Args:
            env_file: Path to .env file. If None, looks in current directory.
        """
        if env_file is None:
            env_file = Path.cwd() / '.env'
        
        if env_file.exists():
            load_dotenv(env_file)
        
        # SevDesk Configuration
        self.sevdesk_api_key = os.getenv('SEVDESK_API_KEY')
        if not self.sevdesk_api_key:
            raise ValueError("SEVDESK_API_KEY not set in environment")
        
        # Actual Budget Configuration
        self.actual_url = os.getenv('ACTUAL_BUDGET_URL')
        self.actual_password = os.getenv('ACTUAL_BUDGET_PASSWORD')
        self.actual_file_id = os.getenv('ACTUAL_BUDGET_FILE_ID')
        self.actual_verify_ssl = os.getenv('ACTUAL_BUDGET_VERIFY_SSL', 'true').lower() == 'true'
        
        if not all([self.actual_url, self.actual_password, self.actual_file_id]):
            raise ValueError("Actual Budget configuration incomplete")
        
        # Sync Configuration
        self.actual_account_name = os.getenv('ACTUAL_ACCOUNT_NAME', 'EGB Funds')
        self.sync_status = os.getenv('SYNC_STATUS')  # Can be None for all statuses
        if self.sync_status:
            self.sync_status = int(self.sync_status)
        
        # Transaction notes - whether to include voucher info in notes
        self.include_transaction_notes = os.getenv('INCLUDE_TRANSACTION_NOTES', 'false').lower() == 'true'
        
        # Income categories - categories that should be marked as income
        # Can be configured via INCOME_CATEGORIES env var (comma-separated)
        default_income_categories = [
            'Bar-Kollekten Missionare',
            'Bar-Kollekten',
            'Spendeneingänge Konto',
            'Spendeneingänge Missionare',
            'Sonstige Einnahmen'
        ]
        income_categories_str = os.getenv('INCOME_CATEGORIES', '')
        if income_categories_str:
            self.income_categories = [cat.strip() for cat in income_categories_str.split(',')]
        else:
            self.income_categories = default_income_categories
        
        # Sync Schedule (cron format: "minute hour day month day_of_week")
        # Default: every hour (for backwards compatibility)
        self.sync_schedule = os.getenv('SYNC_SCHEDULE', '0 * * * *')
        
        # Logging
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        
        # Email Configuration
        self.email_enabled = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
        self.email_smtp_host = os.getenv('EMAIL_SMTP_HOST', 'smtp.gmail.com')
        self.email_smtp_port = int(os.getenv('EMAIL_SMTP_PORT', '587'))
        self.email_smtp_username = os.getenv('EMAIL_SMTP_USERNAME', '')
        self.email_smtp_password = os.getenv('EMAIL_SMTP_PASSWORD', '')
        self.email_from = os.getenv('EMAIL_FROM', '')
        self.email_to = os.getenv('EMAIL_TO', '')
        self.email_use_tls = os.getenv('EMAIL_USE_TLS', 'true').lower() == 'true'
        
        # Database
        self.db_path = Path.cwd() / 'data' / 'sync_state.db'
        self.db_path.parent.mkdir(exist_ok=True)
    
    def __repr__(self) -> str:
        """String representation (without sensitive data)."""
        return (
            f"Config("
            f"sevdesk=configured, "
            f"actual_url={self.actual_url}, "
            f"actual_file={self.actual_file_id}, "
            f"default_account={self.default_voucher_account}"
            f")"
        )


# Singleton instance
_config: Optional[Config] = None


def get_config(env_file: Optional[Path] = None) -> Config:
    """
    Get the application configuration.
    
    Args:
        env_file: Path to .env file. Only used on first call.
    
    Returns:
        Config instance
    """
    global _config
    if _config is None:
        _config = Config(env_file)
    return _config
