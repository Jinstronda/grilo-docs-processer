"""
Test extraction on single contract with verbose output
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2 import service_account
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from extract_tables import create_creds, download_pdf, extract_tables_from_pdf

load_dotenv()

def main():
    print("="*80)
    print("Google Document AI - Single Contract Test")
    print("="*80 + "\n")

    # Load credentials
    try:
        creds = create_creds()
        print("✓ Google credentials loaded\n")
    except Exception as e:
        print(f"✗ Failed to load credentials: {e}")
        return

    # Load CSV
    csv_path = Path(__file__).parent.parent.parent / 'data' / 'hospital_agreements.csv'
    df = pd.read_csv(csv_path)

    # Get first contract
    first_row = df.iloc[0]
    contract_id = first_row['id']
    pdf_url = first_row['original_pdf_url']

    print(f"Contract: {contract_id}")
    print(f"URL: {pdf_url}\n")

    # Download PDF
    pdf_path = download_pdf(pdf_url)
    if not pdf_path:
        return

    # Extract tables with verbose output and save intermediate files
    tables = extract_tables_from_pdf(
        pdf_path,
        creds,
        verbose=True,
        save_intermediate=True
    )

    if not tables:
        print("\nNo tables extracted")
        return

    # Create result
    result = {
        "contract_id": contract_id,
        "tables": tables
    }

    # Display
    print(f"\n{'='*80}")
    print("FINAL JSON OUTPUT:")
    print(f"{'='*80}")
    print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
    if len(json.dumps(result)) > 2000:
        print("...")
    print(f"{'='*80}\n")

    # Save
    output_path = Path(__file__).parent / 'test_output.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved to: {output_path}")

    # Cleanup
    Path(pdf_path).unlink(missing_ok=True)

    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Contract: {contract_id}")
    print(f"Tables extracted: {len(tables)}")
    for i, table in enumerate(tables):
        print(f"  Table {i+1}: {len(table['rows'])} rows, page {table['page']}")
    print(f"Method: Google Document AI (Layout Parser)")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
