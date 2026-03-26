"""Configuration management for Subgeneratorr"""
import os

class Config:
    """Application configuration"""
    
    DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")
    MEDIA_PATH = os.environ.get("MEDIA_PATH", "/media")
    FILE_LIST_PATH = os.environ.get("FILE_LIST_PATH")
    LOG_PATH = os.environ.get("LOG_PATH", "/logs")
    BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "0"))
    LANGUAGE = os.environ.get("LANGUAGE", "en")
    # Transcript feature settings
    ENABLE_TRANSCRIPT = os.environ.get("ENABLE_TRANSCRIPT", "0") == "1"
    
    # Raw JSON output toggle - saves raw Deepgram API response for debugging
    SAVE_RAW_JSON = os.environ.get("SAVE_RAW_JSON", "0") == "1"
    
    # Force regeneration settings
    FORCE_REGENERATE = os.environ.get("FORCE_REGENERATE", "0") == "1"
    
    # Profanity filter settings - "off", "tag", or "remove"
    PROFANITY_FILTER = os.environ.get("PROFANITY_FILTER", "off")
    
    # Model configuration - Nova 3 only
    MODEL = "nova-3"
    
    # Nova-3 Quality Enhancement features
    NUMERALS = os.environ.get("NUMERALS", "0") == "1"
    FILLER_WORDS = os.environ.get("FILLER_WORDS", "0") == "1"
    DETECT_LANGUAGE = os.environ.get("DETECT_LANGUAGE", "0") == "1"
    MEASUREMENTS = os.environ.get("MEASUREMENTS", "0") == "1"
    
    # Cost per minute (USD) for Nova-3
    # Updated to match actual API charges (previous estimate was ~25% low)
    COST_PER_MINUTE = 0.0057
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate required configuration values.
        
        Raises:
            ValueError: If DEEPGRAM_API_KEY is not set
            
        Returns:
            bool: True if validation passes
        """
        if not cls.DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY environment variable not set")
        return True
