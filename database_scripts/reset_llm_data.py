"""
Reset LLM extraction data
Clears llm_extracted_tables column to re-run extraction
"""
import sqlite3

DB_PATH = "data/hospital_tables.db"

def reset_llm_extractions():
    """Clear all LLM extraction data"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(contracts)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'llm_extracted_tables' not in columns:
        print("[INFO] llm_extracted_tables column doesn't exist yet")
        conn.close()
        return
    
    # Count current extractions
    cursor.execute("SELECT COUNT(*) FROM contracts WHERE llm_extracted_tables IS NOT NULL")
    count = cursor.fetchone()[0]
    
    print(f"\n[INFO] Found {count} contracts with LLM extractions")
    
    if count == 0:
        print("[OK] No data to clear")
        conn.close()
        return
    
    # Clear the data
    print("[INFO] Clearing llm_extracted_tables...")
    cursor.execute("UPDATE contracts SET llm_extracted_tables = NULL")
    conn.commit()
    
    print(f"[OK] Cleared {count} LLM extractions\n")
    conn.close()

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RESET LLM EXTRACTION DATA")
    print("="*80)
    reset_llm_extractions()

