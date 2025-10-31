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
COOKIES_FILE = Path(__file__).parent / "cookies.json"  # Saved cookies for auto-login

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
- After the JSON, on a new line, write exactly: JSON EXTRACTED SUCCESSFULLY
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
    """Extract JSON from code blocks in the AI response"""
    try:
        print("[INFO] Extracting JSON from AI response...")
        
        # Use JavaScript to find all code blocks and extract JSON
        result = await page.evaluate('''() => {
            const codeElements = document.querySelectorAll('code');
            const jsonBlocks = [];
            
            codeElements.forEach((code) => {
                const text = code.textContent || code.innerText;
                // Look for code blocks that contain "extracted_tables"
                if (text && text.includes('extracted_tables')) {
                    jsonBlocks.push(text.trim());
                }
            });
            
            return jsonBlocks;
        }''')
        
        if not result or len(result) == 0:
            print("[WARNING] No code blocks with 'extracted_tables' found")
            return None
        
        # Try to parse each JSON block
        for json_text in result:
            try:
                # Remove any markdown code fences
                cleaned = json_text.strip()
                if cleaned.startswith('```'):
                    lines = cleaned.split('\n')
                    cleaned = '\n'.join(lines[1:-1]) if len(lines) > 2 else cleaned
                
                # Remove "JSON EXTRACTED SUCCESSFULLY" marker if present
                cleaned = cleaned.replace('JSON EXTRACTED SUCCESSFULLY', '').strip()
                
                # Parse JSON
                data = json.loads(cleaned)
                
                if 'extracted_tables' in data:
                    num_tables = len(data.get('extracted_tables', []))
                    print(f"[OK] Successfully extracted {num_tables} tables from response!")
                    return data
                    
            except json.JSONDecodeError as e:
                print(f"[DEBUG] JSON parse error: {e}")
                continue
            except Exception as e:
                print(f"[DEBUG] Unexpected error parsing block: {e}")
                continue
        
        print("[WARNING] Found code blocks but couldn't parse valid JSON")
        return None
        
    except Exception as e:
        print(f"[ERROR] Failed to extract JSON from page: {e}")
        import traceback
        traceback.print_exc()
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
        
        # Step 1: Click the "Insert assets" button at the bottom (the plus button)
        print("[INFO] Step 1: Clicking 'Insert assets' button...")
        try:
            # Use the correct selector found via Chrome DevTools inspection
            insert_button = page.get_by_role('button', name='Insert assets such as images')
            await insert_button.click()
            print("[OK] Clicked 'Insert assets' button")
            await page.wait_for_timeout(1000)
            plus_clicked = True
        except Exception as e:
            print(f"[ERROR] Could not click Insert assets button: {e}")
            plus_clicked = False
        
        # Step 2 & 3: Click "Upload File" and handle file chooser
        if plus_clicked:
            print("[INFO] Step 2: Clicking 'Upload File' and uploading...")
            try:
                # Set up file chooser handler BEFORE clicking
                async with page.expect_file_chooser() as fc_info:
                    # Click "Upload File" which will trigger the file chooser
                    upload_menuitem = page.get_by_role('menuitem', name='Upload File')
                    await upload_menuitem.click()
                    print("[OK] Clicked 'Upload File' menu option")
                
                # Handle the file chooser that just appeared
                file_chooser = await fc_info.value
                await file_chooser.set_files(str(pdf_path))
                print("[OK] PDF uploaded successfully!")
                await page.wait_for_timeout(5000)  # Wait for upload to process
                uploaded = True
                
            except Exception as e:
                print(f"[ERROR] Upload process failed: {e}")
                
                # Fallback: try direct file input
                try:
                    file_inputs = await page.query_selector_all('input[type="file"]')
                    for file_input in file_inputs:
                        try:
                            await file_input.set_input_files(str(pdf_path))
                            print("[OK] PDF uploaded via fallback method!")
                            await page.wait_for_timeout(5000)
                            uploaded = True
                            break
                        except:
                            continue
                except Exception as e2:
                    print(f"[DEBUG] Fallback also failed: {e2}")
        
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
        
        # Click the Run button or press Ctrl+Enter automatically
        print("[INFO] Submitting prompt (trying Run button and Ctrl+Enter)...")
        try:
            # First try: Click the Run button
            run_button = page.get_by_role('button', name='Run')
            await run_button.click()
            print("[OK] Clicked 'Run' button - waiting for AI response...")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[INFO] Run button click failed, trying Ctrl+Enter: {e}")
            # Second try: Press Ctrl+Enter
            try:
                await page.keyboard.press('Control+Enter')
                print("[OK] Pressed Ctrl+Enter to submit - waiting for AI response...")
                await page.wait_for_timeout(2000)
            except Exception as e2:
                print(f"[WARNING] Ctrl+Enter also failed: {e2}")
                await wait_for_user_action(
                    page,
                    "Please click the 'Run' button or press Ctrl+Enter to submit"
                )
    else:
        print("[WARNING] Could not find input field automatically")
        await wait_for_user_action(
            page,
            "Please manually enter the extraction prompt and submit it"
        )
    
    # Wait for AI response - automatically detect completion
    print("[INFO] Waiting for AI response (will auto-detect when complete)...")
    print("[INFO] This may take several minutes for large PDFs (up to 10-15 minutes)...")
    
    # Poll the page content to detect completion
    max_wait_time = 900  # 15 minutes in seconds
    poll_interval = 5  # Check every 5 seconds
    elapsed = 0
    response_detected = False
    
    while elapsed < max_wait_time:
        try:
            # Check page text content for completion signals
            page_text = await page.evaluate('() => document.body.innerText')
            
            # Look for either signal
            if 'Response ready' in page_text or 'JSON EXTRACTED SUCCESSFULLY' in page_text:
                if 'Response ready' in page_text:
                    print("[OK] 'Response ready' signal detected!")
                else:
                    print("[OK] 'JSON EXTRACTED SUCCESSFULLY' signal detected!")
                response_detected = True
                await page.wait_for_timeout(2000)  # Give it a moment to finish rendering
                break
                
        except Exception as e:
            print(f"[DEBUG] Page check error (will retry): {e}")
        
        # Wait before next check
        await page.wait_for_timeout(poll_interval * 1000)
        elapsed += poll_interval
        
        # Show progress every minute
        if elapsed % 60 == 0:
            print(f"[INFO] Still waiting... ({elapsed // 60} minutes elapsed)")
    
    if not response_detected:
        print(f"[WARNING] Timeout after {max_wait_time // 60} minutes - falling back to manual confirmation...")
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
        
        # Load cookies for auto-login
        if COOKIES_FILE.exists():
            print("[INFO] Loading saved cookies for auto-login...")
            try:
                with open(COOKIES_FILE, 'r') as f:
                    cookies = json.load(f)
                await context.add_cookies(cookies)
                print("[OK] Cookies loaded - you should be automatically logged in!")
            except Exception as e:
                print(f"[WARNING] Could not load cookies: {e}")
                print("[INFO] You'll need to sign in manually")
        else:
            print("[INFO] No saved cookies found - you'll need to sign in")
        
        # Navigate to Google AI Studio home (same as your normal Chrome)
        print("[INFO] Navigating to Google AI Studio...")
        await page.goto(AI_STUDIO_HOME)
        
        # Check if we're logged in or need to sign in
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(2000)
        
        current_url = page.url
        if 'accounts.google.com' in current_url:
            print("[WARNING] Not logged in - cookies may have expired")
            await wait_for_user_action(
                page,
                "Please sign in to Google AI Studio, then press Enter"
            )
        else:
            print("[OK] Already logged in via cookies!")
        
        # Automatically click on Gemini 2.5 Pro
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(2000)
        
        print("[INFO] Clicking on 'Gemini 2.5 Pro' to start chat...")
        try:
            # Use the selector we discovered with Chrome DevTools
            gemini_button = page.get_by_role('button', name='Gemini 2.5 Pro Our most powerful reasoning model')
            await gemini_button.click()
            print("[OK] Clicked 'Gemini 2.5 Pro' - opening chat...")
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[WARNING] Could not auto-click Gemini 2.5 Pro: {e}")
            await wait_for_user_action(
                page,
                "Please manually click on 'Gemini 2.5 Pro' card to start a chat, then press Enter"
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
                await page.wait_for_timeout(2000)
                
                # Auto-click Gemini 2.5 Pro for next chat
                print("[INFO] Clicking on 'Gemini 2.5 Pro' for next PDF...")
                try:
                    gemini_button = page.get_by_role('button', name='Gemini 2.5 Pro Our most powerful reasoning model')
                    await gemini_button.click()
                    print("[OK] Clicked 'Gemini 2.5 Pro' - opening new chat...")
                    await page.wait_for_load_state('networkidle')
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"[WARNING] Could not auto-click Gemini 2.5 Pro: {e}")
                    await wait_for_user_action(
                        page,
                        "Please click on 'Gemini 2.5 Pro' to start a new chat, then press Enter"
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

