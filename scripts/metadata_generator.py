"""
Metadata Generator
==================
Creates daily summary files with key metrics.

Benefits:
- Quick overview without loading full data
- Track collection health
- Small size (~1KB per day = ~30KB/month)

Created: 2026-01-16
"""

import json
from pathlib import Path
from datetime import datetime


class MetadataGenerator:
    """Generate and save metadata for each collection run."""
    
    def __init__(self, base_dir=None):
        if base_dir is None:
            self.base_dir = Path(__file__).parent.parent
        else:
            self.base_dir = Path(base_dir)
        
        self.metadata_dir = self.base_dir / 'data' / 'metadata'
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
    
    def save_metadata(self, data: dict):
        """Save metadata to JSON file."""
        date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        filepath = self.metadata_dir / f"{date_str}.json"
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_metadata(self, date_str: str):
        """Load metadata for specific date."""
        filepath = self.metadata_dir / f"{date_str}.json"
        
        if not filepath.exists():
            return None
        
        with open(filepath, 'r') as f:
            return json.load(f)
    
    def get_last_week_summary(self):
        """Get summary of last 7 days."""
        summaries = []
        
        for meta_file in sorted(self.metadata_dir.glob('*.json'))[-7:]:
            with open(meta_file, 'r') as f:
                summaries.append(json.load(f))
        
        return summaries


# Example metadata structure
EXAMPLE_METADATA = {
    "date": "2026-01-16",
    "collection_time": "15:35:00",
    "nifty": {
        "ltp": 25694.35,
        "atm": 25700,
        "strikes_collected": 82,
        "candles": 376
    },
    "banknifty": {
        "ltp": 60095.15,
        "atm": 60100,
        "strikes_collected": 82,
        "candles": 376
    },
    "total_files": 166,
    "errors": 0,
    "status": "success"
}


if __name__ == "__main__":
    # Example usage
    gen = MetadataGenerator()
    gen.save_metadata(EXAMPLE_METADATA)
    print("✅ Metadata saved!")
