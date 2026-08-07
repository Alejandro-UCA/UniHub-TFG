import json
import os
import sys
from config import UNIVERSIDADES_JSON, TITULACIONES_JSON, DATA_DIR, PLANES_DIR
from main import run_crawler

# Backup original data
univ_backup = os.path.join(DATA_DIR, "universidades_backup.json")
tit_backup = os.path.join(DATA_DIR, "titulaciones_universidad_backup.json")

# Clean existing planes so they are fetched again
import glob
for f in glob.glob(os.path.join(PLANES_DIR, "*.json")):
    os.remove(f)

# Load existing data
with open(UNIVERSIDADES_JSON, "r", encoding="utf-8") as f:
    universities = json.load(f)

with open(TITULACIONES_JSON, "r", encoding="utf-8") as f:
    titulaciones = json.load(f)

# Save backups
with open(univ_backup, "w", encoding="utf-8") as f:
    json.dump(universities, f, indent=2, ensure_ascii=False)

with open(tit_backup, "w", encoding="utf-8") as f:
    json.dump(titulaciones, f, indent=2, ensure_ascii=False)

# Filter for UCA (005) and CUNEF (089)
target_codes = ["005", "089"]
filtered_univs = [u for u in universities if u["codigo"] in target_codes]
filtered_tits = {k: v for k, v in titulaciones.items() if k in target_codes}

# We won't filter degrees, just fetch all for these two to ensure we get data
# for u_code, u_data in filtered_tits.items(): ...

# Write filtered data
with open(UNIVERSIDADES_JSON, "w", encoding="utf-8") as f:
    json.dump(filtered_univs, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()
    try:
        print("Running Crawler Phase 1 (Parts 1, 2, 3)...")
        run_crawler(run_parts=[1, 2, 3])
    finally:
        # Restore backups
        os.replace(univ_backup, UNIVERSIDADES_JSON)
        os.replace(tit_backup, TITULACIONES_JSON)
        print("\nBackups restored.")
