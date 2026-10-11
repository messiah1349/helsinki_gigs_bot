from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseParser(ABC):
    """
    Abstract interface for gig parsers.
    Each parser returns a list of dictionaries with standard keys:
    {
        'artist': str,
        'gig_date': str (YYYY-MM-DD or readable date),
        'venue': str,
        'city': str,
        'ticket_cost': str (or None),
        'ticket_url': str (or None),
        'source_url': str,
        'raw_description': str (or None),
        'lineup_details': str (or None),
        'is_festival': bool
    }
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the parser or venue/aggregator."""
        pass

    @abstractmethod
    async def parse(self) -> List[Dict[str, Any]]:
        """Fetch and parse events."""
        pass
