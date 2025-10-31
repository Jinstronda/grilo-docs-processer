"""
Interactive Google AI Studio Extractor
Uses Playwright to semi-automate the extraction process with user guidance
"""
import sqlite3
import json
import asyncio
from pathlib import Path
from datetime import datetime
import requests
from playwright.async_api import async_playwright

DB_PATH = Path(__file__).parent.parent / "data" / "hospital_tables.db"
OUTPUT_DIR = Path(__file__).parent / "extractions"
USER_DATA_DIR = Path(__file__).parent / "browser_data"  # Persistent browser data for cookies

# Google AI Studio URLs
AI_STUDIO_HOME = "https://aistudio.google.com/prompts/new_chat"
AI_STUDIO_URL = "https://aistudio.google.com/prompts/new_chat?pli=1&model=gemini-2.5-pro"

EXTRACTION_PROMPT = """Please extract all tables from this PDF document in JSON format.

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
- Clean numeric values (remove currency symbols like €, convert European decimals from 1.234,56 to 1234.56)
- Handle merged cells appropriately
- Keep values as strings to preserve precision
- Return ONLY valid JSON, no markdown or code fences
"""

async def download_pdf(pdf_url, output_path):
    """Download PDF synchronously"""
    print(f"[INFO] Downloading: {pdf_url}")
    
    try:
        response = requests.get(pdf_url, timeout=60, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"[OK] Downloaded ({size_mb:.2f} MB): {output_path}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        return False

async def wait_for_user_action(page, message, timeout=300):
    """Wait for user to complete an action"""
    print(f"\n{'='*80}")
    print(f"USER ACTION REQUIRED: {message}")
    print(f"{'='*80}\n")
    print("Press Enter in this terminal when done...")
    
    # Wait for user input in a non-blocking way
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, input)
    
    print("[OK] Continuing...")
    await page.wait_for_timeout(1000)

async def extract_json_from_page(page):
    """Try to extract JSON from the page content"""
    try:
        # Get all text content
        content = await page.content()
        
        # Try to find JSON in code blocks or pre tags
        json_elements = await page.query_selector_all('pre, code')
        
        for element in json_elements:
            text = await element.text_content()
            if 'extracted_tables' in text:
                # Try to parse
                try:
                    # Clean up markdown code fences if present
                    cleaned = text.strip()
                    if cleaned.startswith('```'):
                        lines = cleaned.split('\n')
                        cleaned = '\n'.join(lines[1:-1]) if len(lines) > 2 else cleaned
                    
                    data = json.loads(cleaned)
                    if 'extracted_tables' in data:
                        return data
                except:
                    continue
        
        # If not found in structured elements, try the whole page
        page_text = await page.evaluate('() => document.body.innerText')
        
        import re
        json_pattern = r'\{[^{}]*"extracted_tables"[^{}]*\[[^\]]*\][^{}]*\}'
        matches = re.finditer(json_pattern, page_text, re.DOTALL)
        
        for match in matches:
            try:
                data = json.loads(match.group(0))
                return data
            except:
                continue
        
        return None
        
    except Exception as e:
        print(f"[ERROR] Failed to extract JSON: {e}")
        return None

async def process_single_pdf(page, pdf_path, contract_info):
    """Process a single PDF through Google AI Studio"""
    print(f"\n{'='*80}")
    print(f"Processing: {contract_info['hospital_name']} ({contract_info['year']})")
    print(f"Contract ID: {contract_info['id']}")
    print(f"PDF: {pdf_path}")
    print(f"{'='*80}\n")
    
    # Wait for page to load fully
    await page.wait_for_load_state('networkidle')
    await page.wait_for_timeout(3000)  # Give more time for UI to render
    
    # Scroll to ensure everything is loaded
    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    await page.wait_for_timeout(1000)
    await page.evaluate('window.scrollTo(0, 0)')
    
    # Take initial screenshot
    await page.screenshot(path=str(OUTPUT_DIR / 'step1_initial.png'))
    print("[OK] Screenshot saved: step1_initial.png")
    
    # The model should already be selected from the initial navigation
    # Just verify we're on a chat page
    print("[INFO] Verifying chat page loaded...")
    await page.wait_for_timeout(2000)
    
    # Upload PDF automatically - Two-step process: Click plus button, then Upload file
    print(f"[INFO] Uploading PDF: {pdf_path}")
    try:
        # Wait for page to be fully ready
        await page.wait_for_timeout(2000)
        
        uploaded = False
        
        # Step 1: Click the plus button at the bottom
        print("[INFO] Step 1: Looking for plus (+) button at bottom...")
        plus_button_selectors = [
            'button[aria-label*="add" i]',
            'button[aria-label*="plus" i]',
            'button:has-text("+")',
            '[role="button"]:has-text("+")',
            'button mat-icon:has-text("add")',
            'button:has([data-icon="add"])',
            'button.add-button',
            # Try finding by position (bottom of page)
            'button[aria-label]:last-of-type',
        ]
        
        plus_clicked = False
        for selector in plus_button_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    try:
                        is_visible = await element.is_visible()
                        if is_visible:
                            # Check if it's near the bottom of the page
                            box = await element.bounding_box()
                            if box:
                                await element.click()
                                print(f"[OK] Clicked plus (+) button")
                                await page.wait_for_timeout(1000)
                                plus_clicked = True
                                break
                    except:
                        continue
                
                if plus_clicked:
                    break
            except:
                continue
        
        if not plus_clicked:
            print("[WARNING] Could not find plus button, trying direct upload...")
        
        # Step 2: Click "Upload file" from the menu
        if plus_clicked:
            print("[INFO] Step 2: Looking for 'Upload file' option...")
            upload_option_selectors = [
                'text="Upload file"',
                ':text("Upload file")',
                'button:has-text("Upload file")',
                '[role="menuitem"]:has-text("Upload")',
                '[role="option"]:has-text("Upload")',
                'div:has-text("Upload file")',
                '[aria-label*="upload file" i]',
            ]
            
            for selector in upload_option_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible:
                            await element.click()
                            print(f"[OK] Clicked 'Upload file' option")
                            await page.wait_for_timeout(1000)
                            break
                except:
                    continue
        
        # Step 3: Now find and use the file input
        print("[INFO] Step 3: Uploading file...")
        await page.wait_for_timeout(500)
        
        file_inputs = await page.query_selector_all('input[type="file"]')
        for file_input in file_inputs:
            try:
                await file_input.set_input_files(str(pdf_path))
                print("[OK] PDF uploaded successfully!")
                await page.wait_for_timeout(5000)  # Wait longer for upload to process
                uploaded = True
                break
            except Exception as e:
                print(f"[DEBUG] File input failed: {e}")
                continue
        
        if not uploaded:
            print("[ERROR] Could not upload file automatically")
            await wait_for_user_action(
                page,
                f"Please manually upload the PDF file:\n  {pdf_path}\n\n1. Click the plus (+) button at the bottom\n2. Click 'Upload file'\n3. Select the PDF\n\nThen press Enter"
            )
    except Exception as e:
        print(f"[ERROR] Upload process failed: {e}")
        import traceback
        traceback.print_exc()
        await wait_for_user_action(
            page,
            f"Please manually upload the PDF file:\n  {pdf_path}\n\nPress Enter when uploaded"
        )
    
    # Take screenshot after upload
    await page.screenshot(path=str(OUTPUT_DIR / 'step2_uploaded.png'))
    print("[OK] Screenshot saved: step2_uploaded.png")
    
    # Try to find and fill prompt
    print("[INFO] Looking for prompt input field...")
    
    # Try multiple selectors
    input_field = None
    selectors = [
        'textarea[placeholder*="prompt" i]',
        'textarea[placeholder*="message" i]',
        'textarea',
        '[contenteditable="true"]',
        'input[type="text"]'
    ]
    
    for selector in selectors:
        try:
            input_field = await page.query_selector(selector)
            if input_field:
                is_visible = await input_field.is_visible()
                if is_visible:
                    print(f"[OK] Found input field with selector: {selector}")
                    break
        except:
            continue
    
    if input_field:
        # Clear and type prompt
        await input_field.click()
        await input_field.fill('')
        await input_field.type(EXTRACTION_PROMPT, delay=10)
        print("[OK] Entered extraction prompt")
        
        # Take screenshot
        await page.screenshot(path=str(OUTPUT_DIR / 'step3_prompt_entered.png'))
        print("[OK] Screenshot saved: step3_prompt_entered.png")
        
        # Wait for user to send
        await wait_for_user_action(
            page,
            "Please review the prompt and click Send/Submit button"
        )
    else:
        print("[WARNING] Could not find input field automatically")
        await wait_for_user_action(
            page,
            "Please manually enter the extraction prompt and submit it"
        )
    
    # Wait for AI response
    print("[INFO] Waiting for AI response...")
    await wait_for_user_action(
        page,
        "Wait for the AI to generate the response, then press Enter"
    )
    
    # Take screenshot of response
    await page.screenshot(path=str(OUTPUT_DIR / 'step4_response.png'))
    print("[OK] Screenshot saved: step4_response.png")
    
    # Try to extract JSON automatically
    print("[INFO] Attempting to extract JSON from response...")
    extracted_data = await extract_json_from_page(page)
    
    if extracted_data:
        print("[OK] Successfully extracted JSON automatically!")
        return extracted_data
    else:
        print("[WARNING] Could not extract JSON automatically")
        
        # Save page content for manual extraction
        content = await page.content()
        manual_file = OUTPUT_DIR / f"manual_extract_{contract_info['id']}.html"
        with open(manual_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[INFO] Page content saved to: {manual_file}")
        
        # Ask user to copy JSON
        print("\n" + "="*80)
        print("Please copy the JSON response from the browser and paste it into:")
        json_file = OUTPUT_DIR / f"manual_{contract_info['id']}.json"
        print(f"  {json_file}")
        print("="*80 + "\n")
        
        return None

async def save_result(contract_info, extracted_data, output_dir):
    """Save extraction result to file and database"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{contract_info['id']}_{contract_info['hospital_name'].replace(' ', '_')}_{contract_info['year']}_{timestamp}.json"
    output_path = output_dir / filename
    
    result = {
        'contract_id': contract_info['id'],
        'hospital_name': contract_info['hospital_name'],
        'year': contract_info['year'],
        'pdf_url': contract_info['pdf_url'],
        'extraction_timestamp': timestamp,
        'data': extracted_data
    }
    
    # Save to file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Saved result to file: {output_path}")
    
    # Save to database
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE contracts 
            SET aistudio_json = ?
            WHERE id = ?
        """, (json.dumps(extracted_data, ensure_ascii=False), contract_info['id']))
        
        conn.commit()
        conn.close()
        
        print(f"[OK] Saved result to database (aistudio_json column)")
    except Exception as e:
        print(f"[WARNING] Could not save to database: {e}")
    
    return output_path

async def main():
    """Main interactive extraction process"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    print(f"\n{'='*80}")
    print("Google AI Studio Interactive Table Extraction")
    print(f"{'='*80}\n")
    
    # Get contracts from database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, hospital_name, year, original_pdf_url
        FROM contracts 
        WHERE original_pdf_url IS NOT NULL
        LIMIT 2
    """)
    
    contracts = [
        {
            'id': row[0],
            'hospital_name': row[1],
            'year': row[2],
            'pdf_url': row[3]
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    
    if not contracts:
        print("[ERROR] No contracts found")
        return
    
    print(f"[INFO] Found {len(contracts)} contracts to process\n")
    
    # Download PDFs first
    pdf_dir = OUTPUT_DIR / "pdfs"
    pdf_dir.mkdir(exist_ok=True)
    
    pdf_paths = []
    for contract in contracts:
        pdf_path = pdf_dir / f"{contract['id']}.pdf"
        
        if not pdf_path.exists():
            success = await download_pdf(contract['pdf_url'], pdf_path)
            if not success:
                print(f"[ERROR] Skipping {contract['id']}")
                continue
        else:
            print(f"[INFO] PDF already exists: {pdf_path}")
        
        pdf_paths.append((contract, pdf_path))
    
    if not pdf_paths:
        print("[ERROR] No PDFs available")
        return
    
    print(f"\n[INFO] Successfully prepared {len(pdf_paths)} PDFs\n")
    
    # Launch browser - Use Chrome (easier for Google sign-in)
    async with async_playwright() as p:
        # Use Chrome channel for better Google authentication
        try:
            browser = await p.chromium.launch(
                headless=False,
                channel="chrome",  # Use installed Google Chrome
                args=['--disable-blink-features=AutomationControlled']
            )
            print("[INFO] Launched Google Chrome")
        except Exception as e:
            print(f"[WARNING] Could not launch Chrome: {e}")
            print("[INFO] Using Chromium instead")
            browser = await p.chromium.launch(headless=False)
        
        context = await browser.new_context(
            viewport={'width': 1100, 'height': 700},
            screen={'width': 1100, 'height': 700}
        )
        page = await context.new_page()
        
        # Set window size - smaller and more compact
        await page.set_viewport_size({'width': 1100, 'height': 700})
        
        # Navigate to Google AI Studio home (same as your normal Chrome)
        print("[INFO] Navigating to Google AI Studio...")
        await page.goto(AI_STUDIO_HOME)
        
        # Wait for user to sign in if needed
        await wait_for_user_action(
            page,
            "Please sign in to Google AI Studio if prompted, then press Enter"
        )
        
        # Wait for user to click on Gemini 2.5 Pro
        await page.wait_for_load_state('networkidle')
        await wait_for_user_action(
            page,
            "Please click on 'Gemini 2.5 Pro' card to start a chat, then press Enter"
        )
        
        # Process each PDF
        results = []
        for i, (contract, pdf_path) in enumerate(pdf_paths, 1):
            print(f"\n{'#'*80}")
            print(f"PDF {i}/{len(pdf_paths)}")
            print(f"{'#'*80}\n")
            
            extracted_data = await process_single_pdf(page, pdf_path, contract)
            
            if extracted_data:
                output_path = await save_result(contract, extracted_data, OUTPUT_DIR)
                results.append((contract['id'], True, output_path))
            else:
                results.append((contract['id'], False, None))
            
            # Ask if user wants to continue
            if i < len(pdf_paths):
                print("\n" + "="*80)
                choice = input("Continue to next PDF? (y/n): ").strip().lower()
                if choice != 'y':
                    print("[INFO] Stopping as requested")
                    break
                
                # Start new chat for next PDF
                print("[INFO] Starting new chat...")
                await page.goto(AI_STUDIO_HOME)
                await page.wait_for_load_state('networkidle')
                await wait_for_user_action(
                    page,
                    "Please click on 'Gemini 2.5 Pro' again to start a new chat, then press Enter"
                )
        
        # Close browser
        await browser.close()
    
    # Summary
    print(f"\n{'='*80}")
    print("EXTRACTION SUMMARY")
    print(f"{'='*80}\n")
    
    for contract_id, success, path in results:
        status = "✓ SUCCESS" if success else "✗ MANUAL"
        print(f"{status} - Contract {contract_id}: {path or 'Manual extraction required'}")
    
    successful = sum(1 for _, success, _ in results if success)
    print(f"\nTotal: {successful}/{len(results)} successful automatic extractions")
    print(f"Output directory: {OUTPUT_DIR}\n")

if __name__ == "__main__":
    asyncio.run(main())

