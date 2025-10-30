"""
LLM Table Extraction - Use Gemini 2.5 Flash to parse tableBlocks
Pre-filters raw JSON to extract only tableBlocks, then sends to Gemini
Optimized for cost and unlimited output tokens
"""
import sqlite3
import json
import os
import time
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add google_docai to path
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'google_docai'))

from filter_tables import filter_table_blocks

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    print("[ERROR] google-genai not installed!")
    print("Run: pip install google-genai")
    exit(1)

load_dotenv()

# Configuration
DB_PATH = "data/hospital_tables.db"
GEMINI_MODEL = "gemini-2.5-flash"

# The extraction prompt (clear and explicit)
EXTRACTION_PROMPT = """You are a data extraction engine. Your task is to parse a JSON document containing table blocks, extract all row data, and clean it according to the rules provided.

<task>

1.  You will be given a JSON document inside the `<document_to_parse>` tag.

2.  Navigate to `documentLayout.blocks`.

3.  For each `block` in the `blocks` array that contains a `tableBlock`:

    1.  Create a new table object for the output.

    2.  Set `table_index` to be the 0-based index of that `block` within the `blocks` array.

    3.  Set `page` using the `block.pageSpan.pageStart` value.

    4.  Process all `bodyRows` in `tableBlock.bodyRows` to create the `table_data` array.

</task>

<input_schema>

The input `tableBlock` data will follow this structure:

```json
{
  "documentLayout": {
    "blocks": [
      {
        "blockId": "96",
        "pageSpan": {"pageStart": 7},
        "tableBlock": {
          "bodyRows": [
            {
              "cells": [
                {
                  "blocks": [
                    {
                      "textBlock": {
                        "text": "THE ACTUAL TEXT IS HERE"
                      }
                    }
                  ]
                }
              ]
            }
          ]
        }
      }
    ]
  }
}
```

</input_schema>

<extraction_rules>

For each cell in bodyRow.cells, extract the text and apply the following cleaning rules:

1. **Text Location**: The text value is located at `cell.blocks[0].textBlock.text`.

2. **Empty Cells**: If textBlock or text is missing, or the text is an empty string, the value must be `null`.

3. **ID-Description Splitting**:
   - This rule applies ONLY to the first column of the row.
   - If the text matches the "ID-Description" pattern (e.g., "616-Matérias de consumo"), you MUST split it into two new keys:
     - `"ItemID": "616"`
     - `"ItemDesc": "Matérias de consumo"`
   - If the text does not have a dash or a number at the start, you MUST set:
     - `"ItemID": null`
     - `"ItemDesc": (the full text of the cell)`

4. **Currency Cleaning**:
   - This rule applies to any column that contains the "€" symbol.
   - Remove the "€" symbol.
   - Remove all spaces.
   - Remove all thousand separators ('.').
   - Replace the decimal comma (',') with a period ('.').
   - Example: "12.706.784,46 €" becomes "12706784.46"

5. **Number Cleaning**:
   - This rule applies to other columns that appear to be numeric.
   - Remove all spaces.
   - Remove all thousand separators ('.').
   - Replace the decimal comma (',') with a period ('.').
   - Example: "1.234,56" becomes "1234.56"

</extraction_rules>

<output_format>

Your output MUST be a single, valid JSON object and nothing else. Do not include any explanation or markdown formatting. The output structure MUST follow this format:

```json
{
  "extracted_tables": [
    {
      "table_index": 0,
      "page": 7,
      "table_data": [
        {
          "ItemID": "616",
          "ItemDesc": "Matérias de consumo",
          "Valor Estimado 2013": "12706784.46",
          "Valor Contratualizado 2014": "14255526.49"
        },
        {
          "ItemID": null,
          "ItemDesc": "Some other row",
          "Valor Estimado 2013": "1234.56",
          "Valor Contratualizado 2014": null
        }
      ]
    }
  ]
}
```

</output_format>

<document_to_parse>

{raw_json_here}

</document_to_parse>"""

class GeminiTableExtractor:
    """Extract tables using Gemini 2.5 Flash"""
    
    def __init__(self, db_path=DB_PATH, num_workers=5):
        self.db_path = db_path
        self.num_workers = num_workers
        self.client = None
        
    def setup_client(self):
        """Setup Gemini client"""
        api_key = os.getenv('GEMINI_API_KEY')
        
        if not api_key:
            raise Exception(
                "GEMINI_API_KEY not found in environment!\n"
                "Add to .env file: GEMINI_API_KEY=your_key_here\n"
                "Get key from: https://ai.google.dev"
            )
        
        self.client = genai.Client(api_key=api_key)
        print(f"[OK] Gemini client initialized (model: {GEMINI_MODEL})\n")
    
    def add_llm_column(self):
        """Add llm_extracted_tables column if doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(contracts)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'llm_extracted_tables' not in columns:
            print("Adding llm_extracted_tables column...")
            cursor.execute("""
                ALTER TABLE contracts 
                ADD COLUMN llm_extracted_tables TEXT
            """)
            conn.commit()
            print("[OK] Column added\n")
        else:
            print("[OK] llm_extracted_tables column already exists\n")
        
        conn.close()
    
    def extract_with_llm(self, contract_id, raw_json_str, verbose=True):
        """Extract tables from raw_json using GPT-5 Mini
        
        Args:
            contract_id: Contract ID
            raw_json_str: Raw JSON string from Google Document AI
            verbose: Print progress
            
        Returns:
            dict: Extracted tables or None if failed
        """
        try:
            print("\n" + "="*80)
            print("STEP 1: FILTERING RAW JSON")
            print("="*80)
            
            # Parse raw JSON
            print(f"  Parsing raw JSON ({len(raw_json_str):,} chars)...")
            raw_json_dict = json.loads(raw_json_str)
            print(f"  [OK] Parsed successfully")
            
            # Filter to get only tableBlocks
            print(f"  Filtering to extract tableBlocks...")
            filtered_json = filter_table_blocks(raw_json_dict)
            filtered_str = json.dumps(filtered_json, ensure_ascii=False)
            
            # Show filtering results
            blocks = filtered_json.get('documentLayout', {}).get('blocks', [])
            print(f"  [OK] Filtered: {len(raw_json_str):,} → {len(filtered_str):,} chars")
            reduction = round((1 - len(filtered_str)/len(raw_json_str))*100, 1)
            print(f"  [OK] Reduction: {reduction}%")
            print(f"  [OK] Tables found: {len(blocks)}")
            
            # Show first table sample
            if blocks:
                first_table = blocks[0]
                body_rows = first_table.get('tableBlock', {}).get('bodyRows', [])
                print(f"\n  Sample - First table:")
                print(f"    blockId: {first_table.get('blockId')}")
                print(f"    page: {first_table.get('pageSpan', {}).get('pageStart')}")
                print(f"    bodyRows: {len(body_rows)}")
                if body_rows:
                    first_row = body_rows[0]
                    cells = first_row.get('cells', [])
                    print(f"    First row cells: {len(cells)}")
                    if cells:
                        first_cell_text = ""
                        for block in cells[0].get('blocks', []):
                            if 'textBlock' in block:
                                first_cell_text = block['textBlock'].get('text', '')
                                break
                        print(f"    First cell text: '{first_cell_text[:50]}'")
            
            print("\n" + "="*80)
            print("STEP 2: BUILDING PROMPT")
            print("="*80)
            
            # Build prompt with filtered JSON
            prompt = EXTRACTION_PROMPT.replace('{raw_json_here}', filtered_str)
            print(f"  Prompt size: {len(prompt):,} characters")
            print(f"  Estimated tokens: ~{len(prompt)//4:,}")
            
            print("\n" + "="*80)
            print("STEP 3: CALLING GEMINI 2.5 FLASH")
            print("="*80)
            print(f"  Model: {GEMINI_MODEL}")
            print(f"  Max output tokens: unlimited")
            print(f"  Sending request...")
            
            # Call Gemini (no token limit)
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
                # No max_output_tokens = unlimited
            )
            
            # Get response text
            result_text = None
            if hasattr(response, 'text') and response.text:
                result_text = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content and candidate.content.parts:
                    result_text = candidate.content.parts[0].text
            
            if not result_text:
                raise Exception("Empty response from Gemini")
            
            print(f"  [OK] Response received!")
            print(f"\n" + "="*80)
            print("STEP 4: PARSING RESPONSE")
            print("="*80)
            print(f"  Response length: {len(result_text):,} characters")
            
            # Check for finish reason
            if hasattr(response, 'candidates') and response.candidates:
                finish_reason = getattr(response.candidates[0], 'finish_reason', 'unknown')
                print(f"  Finish reason: {finish_reason}")
            
            print(f"\n  First 300 chars of response:")
            print(f"  {result_text[:300]}")
            print(f"\n  Last 200 chars of response:")
            print(f"  {result_text[-200:]}")
            
            # Handle thinking tags
            if '<thinking>' in result_text or '```' in result_text:
                print(f"\n  [INFO] Response contains thinking tags or markdown, extracting JSON...")
                
                # Extract JSON from response
                json_start = result_text.find('{')
                json_end = result_text.rfind('}')
                
                if json_start != -1 and json_end != -1:
                    result_text = result_text[json_start:json_end+1]
                    print(f"  [OK] Extracted JSON portion: {len(result_text):,} chars")
                else:
                    raise Exception("Could not find JSON in response")
            
            # Parse JSON
            print(f"\n  Parsing JSON...")
            result = json.loads(result_text.strip())
            print(f"  [OK] JSON parsed successfully")
            
            # Analyze result
            tables = result.get('extracted_tables', [])
            print(f"\n  Tables in result: {len(tables)}")
            
            if tables:
                total_rows = 0
                empty_tables = 0
                for i, table in enumerate(tables[:5]):  # Show first 5
                    rows = len(table.get('table_data', []))
                    total_rows += rows
                    if rows == 0:
                        empty_tables += 1
                    print(f"    Table {i}: {rows} rows (page {table.get('page', '?')})")
                
                print(f"\n  Total rows across all tables: {sum(len(t.get('table_data', [])) for t in tables)}")
                
                if empty_tables > 0:
                    print(f"  [WARNING] {empty_tables} tables have EMPTY table_data!")
                    print(f"  [WARNING] LLM may not be extracting the rows correctly")
                else:
                    print(f"  [OK] All tables have data!")
            
            if verbose:
                num_tables = len(result.get('extracted_tables', []))
                total_rows = sum(
                    len(table.get('table_data', [])) 
                    for table in result.get('extracted_tables', [])
                )
                print(f"  [OK] Extracted {num_tables} tables, {total_rows} rows")
            
            return result
            
        except Exception as e:
            if verbose:
                print(f"  [ERROR] LLM extraction failed: {e}")
                
                # Save debug info
                debug_info = {
                    'contract_id': contract_id,
                    'error': str(e),
                    'prompt_length': len(prompt) if 'prompt' in locals() else 0,
                    'raw_json_length': len(raw_json_str)
                }
                
                if 'response' in locals() and response:
                    debug_info['model'] = OPENAI_MODEL
                    debug_info['finish_reason'] = response.choices[0].finish_reason if response.choices else 'unknown'
                    if 'result_text' in locals():
                        debug_info['response_preview'] = result_text[:500]
                
                with open(f'debug_llm_error_{contract_id[:20]}.json', 'w', encoding='utf-8') as f:
                    json.dump(debug_info, f, indent=2)
                
                print(f"  Debug info saved to: debug_llm_error_{contract_id[:20]}.json")
            
            return None
    
    async def process_contract_async(self, contract_id, raw_json_str, worker_id):
        """Process one contract asynchronously"""
        
        loop = asyncio.get_event_loop()
        
        # Run blocking OpenAI call in thread pool
        result = await loop.run_in_executor(
            None,
            lambda: self.extract_with_llm(contract_id, raw_json_str, verbose=False)
        )
        
        if result:
            num_tables = len(result.get('extracted_tables', []))
            num_rows = sum(
                len(table.get('table_data', []))
                for table in result.get('extracted_tables', [])
            )
            
            # Store in database
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE contracts 
                SET llm_extracted_tables = ?
                WHERE id = ?
            """, (json.dumps(result, ensure_ascii=False), contract_id))
            conn.commit()
            conn.close()
            
            return {'status': 'success', 'num_tables': num_tables, 'num_rows': num_rows}
        else:
            return {'status': 'failed'}
    
    async def worker(self, queue, worker_id, total):
        """Worker that processes contracts from queue"""
        processed = 0
        
        while True:
            try:
                item = await queue.get()
                if item is None:  # Poison pill
                    break
                
                idx, contract_id, raw_json_str = item
                
                print(f"[Worker {worker_id}] [{idx}/{total}] {contract_id[:40]}")
                
                result = await self.process_contract_async(contract_id, raw_json_str, worker_id)
                
                if result['status'] == 'success':
                    print(f"[Worker {worker_id}] [OK] {result['num_tables']} tables, {result['num_rows']} rows")
                else:
                    print(f"[Worker {worker_id}] [FAILED]")
                
                processed += 1
                queue.task_done()
                
                # Rate limiting (OpenAI has generous limits)
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"[Worker {worker_id}] [ERROR] {e}")
                queue.task_done()
        
        print(f"[Worker {worker_id}] Processed {processed} contracts")
    
    async def run_async(self, limit=None, reprocess=False):
        """Run LLM extraction on all raw_jsons"""
        print("="*80)
        print(f"LLM TABLE EXTRACTION - {self.num_workers} WORKERS")
        print(f"Model: {OPENAI_MODEL}")
        print("="*80 + "\n")
        
        # Setup
        self.add_llm_column()
        self.setup_client()
        
        # Get contracts to process
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if reprocess:
            cursor.execute("""
                SELECT id, raw_json 
                FROM contracts 
                WHERE raw_json IS NOT NULL
                ORDER BY id
            """)
        else:
            cursor.execute("""
                SELECT id, raw_json 
                FROM contracts 
                WHERE raw_json IS NOT NULL 
                  AND llm_extracted_tables IS NULL
                ORDER BY id
            """)
        
        contracts = cursor.fetchall()
        conn.close()
        
        if limit:
            contracts = contracts[:limit]
        
        total = len(contracts)
        
        if total == 0:
            print("[OK] No contracts to process\n")
            return
        
        print(f"Processing {total} contracts with {self.num_workers} workers\n")
        print("="*80 + "\n")
        
        # Create queue
        queue = asyncio.Queue()
        
        # Add contracts to queue
        for idx, (contract_id, raw_json_str) in enumerate(contracts, 1):
            await queue.put((idx, contract_id, raw_json_str))
        
        # Add poison pills
        for _ in range(self.num_workers):
            await queue.put(None)
        
        # Start workers
        start_time = time.time()
        
        workers = [
            asyncio.create_task(self.worker(queue, i+1, total))
            for i in range(self.num_workers)
        ]
        
        # Wait for completion
        await queue.join()
        await asyncio.gather(*workers)
        
        elapsed = time.time() - start_time
        
        # Summary
        print("\n" + "="*80)
        print("LLM EXTRACTION COMPLETE")
        print("="*80)
        print(f"Time elapsed: {elapsed/60:.1f} minutes")
        print(f"Average: {elapsed/total:.1f} seconds per contract")
        print(f"Workers: {self.num_workers}")
        print("="*80)

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='LLM table extraction with Gemini 2.5 Flash')
    parser.add_argument('--limit', type=int, help='Limit number of contracts')
    parser.add_argument('--reprocess', action='store_true', help='Reprocess all')
    parser.add_argument('--workers', type=int, default=5, help='Number of workers (default: 5)')
    parser.add_argument('--test', action='store_true', help='Test with one contract')
    
    args = parser.parse_args()
    
    if args.test:
        # Test with one contract
        print("Testing Gemini 2.5 Flash extraction on one contract...\n")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, raw_json 
            FROM contracts 
            WHERE raw_json IS NOT NULL 
            LIMIT 1
        """)
        
        result = cursor.fetchone()
        if not result:
            print("[ERROR] No contracts with raw_json found!")
            return
        
        contract_id, raw_json_str = result
        conn.close()
        
        print(f"Contract: {contract_id}")
        print(f"Raw JSON size: {len(raw_json_str):,} characters\n")
        
        extractor = GeminiTableExtractor()
        extractor.setup_client()
        
        result = extractor.extract_with_llm(contract_id, raw_json_str, verbose=True)
        
        if result:
            print("\n" + "="*80)
            print("LLM EXTRACTION RESULT (first 2000 chars):")
            print("="*80)
            output_str = json.dumps(result, indent=2, ensure_ascii=False)
            print(output_str[:2000])
            if len(output_str) > 2000:
                print("\n... (truncated)")
            
            # Find next test number in samples folder
            samples_dir = Path('samples')
            samples_dir.mkdir(exist_ok=True)
            existing_tests = list(samples_dir.glob('test_*_gemini_output.json'))
            next_num = len(existing_tests) + 1
            
            # Save test output with number
            output_file = samples_dir / f'test_{next_num:03d}_gemini_output.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            # Save the filtered input that was sent to LLM
            filtered_input_file = samples_dir / f'test_{next_num:03d}_filtered_input.json'
            with open(filtered_input_file, 'w', encoding='utf-8') as f:
                filtered_data = filter_table_blocks(json.loads(raw_json_str))
                json.dump(filtered_data, f, indent=2, ensure_ascii=False)
            
            # Save contract info
            info_file = samples_dir / f'test_{next_num:03d}_info.txt'
            with open(info_file, 'w', encoding='utf-8') as f:
                f.write(f"Test Number: {next_num}\n")
                f.write(f"Contract ID: {contract_id}\n")
                f.write(f"Raw JSON size: {len(raw_json_str):,} characters\n")
                f.write(f"Filtered JSON size: {len(json.dumps(filter_table_blocks(json.loads(raw_json_str)))):,} characters\n")
                f.write(f"Model: {GEMINI_MODEL}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Tables extracted: {len(result.get('extracted_tables', []))}\n")
                total_rows = sum(len(t.get('table_data', [])) for t in result.get('extracted_tables', []))
                f.write(f"Total rows: {total_rows}\n")
            
            print(f"\n[OK] Saved test #{next_num}:")
            print(f"  Input:  {filtered_input_file}")
            print(f"  Output: {output_file}")
            print(f"  Info:   {info_file}")
    else:
        # Run full extraction
        extractor = GeminiTableExtractor(num_workers=args.workers)
        asyncio.run(extractor.run_async(
            limit=args.limit,
            reprocess=args.reprocess
        ))

if __name__ == "__main__":
    main()

