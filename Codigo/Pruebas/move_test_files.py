import os
import shutil
import glob

TARGET_DIR = r"d:\Proyecto\Codigo\Pruebas"
os.makedirs(TARGET_DIR, exist_ok=True)

# 1. Search in d:/Proyecto/Codigo/Crawler
crawler_dir = r"d:\Proyecto\Codigo\Crawler"
crawler_test_files = glob.glob(os.path.join(crawler_dir, "test_*.py"))

moved_files = []

for fpath in crawler_test_files:
    fname = os.path.basename(fpath)
    dest = os.path.join(TARGET_DIR, fname)
    shutil.copy2(fpath, dest)
    os.remove(fpath)
    moved_files.append(f"Crawler/{fname}")

# 2. Search in scratch directory
scratch_dir = r"C:\Users\aleja\.gemini\antigravity\brain\a0ec713f-b4e4-4ff2-bc07-7f8151a1a42a\scratch"
if os.path.exists(scratch_dir):
    scratch_files = glob.glob(os.path.join(scratch_dir, "*test*.*")) + \
                    glob.glob(os.path.join(scratch_dir, "*report*.*")) + \
                    glob.glob(os.path.join(scratch_dir, "*analyze*.*")) + \
                    glob.glob(os.path.join(scratch_dir, "*stats*.*"))
    
    for fpath in scratch_files:
        fname = os.path.basename(fpath)
        dest = os.path.join(TARGET_DIR, fname)
        shutil.copy2(fpath, dest)
        moved_files.append(f"scratch/{fname}")

print("MIGRATION COMPLETED")
print("Moved files:", moved_files)
print("Target directory:", TARGET_DIR)
