"""
Google AI Studio Table Extraction Pipeline
Automates PDF upload and table extraction using Google AI Studio web interface
"""
import sqlite3
import json
import os
import asyncio
from pathlib import Path
from datetime import datetime
import tempfile
import requests

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from prompt import get_extraction_prompt

DB_PATH = Path(__file__).parent.parent / "data" / "hospital_tables.db"
OUTPUT_DIR = Path(__file__).parent / "extractions"

class GoogleAIStudioExtractor:
    """Extract tables using Google AI Studio via Playwright automation"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self.output_dir = OUTPUT_DIR
        self.output_dir.mkdir(exist_ok=True)
        
    def get_contracts_to_process(self, limit=10):
        """Get contracts that need table extraction"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id, 
                hospital_name, 
                year, 
                original_pdf_url,
                raw_json
            FROM contracts 
            WHERE original_pdf_url IS NOT NULL 
            AND raw_json IS NOT NULL
            LIMIT ?
        """, (limit,))
        
        contracts = cursor.fetchall()
        conn.close()
        
        return [
            {
                'id': row[0],
                'hospital_name': row[1],
                'year': row[2],
                'pdf_url': row[3],
                'raw_json': row[4]
            }
            for row in contracts
        ]
    
    def download_pdf(self, pdf_url, contract_id):
        """Download PDF to temporary location"""
        temp_dir = Path(tempfile.gettempdir()) / "grilo_pdfs"
        temp_dir.mkdir(exist_ok=True)
        
        pdf_path = temp_dir / f"{contract_id}.pdf"
        
        # Skip if already downloaded
        if pdf_path.exists():
            print(f"[INFO] PDF already downloaded: {pdf_path}")
            return str(pdf_path)
        
        print(f"[INFO] Downloading PDF from: {pdf_url}")
        
        try:
            response = requests.get(pdf_url, timeout=30, stream=True)
            response.raise_for_status()
            
            with open(pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
            print(f"[OK] Downloaded PDF ({file_size_mb:.2f} MB): {pdf_path}")
            return str(pdf_path)
            
        except Exception as e:
            print(f"[ERROR] Failed to download PDF: {e}")
            return None
    
    def save_extraction_result(self, contract_id, hospital_name, year, extracted_data):
        """Save extraction results to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{contract_id}_{hospital_name.replace(' ', '_')}_{year}_{timestamp}.json"
        output_path = self.output_dir / filename
        
        result = {
            'contract_id': contract_id,
            'hospital_name': hospital_name,
            'year': year,
            'extraction_timestamp': timestamp,
            'extracted_tables': extracted_data
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Saved extraction to: {output_path}")
        return output_path
    
    async def process_contract(self, contract, page):
        """Process a single contract with Google AI Studio"""
        contract_id = contract['id']
        hospital_name = contract['hospital_name']
        year = contract['year']
        pdf_url = contract['pdf_url']
        
        print(f"\n{'='*80}")
        print(f"Processing Contract: {contract_id}")
        print(f"Hospital: {hospital_name} ({year})")
        print(f"{'='*80}\n")
        
        # Download PDF
        pdf_path = self.download_pdf(pdf_url, contract_id)
        if not pdf_path:
            print(f"[ERROR] Skipping contract {contract_id} - PDF download failed")
            return None
        
        # Upload PDF to Google AI Studio and extract tables
        extraction_result = await self.extract_tables_with_ai_studio(page, pdf_path, contract)
        
        if extraction_result:
            # Save results
            output_path = self.save_extraction_result(
                contract_id, 
                hospital_name, 
                year, 
                extraction_result
            )
            return output_path
        
        return None
    
    async def extract_tables_with_ai_studio(self, page, pdf_path, contract):
        """
        Use Playwright to interact with Google AI Studio
        Upload PDF and extract tables using the web interface
        """
        print(f"[INFO] Extracting tables from PDF via Google AI Studio...")
        
        try:
            # Navigate to Google AI Studio chat
            await page.goto('https://aistudio.google.com/prompts/new_chat')
            
            # Wait for page to load (might need authentication)
            await page.wait_for_load_state('networkidle', timeout=30000)
            
            # Check if we're on the sign-in page
            current_url = page.url
            if 'accounts.google.com' in current_url:
                print("[WARNING] Google authentication required!")
                print("[INFO] Please sign in to Google AI Studio manually in the browser")
                print("[INFO] Waiting for you to complete sign-in...")
                
                # Wait for user to complete sign-in and reach AI Studio
                await page.wait_for_url('**/aistudio.google.com/**', timeout=300000)  # 5 min timeout
                print("[OK] Sign-in completed!")
            
            # Now we should be on Google AI Studio
            await page.wait_for_load_state('networkidle')
            
            # Take screenshot to understand the UI
            await page.screenshot(path=str(self.output_dir / 'ai_studio_interface.png'))
            print("[OK] Screenshot saved to understand UI")
            
            # Get page snapshot to understand structure
            snapshot = await page.accessibility.snapshot()
            print("[DEBUG] Page structure captured")
            
            # Look for file upload button or attachment option
            # This will need to be adjusted based on the actual UI structure
            
            # Try to find upload/attach button
            upload_button = await page.query_selector('input[type="file"]')
            if not upload_button:
                # Try alternative selectors
                upload_button = await page.query_selector('[aria-label*="upload"]')
            
            if upload_button:
                print("[OK] Found file upload button")
                await upload_button.set_input_files(pdf_path)
                print(f"[OK] Uploaded PDF: {pdf_path}")
                
                # Wait for file to upload
                await page.wait_for_timeout(2000)
            else:
                print("[WARNING] Could not find file upload button")
                print("[INFO] Please implement manual upload steps")
            
            # Prepare prompt for table extraction
            prompt = """Please extract all tables from this PDF document in JSON format.

For each table, provide:
{
  "extracted_tables": [
    {
      "table_index": 0,
      "page": <page_number>,
      "table_data": [
        {"column1": "value1", "column2": "value2"},
        ...
      ]
    }
  ]
}

Rules:
- Use the actual column headers from the table
- Clean numeric values (remove currency symbols, convert European decimals)
- Handle merged cells appropriately
- Return ONLY valid JSON, no markdown or code fences
"""
            
            # Find prompt input field and type the prompt
            prompt_input = await page.query_selector('textarea')
            if not prompt_input:
                prompt_input = await page.query_selector('[contenteditable="true"]')
            
            if prompt_input:
                await prompt_input.fill(prompt)
                print("[OK] Entered extraction prompt")
                
                # Find and click send/submit button
                send_button = await page.query_selector('button[type="submit"]')
                if not send_button:
                    send_button = await page.query_selector('[aria-label*="send"]')
                
                if send_button:
                    await send_button.click()
                    print("[OK] Submitted prompt")
                    
                    # Wait for response
                    print("[INFO] Waiting for AI response...")
                    await page.wait_for_timeout(30000)  # Wait 30 seconds
                    
                    # Get the response
                    response_text = await page.text_content('body')
                    
                    # Try to extract JSON from response
                    # This is a placeholder - actual extraction logic will depend on UI
                    return self.parse_ai_response(response_text)
            
            print("[WARNING] Could not complete automation - manual intervention needed")
            return None
            
        except Exception as e:
            print(f"[ERROR] Google AI Studio automation failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def parse_ai_response(self, response_text):
        """Parse AI Studio response to extract JSON tables"""
        try:
            # Try to find JSON in the response
            import re
            
            # Look for JSON block
            json_match = re.search(r'\{[\s\S]*"extracted_tables"[\s\S]*\}', response_text)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
            
            print("[WARNING] Could not find JSON in AI response")
            return None
            
        except Exception as e:
            print(f"[ERROR] Failed to parse AI response: {e}")
            return None
    
    async def run(self, limit=10):
        """Main execution flow"""
        from playwright.async_api import async_playwright
        
        print(f"\n{'='*80}")
        print("Google AI Studio Table Extraction Pipeline")
        print(f"{'='*80}\n")
        
        # Get contracts to process
        contracts = self.get_contracts_to_process(limit)
        print(f"[INFO] Found {len(contracts)} contracts to process\n")
        
        if not contracts:
            print("[INFO] No contracts to process")
            return
        
        async with async_playwright() as p:
            # Launch browser with visible UI for manual authentication
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            
            results = []
            
            for i, contract in enumerate(contracts, 1):
                print(f"\n[INFO] Processing {i}/{len(contracts)}")
                result = await self.process_contract(contract, page)
                results.append(result)
                
                # Small delay between contracts
                await asyncio.sleep(2)
            
            await browser.close()
        
        # Summary
        print(f"\n{'='*80}")
        print("EXTRACTION COMPLETE")
        print(f"{'='*80}\n")
        
        successful = sum(1 for r in results if r is not None)
        print(f"Successful extractions: {successful}/{len(contracts)}")
        print(f"Output directory: {self.output_dir}")

if __name__ == "__main__":
    extractor = GoogleAIStudioExtractor()
    asyncio.run(extractor.run(limit=5))  # Start with 5 contracts

