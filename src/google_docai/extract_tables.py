"""
Main table extraction script using Google Document AI
Orchestrates: API call → filter → transform → final JSON
"""
import os
import sys
import json
import requests
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2 import service_account
import pandas as pd

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from api_client import call_layout_parser
from filter_tables import filter_table_blocks, count_tables
from transform_to_json import transform_all_tables

load_dotenv()

def create_creds():
    """Create Google credentials from saved OAuth token"""
    from google.oauth2.credentials import Credentials
    from pathlib import Path

    # Load saved OAuth credentials
    creds_path = Path.home() / '.google_docai_credentials.json'

    if not creds_path.exists():
        raise FileNotFoundError(
            f"Credentials not found at {creds_path}\n"
            f"Please run: python src/google_docai/setup_auth.py"
        )

    credentials = Credentials.from_authorized_user_file(
        str(creds_path),
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )

    return credentials

def download_pdf(url, verbose=True):
    """Download PDF from URL

    Args:
        url: PDF URL
        verbose: Print progress

    Returns:
        str: Path to downloaded PDF or None
    """
    try:
        if verbose:
            print(f"Downloading PDF...")
        temp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        temp.write(r.content)
        temp.flush()
        if verbose:
            print(f"  ✓ Downloaded\n")
        return temp.name
    except Exception as e:
        print(f"  ✗ Download error: {e}\n")
        return None

def extract_tables_from_pdf(pdf_path, credentials, verbose=True, save_intermediate=False):
    """Extract tables from PDF using Document AI pipeline

    Args:
        pdf_path: Path to PDF file
        credentials: Google credentials
        verbose: Print progress
        save_intermediate: Save intermediate JSON files

    Returns:
        list: Array of extracted tables in final format
    """
    try:
        # Step 1: Call Document AI API
        if verbose:
            print("="*80)
            print("STEP 1: Calling Document AI Layout Parser")
            print("="*80 + "\n")

        api_response = call_layout_parser(pdf_path, credentials, verbose)

        if not api_response:
            print("✗ API call failed")
            return []

        if save_intermediate:
            with open('debug_api_response.json', 'w', encoding='utf-8') as f:
                json.dump(api_response, f, indent=2, ensure_ascii=False)
            if verbose:
                print(f"  Saved API response to debug_api_response.json\n")

        # Step 2: Filter to keep only tableBlocks
        if verbose:
            print("="*80)
            print("STEP 2: Filtering to extract tableBlocks")
            print("="*80 + "\n")

        filtered_response = filter_table_blocks(api_response)
        num_tables = count_tables(filtered_response)

        if verbose:
            print(f"  ✓ Found {num_tables} table(s)\n")

        if num_tables == 0:
            print("✗ No tables detected in document")
            return []

        if save_intermediate:
            with open('debug_filtered_tables.json', 'w', encoding='utf-8') as f:
                json.dump(filtered_response, f, indent=2, ensure_ascii=False)
            if verbose:
                print(f"  Saved filtered tables to debug_filtered_tables.json\n")

        # Step 3: Transform to final JSON format
        if verbose:
            print("="*80)
            print("STEP 3: Transforming to final JSON format")
            print("="*80 + "\n")

        final_tables = transform_all_tables(filtered_response)

        if verbose:
            print(f"  ✓ Transformed {len(final_tables)} table(s)")
            for i, table in enumerate(final_tables):
                print(f"    Table {i+1}: {len(table['rows'])} rows, page {table['page']}")
            print()

        return final_tables

    except Exception as e:
        print(f"\n✗ Extraction error: {e}")
        import traceback
        traceback.print_exc()
        return []

def main():
    """Test extraction on first contract"""
    print("="*80)
    print("Google Document AI - Table Extraction Test")
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

    # Extract tables
    tables = extract_tables_from_pdf(pdf_path, creds, verbose=True, save_intermediate=True)

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
    output_path = Path(__file__).parent / 'docai_output.json'
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
    print(f"Method: Google Document AI (Form Parser)")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
