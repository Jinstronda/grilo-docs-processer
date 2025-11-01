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

# ============================================================================
# CONFIGURATION
# ============================================================================

# TEST MODE - Set to True to test extraction without PDFs
TEST_MODE = False  # Change to True for quick testing

# PARALLEL PROCESSING
NUM_WORKERS = 4  # Number of parallel Chrome tabs (workers)
BATCH_SIZE = 100  # Total PDFs to process in this batch

DB_PATH = Path(__file__).parent.parent / "data" / "hospital_tables.db"
OUTPUT_DIR = Path(__file__).parent / "extractions"
USER_DATA_DIR = Path(__file__).parent / "browser_data"  # Persistent browser data for cookies
COOKIES_FILE = Path(__file__).parent / "cookies.json"  # Saved cookies for auto-login

# Google AI Studio URLs
AI_STUDIO_HOME = "https://aistudio.google.com/prompts/new_chat"
AI_STUDIO_URL = "https://aistudio.google.com/prompts/new_chat?pli=1&model=gemini-2.5-pro"

# Test prompt for quick testing
TEST_PROMPT = """Output a JSON with the following structure:
{
  "extracted_tables": [
    {
      "table_index": 0,
      "page": 1,
      "table_data": [
        {"number": "1", "squared": "1"},
        {"number": "2", "squared": "4"},
        {"number": "3", "squared": "9"}
      ]
    }
  ]
}

Generate table_data with numbers from 1 to 100 and their squares.
Return ONLY the JSON, then on a new line write: JSON EXTRACTED SUCCESSFULLY
"""

# Full extraction prompt for PDFs
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
    """Extract JSON from the page - either code blocks OR body text"""
    try:
        print("[INFO] Extracting JSON from AI response...")
        
        # SIMPLE APPROACH: Just get the entire body text and extract JSON from it
        body_text = await page.evaluate('() => document.body.innerText')
        
        print(f"[DEBUG] Body text length: {len(body_text)} characters")
        
        # Method 1: Try code blocks first (faster if available)
        result = await page.evaluate('''() => {
            const results = [];
            
            // Try all code elements
            const allCodes = document.querySelectorAll('code');
            
            for (const code of allCodes) {
                let text = code.textContent || code.innerText;
                if (text && text.includes('extracted_tables') && text.trim().length > 50) {
                    results.push(text.trim());
                }
            }
            
            return results;
        }''')
        
        if result and len(result) > 0:
            print(f"[INFO] Found {len(result)} code block(s) with JSON")
            # Use code block extraction (original logic)
            json_text = result[0]
        else:
            print("[INFO] No code blocks - extracting directly from body text...")
            
            # Method 2: Extract from body text directly
            # Find the JSON object in the text
            import re
            
            # Look for the pattern starting with { and containing extracted_tables
            # Find start of JSON (opening brace before extracted_tables)
            if 'extracted_tables' not in body_text:
                print("[ERROR] 'extracted_tables' not found in body text!")
                return None
            
            # Find position of extracted_tables
            et_pos = body_text.find('"extracted_tables"')
            if et_pos == -1:
                et_pos = body_text.find("'extracted_tables'")
            
            # Scan backwards to find the opening {
            start_pos = body_text.rfind('{', 0, et_pos)
            if start_pos == -1:
                print("[ERROR] Could not find opening brace before extracted_tables")
                return None
            
            # Now count braces forward to find the matching closing }
            brace_count = 0
            end_pos = start_pos
            
            for i in range(start_pos, len(body_text)):
                if body_text[i] == '{':
                    brace_count += 1
                elif body_text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break
            
            if brace_count != 0:
                print(f"[ERROR] Unmatched braces - brace_count: {brace_count}")
                return None
            
            json_text = body_text[start_pos:end_pos]
            print(f"[INFO] Extracted JSON from body text ({len(json_text)} characters)")
        
        # Clean and parse the JSON
        try:
            # Remove any markdown code fences
            cleaned = json_text.strip()
            if cleaned.startswith('```'):
                lines = cleaned.split('\n')
                cleaned = '\n'.join(lines[1:-1]) if len(lines) > 2 else cleaned
            
            # Remove "JSON EXTRACTED SUCCESSFULLY" marker(s) if present
            cleaned = cleaned.replace('JSON EXTRACTED SUCCESSFULLY', '').strip()
            
            # Sometimes there are multiple markers, remove all
            while 'JSON EXTRACTED SUCCESSFULLY' in cleaned:
                cleaned = cleaned.replace('JSON EXTRACTED SUCCESSFULLY', '').strip()
            
            # Remove any trailing text after the closing brace
            last_brace = cleaned.rfind('}')
            if last_brace != -1:
                cleaned = cleaned[:last_brace + 1]
            
            print(f"[DEBUG] Attempting to parse JSON ({len(cleaned)} characters)...")
            
            # Parse as JSON
            data = json.loads(cleaned)
            
            # Check if this is our extraction result
            if 'extracted_tables' in data:
                num_tables = len(data.get('extracted_tables', []))
                total_rows = sum(len(t.get('table_data', [])) for t in data.get('extracted_tables', []))
                print(f"[OK] Successfully extracted {num_tables} tables ({total_rows} total rows)!")
                return data
            else:
                print(f"[WARNING] Parsed JSON but no 'extracted_tables' key found")
                return None
                
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parse error: {e}")
            # Save the problematic JSON for debugging
            debug_file = OUTPUT_DIR / f"debug_json_parse_error.txt"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(f"Error: {e}\n\n")
                f.write(f"JSON text (first 10000 chars):\n{json_text[:10000]}")
            print(f"[ERROR] Saved problematic JSON to: {debug_file}")
            return None
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            return None
        
    except Exception as e:
        print(f"[ERROR] Failed to extract JSON from page: {e}")
        import traceback
        traceback.print_exc()
        return None

async def process_single_pdf(page, pdf_path, contract_info):
    """Process a single PDF through Google AI Studio"""
    print(f"\n{'='*80}")
    
    if TEST_MODE:
        print(f"TEST MODE: Testing JSON extraction")
        print(f"Contract ID: {contract_info['id']} (for reference)")
    else:
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
    
    # Screenshots disabled for performance
    # worker_prefix = f"w{contract_info.get('worker_id', 0)}_"
    # await page.screenshot(path=str(OUTPUT_DIR / f'{worker_prefix}step1_initial.png'))
    
    # The model should already be selected from the initial navigation
    # Just verify we're on a chat page
    print("[INFO] Verifying chat page loaded...")
    await page.wait_for_timeout(2000)
    
    # Upload PDF (skip in test mode)
    if TEST_MODE:
        print("[INFO] TEST MODE - Skipping PDF upload")
    else:
        print(f"[INFO] Uploading PDF: {pdf_path}")
    
    if not TEST_MODE:
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
        
        # Screenshots disabled for performance
        # worker_prefix = f"w{contract_info.get('worker_id', 0)}_"
        # await page.screenshot(path=str(OUTPUT_DIR / f'{worker_prefix}step2_uploaded.png'))
    
    # Try to find and fill prompt
    if TEST_MODE:
        print("[INFO] TEST MODE - Using test prompt (numbers 1-100)")
        prompt_to_use = TEST_PROMPT
    else:
        print("[INFO] Using extraction prompt for PDF tables")
        prompt_to_use = EXTRACTION_PROMPT
    
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
        await input_field.type(prompt_to_use, delay=10)
        
        if TEST_MODE:
            print("[OK] Entered test prompt")
        else:
            print("[OK] Entered extraction prompt")
        
        # Screenshots disabled for performance
        # worker_prefix = f"w{contract_info.get('worker_id', 0)}_"
        # await page.screenshot(path=str(OUTPUT_DIR / f'{worker_prefix}step3_prompt_entered.png'))
        
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
    
    # Poll the page to detect when JSON code block appears
    max_wait_time = 900  # 15 minutes in seconds
    poll_interval = 5  # Check every 5 seconds
    elapsed = 0
    response_detected = False
    
    print("[INFO] Watching for JSON code block to appear (checking every 5 seconds)...")
    
    while elapsed < max_wait_time:
        try:
            # Look for the expandable JSON code block that always appears in responses
            json_block_exists = await page.evaluate('''() => {
                // Look for button with "JSON" text and an expanded code region
                const buttons = Array.from(document.querySelectorAll('button'));
                const jsonButton = buttons.find(btn => {
                    const text = btn.textContent || '';
                    return text.includes('JSON') && btn.getAttribute('aria-expanded') !== 'false';
                });
                
                if (jsonButton) {
                    // Check if there's a code element nearby with actual content
                    const codeElements = document.querySelectorAll('code');
                    for (const code of codeElements) {
                        const text = code.textContent || '';
                        if (text.trim().length > 10 && text.includes('{')) {
                            return true;
                        }
                    }
                }
                
                // Also check for "Response ready" indicator
                const pageText = document.body.innerText || '';
                if (pageText.includes('Response ready')) {
                    return true;
                }
                
                return false;
            }''')
            
            if json_block_exists:
                print("[OK] JSON code block detected - waiting for streaming to complete...")
                
                # Wait for JSON to stop growing (streaming complete)
                print("[INFO] Monitoring JSON size to detect when streaming stops...")
                last_size = 0
                stable_count = 0
                max_stability_checks = 10  # 10 checks × 3 seconds = 30 seconds max
                
                for check in range(max_stability_checks):
                    await page.wait_for_timeout(3000)  # Check every 3 seconds
                    
                    current_size = await page.evaluate('''() => {
                        const codes = document.querySelectorAll('code');
                        let maxSize = 0;
                        codes.forEach(code => {
                            const text = code.textContent || code.innerText || '';
                            if (text.includes('extracted_tables')) {
                                maxSize = Math.max(maxSize, text.length);
                            }
                        });
                        return maxSize;
                    }''')
                    
                    if current_size == last_size and current_size > 1000:
                        stable_count += 1
                        if stable_count >= 2:  # Stable for 2 checks (6 seconds)
                            print(f"[OK] JSON stable at {current_size} characters - streaming complete!")
                            break
                    else:
                        stable_count = 0
                    
                    last_size = current_size
                    if check % 3 == 0:  # Every 9 seconds   
                        print(f"[INFO] JSON size: {current_size} chars (checking for stability...)")
                
                # Final wait to be absolutely sure
                await page.wait_for_timeout(5000)
                response_detected = True
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
    
    # Screenshots disabled for performance
    # worker_prefix = f"w{contract_info.get('worker_id', 0)}_"
    # await page.screenshot(path=str(OUTPUT_DIR / f'{worker_prefix}step4_response.png'))
    
    # Extra wait to ensure page is fully stable after streaming
    await page.wait_for_timeout(3000)
    
    # DETAILED DEBUGGING - Check what's actually on the page
    print("[DEBUG] ========== EXTRACTION DEBUG START ==========")
    
    debug_info = await page.evaluate('''() => {
        const info = {
            totalElements: {
                regions: document.querySelectorAll('region[aria-label="JSON"]').length,
                allRegions: document.querySelectorAll('[role="region"]').length,
                codeTags: document.querySelectorAll('code').length,
                buttons: document.querySelectorAll('button').length
            },
            jsonButtons: [],
            codeBlocks: [],
            bodyTextIncludes: {
                extracted_tables: document.body.innerText.includes('extracted_tables'),
                responseReady: document.body.innerText.includes('Response ready'),
                jsonExtracted: document.body.innerText.includes('JSON EXTRACTED')
            }
        };
        
        // Find JSON buttons
        const buttons = document.querySelectorAll('button');
        buttons.forEach(btn => {
            const text = btn.textContent || '';
            if (text.includes('JSON')) {
                info.jsonButtons.push({
                    text: text.trim().substring(0, 50),
                    ariaExpanded: btn.getAttribute('aria-expanded'),
                    visible: btn.offsetParent !== null
                });
            }
        });
        
        // Find code blocks with content
        const codes = document.querySelectorAll('code');
        codes.forEach((code, idx) => {
            const text = code.textContent || code.innerText || '';
            if (text.length > 50) {
                info.codeBlocks.push({
                    index: idx,
                    length: text.length,
                    hasExtractedTables: text.includes('extracted_tables'),
                    preview: text.substring(0, 100)
                });
            }
        });
        
        return info;
    }''')
    
    print(f"[DEBUG] Page elements:")
    print(f"  - Regions with aria-label='JSON': {debug_info['totalElements']['regions']}")
    print(f"  - All regions: {debug_info['totalElements']['allRegions']}")
    print(f"  - Code tags: {debug_info['totalElements']['codeTags']}")
    print(f"[DEBUG] Body text contains:")
    print(f"  - 'extracted_tables': {debug_info['bodyTextIncludes']['extracted_tables']}")
    print(f"  - 'Response ready': {debug_info['bodyTextIncludes']['responseReady']}")
    print(f"[DEBUG] JSON buttons found: {len(debug_info['jsonButtons'])}")
    for btn in debug_info['jsonButtons']:
        print(f"  - Text: '{btn['text']}', Expanded: {btn['ariaExpanded']}, Visible: {btn['visible']}")
    print(f"[DEBUG] Code blocks with content: {len(debug_info['codeBlocks'])}")
    for block in debug_info['codeBlocks'][:3]:  # Show first 3
        print(f"  - Block {block['index']}: {block['length']} chars, has extracted_tables: {block['hasExtractedTables']}")
        print(f"    Preview: {block['preview']}")
    print("[DEBUG] ========== EXTRACTION DEBUG END ==========\n")
    
    # Try to extract JSON automatically
    print("[INFO] Attempting to extract JSON from response...")
    extracted_data = await extract_json_from_page(page)
    
    if extracted_data:
        print("[OK] Successfully extracted JSON automatically!")
        return {'data': extracted_data, 'success': True}
    else:
        # Check if JSON is in body text but not in code blocks yet
        if debug_info['bodyTextIncludes']['extracted_tables']:
            print("[WARNING] JSON is in body text but not in code blocks - may still be rendering")
            print("[INFO] This should be retried on the SAME page, not a new chat")
            
            # Return a special status indicating we should retry WITHOUT starting new chat
            return {'data': None, 'success': False, 'retry_same_page': True}
        else:
            print("[ERROR] EXTRACTION FAILED - JSON not even in body text!")
            print("[ERROR] Check debug output above to see what was found")
            
            # Save page content for manual extraction
            content = await page.content()
            manual_file = OUTPUT_DIR / f"manual_extract_{contract_info['id']}.html"
            with open(manual_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[ERROR] Page content saved to: {manual_file}")
            
            # Save debug info too
            debug_file = OUTPUT_DIR / f"debug_extract_{contract_info['id']}.txt"
            with open(debug_file, 'w', encoding='utf-8') as f:
                import json as json_mod
                f.write(json_mod.dumps(debug_info, indent=2))
            print(f"[ERROR] Debug info saved to: {debug_file}")
            
            return {'data': None, 'success': False, 'retry_same_page': False}

# Removed - using math formula distribution instead

async def save_result(contract_info, extracted_data, output_dir, success=True, worker_id=0):
    """Save extraction result to file and database with status"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{contract_info['id']}_{contract_info['hospital_name'].replace(' ', '_')}_{contract_info['year']}_w{worker_id}_{timestamp}.json"
    output_path = output_dir / filename
    
    result = {
        'contract_id': contract_info['id'],
        'hospital_name': contract_info['hospital_name'],
        'year': contract_info['year'],
        'pdf_url': contract_info['pdf_url'],
        'extraction_timestamp': timestamp,
        'extraction_status': 'success' if success else 'failed',
        'data': extracted_data
    }
    
    # Save to file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Saved result to file: {output_path}")
    
    # Save to database with status
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        status = 'success' if success else 'failed'
        
        cursor.execute("""
            UPDATE contracts 
            SET aistudio_json = ?,
                aistudio_extraction_status = ?
            WHERE id = ?
        """, (
            json.dumps(extracted_data, ensure_ascii=False) if extracted_data else None,
            status,
            contract_info['id']
        ))
        
        conn.commit()
        conn.close()
        
        print(f"[OK] Saved to database - Status: {status}")
    except Exception as e:
        print(f"[WARNING] Could not save to database: {e}")
    
    return output_path

async def worker_process_pdfs(context, worker_id, assigned_pdfs):
    """Worker function - processes assigned PDFs using round-robin distribution"""
    try:
        page = await context.new_page()
        
        print(f"[Worker {worker_id}] Starting with {len(assigned_pdfs)} assigned PDFs...")
        
        # Give this page a slight delay to avoid race conditions
        await page.wait_for_timeout(worker_id * 1000)  # Stagger workers
        
        # Navigate and dismiss popups
        await page.goto(AI_STUDIO_HOME, timeout=60000)
        await page.wait_for_load_state('networkidle', timeout=60000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"[Worker {worker_id}] Failed to start: {e}")
        return []
    
    # Dismiss popups
    try:
        popup_selectors = ['button:has-text("OK, got it")', 'button:has-text("Dismiss")']
        for selector in popup_selectors:
            try:
                buttons = await page.query_selector_all(selector)
                for button in buttons:
                    if await button.is_visible():
                        await button.click()
                        await page.wait_for_timeout(500)
            except:
                pass
    except:
        pass
    
    # Click Gemini 2.5 Pro with retries
    print(f"[Worker {worker_id}] Attempting to click Gemini 2.5 Pro...")
    gemini_clicked = False
    
    for attempt in range(4):  # Up to 4 retries
        try:
            if attempt > 0:
                print(f"[Worker {worker_id}] Retry {attempt}/3 for Gemini button...")
                await page.wait_for_timeout(3000)
            
            gemini_button = page.get_by_role('button', name='Gemini 2.5 Pro Our most powerful reasoning model')
            await gemini_button.click(timeout=10000)
            await page.wait_for_load_state('networkidle', timeout=60000)
            await page.wait_for_timeout(2000)
            print(f"[Worker {worker_id}] ✓ Ready on Gemini 2.5 Pro chat")
            gemini_clicked = True
            break
        except Exception as e:
            print(f"[Worker {worker_id}] Attempt {attempt + 1}/4 failed: {e}")
    
    if not gemini_clicked:
        print(f"[Worker {worker_id}] ✗ Failed to click Gemini 2.5 Pro after 4 attempts - closing worker")
        await page.close()
        return []
    
    worker_results = []
    
    try:
        # Process each assigned PDF using round-robin distribution
        for pdf_index, contract in enumerate(assigned_pdfs, 1):
            print(f"\n[Worker {worker_id}] Processing PDF {pdf_index}/{len(assigned_pdfs)}: {contract['hospital_name']}")
            
            # Download PDF
            pdf_dir = OUTPUT_DIR / "pdfs"
            pdf_dir.mkdir(exist_ok=True)
            pdf_path = pdf_dir / f"{contract['id']}.pdf"
            
            if not pdf_path.exists():
                success = await download_pdf(contract['pdf_url'], pdf_path)
                if not success:
                    print(f"[Worker {worker_id}] Download failed - retrying in 10 seconds...")
                    await page.wait_for_timeout(10000)
                    success = await download_pdf(contract['pdf_url'], pdf_path)
                    if not success:
                        await save_result(contract, None, OUTPUT_DIR, success=False, worker_id=worker_id)
                        print(f"[Worker {worker_id}] ✗ Download failed after retry - skipping")
                        continue
            
            # Process the PDF with retry logic
            max_retries = 4  # Increased to 4 attempts
            result = None
            
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        # Check if we should retry on same page or start fresh
                        if result and result.get('retry_same_page'):
                            print(f"[Worker {worker_id}] Retry {attempt}/{max_retries-1} - JSON in body but not code blocks")
                            print(f"[Worker {worker_id}] Waiting 15 seconds for code blocks to render...")
                            await page.wait_for_timeout(15000)  # Wait for code blocks to appear
                            print(f"[Worker {worker_id}] Retrying extraction on SAME page...")
                        else:
                            print(f"[Worker {worker_id}] Retry {attempt}/{max_retries-1} - Starting fresh chat...")
                            await page.wait_for_timeout(10000)  # 10 second delay
                            
                            # Start fresh chat for retry
                            for chat_attempt in range(4):
                                try:
                                    await page.goto(AI_STUDIO_HOME, timeout=60000)
                                    await page.wait_for_load_state('networkidle', timeout=60000)
                                    await page.wait_for_timeout(2000)
                                    
                                    gemini_button = page.get_by_role('button', name='Gemini 2.5 Pro Our most powerful reasoning model')
                                    await gemini_button.click(timeout=10000)
                                    await page.wait_for_load_state('networkidle', timeout=60000)
                                    await page.wait_for_timeout(2000)
                                    print(f"[Worker {worker_id}] ✓ Retry chat ready")
                                    break
                                except Exception as e:
                                    print(f"[Worker {worker_id}] Chat setup attempt {chat_attempt + 1}/4: {e}")
                                    if chat_attempt >= 3:
                                        raise
                    
                    # Add worker_id to contract for worker-specific screenshots
                    contract['worker_id'] = worker_id
                    
                    # Process or re-extract (depending on retry type)
                    if attempt == 0 or not result or not result.get('retry_same_page'):
                        # First attempt or fresh chat - full process
                        result = await process_single_pdf(page, str(pdf_path), contract)
                    else:
                        # Same page retry - just re-extract from existing response
                        print(f"[Worker {worker_id}] Re-extracting from existing response...")
                        extracted_data = await extract_json_from_page(page)
                        if extracted_data:
                            result = {'data': extracted_data, 'success': True}
                        else:
                            result = {'data': None, 'success': False, 'retry_same_page': False}
                    
                    if result and result['success']:
                        print(f"[Worker {worker_id}] ✓ Extraction successful on attempt {attempt + 1}")
                        break  # Success - exit retry loop
                    elif attempt < max_retries - 1:
                        retry_type = "same page" if result.get('retry_same_page') else "fresh chat"
                        print(f"[Worker {worker_id}] Extraction failed on attempt {attempt + 1} - will retry ({retry_type})...")
                
                except Exception as e:
                    print(f"[Worker {worker_id}] Error on attempt {attempt + 1}/{max_retries}: {e}")
                    if attempt < max_retries - 1:
                        print(f"[Worker {worker_id}] Will retry in 10 seconds...")
            
            # Save final result after retries
            if result and result['success']:
                output_path = await save_result(contract, result['data'], OUTPUT_DIR, success=True, worker_id=worker_id)
                worker_results.append((contract['id'], True, output_path))
                print(f"[Worker {worker_id}] ✓ Success")
            else:
                await save_result(contract, None, OUTPUT_DIR, success=False, worker_id=worker_id)
                worker_results.append((contract['id'], False, None))
                print(f"[Worker {worker_id}] ✗ Failed after {max_retries} attempts")
            
            # Start new chat for next PDF (if more PDFs assigned)
            if pdf_index < len(assigned_pdfs):
                print(f"[Worker {worker_id}] Starting new chat for next assigned PDF...")
                
                for chat_attempt in range(4):  # Up to 4 retries for new chat
                    try:
                        if chat_attempt > 0:
                            print(f"[Worker {worker_id}] New chat retry {chat_attempt}/3...")
                        
                        await page.goto(AI_STUDIO_HOME, timeout=60000)
                        await page.wait_for_load_state('networkidle', timeout=60000)
                        await page.wait_for_timeout(2000)
                        
                        gemini_button = page.get_by_role('button', name='Gemini 2.5 Pro Our most powerful reasoning model')
                        await gemini_button.click(timeout=10000)
                        await page.wait_for_load_state('networkidle', timeout=60000)
                        await page.wait_for_timeout(2000)
                        print(f"[Worker {worker_id}] ✓ New chat ready")
                        break
                    except Exception as e:
                        print(f"[Worker {worker_id}] New chat attempt {chat_attempt + 1}/4 failed: {e}")
                        if chat_attempt >= 3:
                            print(f"[Worker {worker_id}] ✗ Cannot create new chat after 4 attempts - stopping worker")
                            return worker_results
    
    except Exception as e:
        print(f"[Worker {worker_id}] Worker crashed: {e}")
    
    finally:
        try:
            await page.close()
        except:
            pass
        print(f"[Worker {worker_id}] Finished - processed {len(worker_results)} PDFs")
    
    return worker_results

async def main():
    """Main parallel extraction process"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    print(f"\n{'='*80}")
    if TEST_MODE:
        print("Google AI Studio - TEST MODE")
    else:
        print("Google AI Studio Parallel Table Extraction")
        print(f"Workers: {NUM_WORKERS}")
        print(f"Batch Size: {BATCH_SIZE}")
    print(f"{'='*80}\n")
    
    # Get ALL unprocessed contracts for this batch
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, hospital_name, year, original_pdf_url
        FROM contracts 
        WHERE original_pdf_url IS NOT NULL 
          AND (aistudio_extraction_status IS NULL OR aistudio_extraction_status = 'failed')
        ORDER BY id
        LIMIT ?
    """, (BATCH_SIZE,))
    
    all_contracts = [
        {
            'id': row[0],
            'hospital_name': row[1],
            'year': row[2],
            'pdf_url': row[3]
        }
        for row in cursor.fetchall()
    ]
    conn.close()
    
    if not all_contracts:
        print("[INFO] No unprocessed contracts found!")
        return
    
    print(f"[INFO] Retrieved {len(all_contracts)} contracts for processing")
    print(f"[INFO] Using {NUM_WORKERS} parallel workers with round-robin distribution\n")
    
    # Distribute PDFs using round-robin (math formula)
    # Worker 1: PDFs 0, 4, 8, 12... (indices 0, 4, 8...)
    # Worker 2: PDFs 1, 5, 9, 13... (indices 1, 5, 9...)
    # Worker 3: PDFs 2, 6, 10, 14... (indices 2, 6, 10...)
    # Worker 4: PDFs 3, 7, 11, 15... (indices 3, 7, 11...)
    worker_assignments = [
        all_contracts[i::NUM_WORKERS]  # Pythonic round-robin slicing!
        for i in range(NUM_WORKERS)
    ]
    
    print("[INFO] Worker assignments:")
    for i, pdfs in enumerate(worker_assignments, 1):
        print(f"  Worker {i}: {len(pdfs)} PDFs")
    print()
    
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
                
                # Fix sameSite values - Playwright needs Strict/Lax/None
                for cookie in cookies:
                    same_site = cookie.get('sameSite', 'Lax')
                    
                    # Convert various formats to Playwright-compatible values
                    if same_site == 'unspecified':
                        cookie['sameSite'] = 'Lax'
                    elif same_site == 'no_restriction':
                        cookie['sameSite'] = 'None'
                    elif same_site in ['strict', 'Strict']:
                        cookie['sameSite'] = 'Strict'
                    elif same_site in ['lax', 'Lax']:
                        cookie['sameSite'] = 'Lax'
                    
                    # Convert expiration to expires
                    if 'expirationDate' in cookie:
                        cookie['expires'] = cookie.pop('expirationDate')
                    
                    # Remove fields Playwright doesn't need
                    cookie.pop('id', None)
                    cookie.pop('hostOnly', None)
                    cookie.pop('session', None)
                    cookie.pop('storeId', None)
                
                await context.add_cookies(cookies)
                print("[OK] Cookies loaded!")
            except Exception as e:
                print(f"[WARNING] Could not load cookies: {e}")
                print("[INFO] You may need to sign in manually")
        
        # Start all workers in parallel with their assigned PDFs
        print(f"[INFO] Starting {NUM_WORKERS} workers with round-robin distribution...\n")
        
        worker_tasks = [
            worker_process_pdfs(context, worker_id + 1, worker_assignments[worker_id])
            for worker_id in range(NUM_WORKERS)
        ]
        
        # Wait for all workers to complete (don't propagate exceptions)
        all_results = await asyncio.gather(*worker_tasks, return_exceptions=True)
        
        # Flatten results from all workers
        results = []
        for worker_results in all_results:
            if isinstance(worker_results, list):
                results.extend(worker_results)
            elif isinstance(worker_results, Exception):
                print(f"[ERROR] Worker failed with exception: {worker_results}")
            else:
                print(f"[WARNING] Unexpected worker result: {worker_results}")
        
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

