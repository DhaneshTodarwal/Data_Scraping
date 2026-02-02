"""
Data Compression & Archival Script
===================================
Automatically compresses old strike data to save storage space.
Runs weekly via cron job.

Compression Benefits:
- Reduces storage by ~80-85%
- Preserves all data (lossless)
- Easy to extract when needed

Created: 2026-01-16
"""

import os
import tarfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import logging

# Setup
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data' / 'strikes_ohlcv'
ARCHIVE_DIR = BASE_DIR / 'archives'
LOG_DIR = BASE_DIR / 'logs'

ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'compression.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DataCompression")

# Keep last 14 days uncompressed, compress older
DAYS_TO_KEEP_UNCOMPRESSED = 14


def get_folders_to_compress():
    """Find date folders older than threshold."""
    today = datetime.now()
    threshold = today - timedelta(days=DAYS_TO_KEEP_UNCOMPRESSED)
    
    folders_to_compress = []
    
    # Scan for NIFTY and BANKNIFTY
    for symbol in ['NIFTY', 'BANKNIFTY']:
        symbol_path = DATA_DIR / symbol
        if not symbol_path.exists():
            continue
            
        # Scan years
        for year_dir in symbol_path.glob('*'):
            if not year_dir.is_dir():
                continue
                
            # Scan months
            for month_dir in year_dir.glob('*'):
                if not month_dir.is_dir():
                    continue
                    
                # Scan days
                for day_dir in month_dir.glob('*'):
                    if not day_dir.is_dir():
                        continue
                    
                    # Parse date from path
                    try:
                        # Format: NIFTY/2026/01_January/16
                        day_num = int(day_dir.name)
                        month_parts = month_dir.name.split('_')
                        month_num = int(month_parts[0])
                        year_num = int(year_dir.name)
                        
                        folder_date = datetime(year_num, month_num, day_num)
                        
                        if folder_date.date() < threshold.date():
                            folders_to_compress.append({
                                'path': day_dir,
                                'date': folder_date,
                                'symbol': symbol
                            })
                    except (ValueError, IndexError):
                        logger.warning(f"Could not parse date from: {day_dir}")
    
    return sorted(folders_to_compress, key=lambda x: x['date'])


def compress_folder(folder_info):
    """Compress a single date folder."""
    folder_path = folder_info['path']
    date = folder_info['date']
    symbol = folder_info['symbol']
    
    # Archive filename: NIFTY_2026-01-16.tar.gz
    archive_name = f"{symbol}_{date.strftime('%Y-%m-%d')}.tar.gz"
    archive_path = ARCHIVE_DIR / archive_name
    
    # Skip if already compressed
    if archive_path.exists():
        logger.info(f"  ⏭️ Already compressed: {archive_name}")
        return True
    
    try:
        # Create compressed archive
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(folder_path, arcname=folder_path.name)
        
        # Calculate sizes
        original_size = sum(f.stat().st_size for f in folder_path.rglob('*') if f.is_file())
        compressed_size = archive_path.stat().st_size
        savings = ((original_size - compressed_size) / original_size) * 100
        
        logger.info(f"  ✅ Compressed: {archive_name}")
        logger.info(f"     Original: {original_size / 1024 / 1024:.1f} MB")
        logger.info(f"     Compressed: {compressed_size / 1024 / 1024:.1f} MB")
        logger.info(f"     Savings: {savings:.1f}%")
        
        # Remove original folder
        shutil.rmtree(folder_path)
        logger.info(f"     Removed original folder")
        
        return True
        
    except Exception as e:
        logger.error(f"  ❌ Failed to compress {folder_path}: {e}")
        # Remove partial archive if created
        if archive_path.exists():
            archive_path.unlink()
        return False


def run_compression():
    """Main compression routine."""
    logger.info("="*60)
    logger.info("DATA COMPRESSION STARTED")
    logger.info("="*60)
    
    folders = get_folders_to_compress()
    
    if not folders:
        logger.info("✅ No folders to compress (all recent data)")
        return
    
    logger.info(f"Found {len(folders)} folders to compress (older than {DAYS_TO_KEEP_UNCOMPRESSED} days)")
    
    success_count = 0
    for folder_info in folders:
        if compress_folder(folder_info):
            success_count += 1
    
    logger.info("="*60)
    logger.info(f"COMPRESSION COMPLETE: {success_count}/{len(folders)} successful")
    logger.info("="*60)


def extract_archive(archive_name, output_dir=None):
    """
    Extract a compressed archive.
    
    Usage:
        python compress_data.py extract NIFTY_2026-01-16.tar.gz
    """
    archive_path = ARCHIVE_DIR / archive_name
    
    if not archive_path.exists():
        logger.error(f"Archive not found: {archive_name}")
        return False
    
    if output_dir is None:
        output_dir = DATA_DIR
    
    try:
        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(output_dir)
        logger.info(f"✅ Extracted: {archive_name} to {output_dir}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to extract {archive_name}: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'extract':
        if len(sys.argv) < 3:
            print("Usage: python compress_data.py extract <archive_name>")
            sys.exit(1)
        extract_archive(sys.argv[2])
    else:
        run_compression()
