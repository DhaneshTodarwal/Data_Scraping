#!/bin/bash
# Scanner Start Script
cd "/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping/analysis"
export PYTHONPATH="/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping:$PYTHONPATH"
/usr/bin/python3 realtime_scanner.py --run --interval 60 --confidence 60 --probability 55
