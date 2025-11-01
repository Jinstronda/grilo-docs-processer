import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "hospital_tables.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Total PDFs
cursor.execute("SELECT COUNT(*) FROM contracts WHERE original_pdf_url IS NOT NULL")
total = cursor.fetchone()[0]

# Status breakdown
cursor.execute("""
    SELECT aistudio_extraction_status, COUNT(*) 
    FROM contracts 
    WHERE original_pdf_url IS NOT NULL 
    GROUP BY aistudio_extraction_status
""")

status_counts = {}
for row in cursor.fetchall():
    status = row[0] if row[0] else "pending"
    count = row[1]
    status_counts[status] = count

conn.close()

success = status_counts.get('success', 0)
failed = status_counts.get('failed', 0)
pending = status_counts.get('pending', 0)

print("=" * 60)
print("PDF EXTRACTION STATISTICS")
print("=" * 60)
print(f"\nTotal PDFs: {total}")
print(f"\nStatus Breakdown:")
print(f"  Success:  {success:3} ({success/total*100:.1f}%)")
print(f"  Failed:   {failed:3} ({failed/total*100:.1f}%)")
print(f"  Pending:  {pending:3} ({pending/total*100:.1f}%)")

if total > 0:
    success_rate = success / total * 100
    remaining = pending + failed
    print(f"\n{'='*60}")
    print(f"Success Rate:  {success_rate:.1f}%")
    print(f"Completed:     {success + failed}/{total}")
    print(f"Remaining:     {remaining}")
    
    # Estimate time remaining (assuming ~3 min per PDF with 8 workers)
    time_per_batch = 15  # minutes (100 PDFs / 8 workers * 3 min avg)
    batches_remaining = (remaining + 99) // 100  # Round up
    est_time = batches_remaining * time_per_batch
    print(f"\nEstimated time: ~{est_time} minutes ({batches_remaining} batches @ 8 workers)")

print("=" * 60)

