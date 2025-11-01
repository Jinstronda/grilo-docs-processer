"""
Check database status and fix stuck processing entries
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "hospital_tables.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("="*80)
print("AI Studio Extraction Status Report")
print("="*80 + "\n")

# Get status counts
cursor.execute("""
    SELECT aistudio_extraction_status, COUNT(*) 
    FROM contracts 
    WHERE aistudio_extraction_status IS NOT NULL 
    GROUP BY aistudio_extraction_status
""")

print("Current Status:")
for status, count in cursor.fetchall():
    print(f"  {status}: {count}")

# Count stuck processing entries
cursor.execute("""
    SELECT COUNT(*) FROM contracts 
    WHERE aistudio_extraction_status LIKE 'processing_worker_%'
      AND aistudio_json IS NULL
""")

stuck_count = cursor.fetchone()[0]
print(f"\nStuck 'processing_worker' entries (no JSON): {stuck_count}")

# Count successful
cursor.execute("SELECT COUNT(*) FROM contracts WHERE aistudio_extraction_status = 'success'")
success_count = cursor.fetchone()[0]
print(f"Successful extractions: {success_count}")

# Count failed
cursor.execute("SELECT COUNT(*) FROM contracts WHERE aistudio_extraction_status = 'failed'")
failed_count = cursor.fetchone()[0]
print(f"Failed extractions: {failed_count}")

# Fix stuck entries
if stuck_count > 0:
    print(f"\n{'='*80}")
    print(f"Fixing {stuck_count} stuck 'processing_worker' entries...")
    print("="*80 + "\n")
    
    cursor.execute("""
        UPDATE contracts 
        SET aistudio_extraction_status = 'failed'
        WHERE aistudio_extraction_status LIKE 'processing_worker_%'
          AND aistudio_json IS NULL
    """)
    
    conn.commit()
    print(f"[OK] Changed {stuck_count} stuck entries to 'failed'")

# Show final status
print(f"\n{'='*80}")
print("After Cleanup:")
print("="*80 + "\n")

cursor.execute("""
    SELECT aistudio_extraction_status, COUNT(*) 
    FROM contracts 
    WHERE aistudio_extraction_status IS NOT NULL 
    GROUP BY aistudio_extraction_status
""")

for status, count in cursor.fetchall():
    print(f"  {status}: {count}")

# Count unprocessed
cursor.execute("""
    SELECT COUNT(*) FROM contracts 
    WHERE original_pdf_url IS NOT NULL 
      AND aistudio_extraction_status IS NULL
""")

unprocessed = cursor.fetchone()[0]
print(f"\nUnprocessed (NULL status): {unprocessed}")

conn.close()

print(f"\n{'='*80}")
print("Summary:")
print("="*80)
print(f"Success: {success_count}")
print(f"Failed: {failed_count + stuck_count}")
print(f"Remaining: {unprocessed}")
print(f"Total PDFs in database: {success_count + failed_count + stuck_count + unprocessed}")

