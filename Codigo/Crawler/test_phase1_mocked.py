import sys
import multiprocessing as mp
from main import run_crawler

if __name__ == "__main__":
    mp.freeze_support()
    print("Running Crawler Phase 1 (Parts 2, 3) on filtered data...")
    run_crawler(run_parts=[2, 3])
