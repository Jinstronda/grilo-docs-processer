"""
Export a single random LLM-extracted table to a numbered folder
Creates: samples/export_N/ containing:
  - contract.pdf (Downloaded PDF if possible)
  - pdf_link.txt (PDF URL for reference)
  - raw_json.json (Google Document AI output)
  - llm_extraction.json (Gemini formatted tables)
"""
import sqlite3
import json
import os
from pathlib import Path
import random

# Try to import download libraries
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    try:
        import urllib.request
        import urllib.error
        HAS_URLLIB = True
    except ImportError:
        HAS_URLLIB = False

DB_PATH = "data/hospital_tables.db"
OUTPUT_DIR = "samples"

def get_next_export_number():
    """Find the next export number based on existing folders"""
    samples_path = Path(OUTPUT_DIR)
    samples_path.mkdir(exist_ok=True)
    
    # Find all export_N folders
    existing = [d.name for d in samples_path.iterdir() if d.is_dir() and d.name.startswith('export_')]
    
    if not existing:
        return 1
    
    # Extract numbers and find max
    numbers = []
    for folder in existing:
        try:
            num = int(folder.replace('export_', ''))
            numbers.append(num)
        except ValueError:
            continue
    
    return max(numbers) + 1 if numbers else 1

def export_random_llm_extraction():
    """Export one random LLM-extracted table to a numbered folder"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all contracts with LLM-extracted tables
    cursor.execute("""
        SELECT 
            id, 
            hospital_name, 
            year, 
            original_pdf_url, 
            raw_json,
            llm_extracted_tables 
        FROM contracts 
        WHERE llm_extracted_tables IS NOT NULL
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("[INFO] No LLM-extracted tables found in database")
        return
    
    # Pick one random contract
    contract_id, hospital, year, pdf_url, raw_json, llm_extraction = random.choice(rows)
    
    # Get next export number
    export_num = get_next_export_number()
    export_folder = Path(OUTPUT_DIR) / f"export_{export_num}"
    export_folder.mkdir(exist_ok=True)
    
    print(f"\n{'='*80}")
    print(f"EXPORTING RANDOM LLM EXTRACTION #{export_num}")
    print(f"{'='*80}\n")
    print(f"Contract ID: {contract_id}")
    print(f"Hospital: {hospital} ({year})")
    print(f"PDF: {pdf_url}\n")
    
    # Parse JSON to get statistics
    try:
        data = json.loads(llm_extraction)
        
        # Handle both formats
        if isinstance(data, dict) and 'extracted_tables' in data:
            tables = data['extracted_tables']
        elif isinstance(data, list):
            tables = data
        else:
            tables = []
        
        num_tables = len(tables)
        total_rows = sum(len(table.get('table_data', [])) for table in tables)
        
        print(f"Tables: {num_tables}")
        print(f"Total rows: {total_rows}\n")
        
    except Exception as e:
        print(f"[WARNING] Could not parse LLM JSON: {e}\n")
        num_tables = "ERROR"
        total_rows = "ERROR"
    
    # Write PDF link for reference
    pdf_link_file = export_folder / "pdf_link.txt"
    with open(pdf_link_file, 'w', encoding='utf-8') as f:
        f.write(f"Contract ID: {contract_id}\n")
        f.write(f"Hospital: {hospital} ({year})\n")
        f.write(f"PDF URL:\n{pdf_url}\n")
    
    # Download PDF
    pdf_file = export_folder / "contract.pdf"
    print(f"Downloading PDF...")
    
    pdf_downloaded = False
    
    if HAS_REQUESTS:
        try:
            response = requests.get(pdf_url, timeout=30, stream=True)
            response.raise_for_status()
            
            with open(pdf_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            pdf_downloaded = True
            
        except Exception as e:
            print(f"[WARNING] requests download failed: {e}")
    
    elif HAS_URLLIB:
        try:
            urllib.request.urlretrieve(pdf_url, pdf_file)
            pdf_downloaded = True
            
        except Exception as e:
            print(f"[WARNING] urllib download failed: {e}")
    
    if pdf_downloaded:
        # Get file size
        file_size_mb = pdf_file.stat().st_size / (1024 * 1024)
        print(f"[OK] Downloaded PDF ({file_size_mb:.2f} MB)\n")
    else:
        if not HAS_REQUESTS and not HAS_URLLIB:
            print(f"[WARNING] No download library available")
        print(f"[INFO] PDF not downloaded. Link saved to pdf_link.txt\n")
    
    # Write raw JSON (Google Document AI output)
    raw_json_file = export_folder / "raw_json.json"
    if raw_json:
        try:
            # Parse and pretty-print
            raw_data = json.loads(raw_json)
            with open(raw_json_file, 'w', encoding='utf-8') as f:
                json.dump(raw_data, f, indent=2, ensure_ascii=False)
        except:
            # If parsing fails, write as-is
            with open(raw_json_file, 'w', encoding='utf-8') as f:
                f.write(raw_json)
    else:
        with open(raw_json_file, 'w', encoding='utf-8') as f:
            f.write("null")
    
    # Write LLM extraction (Gemini formatted tables)
    llm_file = export_folder / "llm_extraction.json"
    try:
        llm_data = json.loads(llm_extraction)
        with open(llm_file, 'w', encoding='utf-8') as f:
            json.dump(llm_data, f, indent=2, ensure_ascii=False)
    except:
        with open(llm_file, 'w', encoding='utf-8') as f:
            f.write(llm_extraction)
    
    print(f"[OK] Exported to: {export_folder}/\n")
    print("Files created:")
    if pdf_downloaded:
        print(f"  - contract.pdf        (Downloaded PDF)")
    print(f"  - pdf_link.txt        (PDF URL)")
    print(f"  - raw_json.json       (Google Document AI output)")
    print(f"  - llm_extraction.json (Gemini formatted tables)")
    print(f"\nYou can now:")
    if pdf_downloaded:
        print(f"  1. Open contract.pdf directly")
    else:
        print(f"  1. Open PDF URL from pdf_link.txt")
    print(f"  2. Compare raw_json.json (Document AI) vs llm_extraction.json (Gemini)")
    print(f"  3. Verify table accuracy\n")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    export_random_llm_extraction()

