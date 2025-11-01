"""
Fix UTF-8 encoding in extracted JSON files and database
Run this AFTER batch extraction completes
"""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "hospital_tables.db"
EXTRACTIONS_DIR = Path(__file__).parent / "extractions"

print("="*80)
print("Fixing UTF-8 Encoding in Extracted Files")
print("="*80 + "\n")

# Get all successful extractions from database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
    SELECT id, aistudio_json 
    FROM contracts 
    WHERE aistudio_extraction_status = 'success'
      AND aistudio_json IS NOT NULL
""")

results = cursor.fetchall()
print(f"Found {len(results)} successful extractions in database\n")

fixed_count = 0

for contract_id, json_str in results:
    try:
        # Parse the JSON (this might have encoding issues)
        data = json.loads(json_str)
        
        # Re-save to database with explicit UTF-8 encoding
        clean_json = json.dumps(data, ensure_ascii=False, indent=2)
        
        cursor.execute("""
            UPDATE contracts 
            SET aistudio_json = ?
            WHERE id = ?
        """, (clean_json, contract_id))
        
        fixed_count += 1
        if fixed_count % 10 == 0:
            print(f"Fixed {fixed_count}/{len(results)}...")
            
    except Exception as e:
        print(f"Error fixing {contract_id}: {e}")

conn.commit()
conn.close()

print(f"\n[OK] Fixed {fixed_count} database entries with proper UTF-8 encoding")

# Also fix JSON files
print("\nFixing JSON files in extractions folder...")
json_files = list(EXTRACTIONS_DIR.glob("*.json"))
print(f"Found {len(json_files)} JSON files\n")

file_fixed = 0
for json_file in json_files:
    try:
        # Read with UTF-8
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Write back with UTF-8 and ensure_ascii=False
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        file_fixed += 1
        if file_fixed % 10 == 0:
            print(f"Fixed {file_fixed}/{len(json_files)} files...")
            
    except Exception as e:
        print(f"Error fixing {json_file.name}: {e}")

print(f"\n[OK] Fixed {file_fixed} JSON files with proper UTF-8 encoding")

print("\n" + "="*80)
print("COMPLETE")
print("="*80)
print(f"Database entries fixed: {fixed_count}")
print(f"JSON files fixed: {file_fixed}")
print("\nPortuguese characters (ç, ã, ó, €) should now display correctly!")

