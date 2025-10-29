import json
import os
from pathlib import Path
from dotenv import load_dotenv
import sys
import importlib.util

load_dotenv()

# Import from numbered module
spec = importlib.util.spec_from_file_location("extract_tables", "src/1_extract_tables.py")
extract_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract_module)

create_creds = extract_module.create_creds
process_pdf = extract_module.process_pdf

def test_hds_pdf():
    """Test extraction on HDS PDF"""
    pdf_path = r"c:\Users\joaop\Desktop\Content Creation stuff\HDS_Adenda2023-Homologada (1).pdf"

    if not Path(pdf_path).exists():
        print(f"ERROR: PDF not found at {pdf_path}")
        return

    print("Testing HDS PDF extraction...")
    print(f"PDF: {pdf_path}\n")

    creds = create_creds()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in .env")
        return

    tables = process_pdf(pdf_path, creds, api_key)

    print(f"\nExtracted {len(tables)} tables")
    print("\nJSON Output:")
    print(json.dumps({"tables": tables}, indent=2, ensure_ascii=False))

    # Save to file
    output_path = "hds_extraction_result.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({"tables": tables}, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {output_path}")

if __name__ == "__main__":
    test_hds_pdf()
