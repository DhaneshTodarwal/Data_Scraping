import json
from pathlib import Path
from scripts.nse_scraper import NSEOptionChainScraper

def main():
    scraper = NSEOptionChainScraper()
    base_dir = Path("/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping")
    
    for symbol, filename in [("NIFTY", "nifty_raw.json"), ("BANKNIFTY", "banknifty_raw.json")]:
        file_path = base_dir / filename
        if not file_path.exists():
            print(f"File {filename} not found.")
            continue
            
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        if not raw_data.get("records"):
            print(f"Invalid data in {filename}")
            continue
            
        parsed_data = scraper.parse_option_chain(raw_data, symbol)
        pcr = scraper.calculate_pcr(parsed_data['strikes'])
        parsed_data['pcr'] = pcr
        
        saved_path = scraper.save_option_chain(parsed_data)
        print(f"Successfully processed and saved {symbol} data to {saved_path}")

if __name__ == "__main__":
    main()
