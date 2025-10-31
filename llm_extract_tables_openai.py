"""
LLM Table Extraction - Using OpenAI GPT-5
"""
print("[DEBUG] Script started...")

import sqlite3
print("[DEBUG] sqlite3 imported")
import json
print("[DEBUG] json imported")
import os
print("[DEBUG] os imported")
import time
print("[DEBUG] time imported")
import asyncio
print("[DEBUG] asyncio imported")
import sys
print("[DEBUG] sys imported")
from pathlib import Path
print("[DEBUG] pathlib imported")
from datetime import datetime
print("[DEBUG] datetime imported")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))
print("[DEBUG] Added src to path")

# Add google_docai to path (not needed anymore but keeping path for compatibility)
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'google_docai'))
print("[DEBUG] Added google_docai to path")

# No longer using filter_tables - sending raw JSON directly
# from filter_tables import filter_table_blocks

from call_llm import LLMCaller
print("[DEBUG] call_llm imported")

from prompt import get_extraction_prompt
print("[DEBUG] prompt imported")

# Configuration
DB_PATH = "data/hospital_tables.db"
OPENAI_MODEL = "gpt-5-2025-08-07"  # OpenAI GPT-5

class GPT5TableExtractor:
    """Extract tables using OpenAI GPT-5"""
    
    def __init__(self, num_workers=5):
        self.db_path = DB_PATH
        self.num_workers = num_workers
        self.llm_caller = None
    
    def setup_client(self):
        """Setup OpenAI LLM client"""
        self.llm_caller = LLMCaller(
            model=OPENAI_MODEL,
            api_key_env="OPENAI_API_KEY"
        )
        print()
    
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
        """Extract tables from raw_json using OpenAI GPT-5
        
        Args:
            contract_id: Contract ID
            raw_json_str: Raw JSON string from Google Document AI
            verbose: Print progress
            
        Returns:
            dict: Extracted tables or None if failed
        """
        try:
            if verbose:
                print("\n" + "="*80)
                print("STEP 1: PREPARING RAW JSON")
                print("="*80)
            
            # Parse raw JSON (just to validate)
            if verbose:
                print(f"  Validating raw JSON ({len(raw_json_str):,} chars)...")
            raw_json_dict = json.loads(raw_json_str)
            if verbose:
                print(f"  [OK] JSON is valid")
            
            if verbose:
                print("\n" + "="*80)
                print("STEP 2: BUILDING PROMPT")
                print("="*80)
            
            # Build prompt with RAW JSON (no filtering)
            prompt = get_extraction_prompt(raw_json_str)
            if verbose:
                print(f"  Prompt size: {len(prompt):,} characters")
                print(f"  Estimated tokens: ~{len(prompt)//4:,}")
            
            if verbose:
                print("\n" + "="*80)
                print("STEP 3: CALLING OPENAI GPT-5")
                print("="*80)
                print(f"  Model: {OPENAI_MODEL}")
                print(f"  Sending request...")
            
            # Call Cerebras via LLM Caller
            result_text = self.llm_caller.call(
                prompt=prompt,
                temperature=0.1
            )
            
            if not result_text:
                raise Exception("Empty response from Cerebras")
            
            if verbose:
                print(f"  [OK] Response received!")
                print(f"\n" + "="*80)
                print("STEP 4: PARSING RESPONSE")
                print("="*80)
                print(f"  Response length: {len(result_text):,} characters")
                
                print(f"\n  First 300 chars of response:")
                print(f"  {result_text[:300]}")
                print(f"\n  Last 200 chars of response:")
                print(f"  {result_text[-200:]}")
            
            # Save raw response for debugging
            debug_response_file = f'debug_response_{contract_id[:20]}.txt'
            with open(debug_response_file, 'w', encoding='utf-8') as f:
                f.write(result_text)
            
            # Robust JSON extraction
            if verbose:
                print(f"\n  [INFO] Extracting JSON from response...")
            
            # Remove markdown code blocks
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0]
            
            # Remove thinking tags
            if '<thinking>' in result_text:
                # Remove everything before </thinking>
                parts = result_text.split('</thinking>')
                if len(parts) > 1:
                    result_text = parts[1]
            
            # Find the outermost JSON object
            json_start = result_text.find('{')
            if json_start == -1:
                raise Exception("No JSON object found in response")
            
            # Find matching closing brace
            brace_count = 0
            json_end = -1
            for i in range(json_start, len(result_text)):
                if result_text[i] == '{':
                    brace_count += 1
                elif result_text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i
                        break
            
            if json_end == -1:
                raise Exception("Could not find closing brace for JSON object")
            
            result_text = result_text[json_start:json_end+1]
            
            if verbose:
                print(f"  [OK] Extracted JSON portion: {len(result_text):,} chars")
            
            # Try to parse JSON
            if verbose:
                print(f"\n  Parsing JSON...")
            
            try:
                result = json.loads(result_text.strip())
            except json.JSONDecodeError as e:
                # Try to fix common issues
                if verbose:
                    print(f"  [WARNING] Initial JSON parse failed: {e}")
                    print(f"  [INFO] Attempting to fix common JSON errors...")
                
                # Remove trailing commas before closing braces/brackets
                import re
                fixed_text = re.sub(r',(\s*[}\]])', r'\1', result_text)
                
                try:
                    result = json.loads(fixed_text.strip())
                    if verbose:
                        print(f"  [OK] JSON fixed and parsed successfully")
                except json.JSONDecodeError as e2:
                    # Save the problematic JSON
                    error_json_file = f'debug_bad_json_{contract_id[:20]}.json'
                    with open(error_json_file, 'w', encoding='utf-8') as f:
                        f.write(result_text)
                    print(f"  [ERROR] Saved problematic JSON to: {error_json_file}")
                    raise e2
            
            if verbose:
                print(f"  [OK] JSON parsed successfully")
            
            # Analyze result
            tables = result.get('extracted_tables', [])
            if verbose:
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
                
                num_tables = len(result.get('extracted_tables', []))
                total_rows = sum(
                    len(table.get('table_data', [])) 
                    for table in result.get('extracted_tables', [])
                )
                print(f"  [OK] Extracted {num_tables} tables, {total_rows} rows")
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            
            # Always print error (even if not verbose)
            print(f"\n{'='*80}")
            print(f"[ERROR] LLM EXTRACTION FAILED - Contract {contract_id[:40]}")
            print(f"{'='*80}")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {error_msg}")
            print(f"Raw JSON size: {len(raw_json_str):,} chars")
            
            if 'prompt' in locals():
                print(f"Prompt size: {len(prompt):,} chars")
            
            # Print traceback
            import traceback
            print("\nFull traceback:")
            traceback.print_exc()
            print(f"{'='*80}\n")
            
            # Save debug info
            debug_info = {
                'contract_id': contract_id,
                'error': error_msg,
                'error_type': type(e).__name__,
                'prompt_length': len(prompt) if 'prompt' in locals() else 0,
                'raw_json_length': len(raw_json_str)
            }
            
            if 'result_text' in locals():
                debug_info['response_preview'] = result_text[:500]
            
            debug_file = f'debug_llm_error_{contract_id[:20]}.json'
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(debug_info, f, indent=2)
            
            print(f"Debug info saved to: {debug_file}\n")
            
            # Return error info instead of None
            return {'error': error_msg, 'error_type': type(e).__name__}
    
    async def process_contract_async(self, contract_id, raw_json_str, worker_id):
        """Process one contract asynchronously"""
        
        loop = asyncio.get_event_loop()
        
        # Run blocking Cerebras call in thread pool
        result = await loop.run_in_executor(
            None,
            lambda: self.extract_with_llm(contract_id, raw_json_str, verbose=False)
        )
        
        # Check if extraction succeeded
        if result and 'error' not in result:
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
            # Extraction failed
            error_msg = result.get('error', 'Unknown error') if result else 'No result returned'
            return {'status': 'failed', 'error': error_msg}
    
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
                print(f"[Worker {worker_id}] Starting OpenAI GPT-5 call...")
                
                result = await self.process_contract_async(contract_id, raw_json_str, worker_id)
                
                if result['status'] == 'success':
                    print(f"[Worker {worker_id}] [OK] {result['num_tables']} tables, {result['num_rows']} rows")
                else:
                    print(f"[Worker {worker_id}] [FAILED] Error: {result.get('error', 'Unknown error')}")
                
                processed += 1
                queue.task_done()
                
                # Rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"\n{'='*80}")
                print(f"[Worker {worker_id}] EXCEPTION IN WORKER")
                print(f"{'='*80}")
                print(f"Error type: {type(e).__name__}")
                print(f"Error message: {str(e)}")
                
                import traceback
                print("\nFull traceback:")
                traceback.print_exc()
                print(f"{'='*80}\n")
                
                queue.task_done()
        
        print(f"[Worker {worker_id}] Finished processing {processed} contracts")
    
    async def run_async(self, limit=None, reprocess=False):
        """Run LLM extraction on all raw_jsons"""
        print("="*80)
        print(f"LLM TABLE EXTRACTION - {self.num_workers} WORKERS")
        print(f"Model: {OPENAI_MODEL}")
        print("="*80 + "\n")
        
        # Setup
        print("[1/7] Adding llm_extracted_tables column if needed...")
        self.add_llm_column()
        
        print("[2/7] Setting up LiteLLM client...")
        self.setup_client()
        
        # Get contracts to process
        print("[3/7] Querying database for contracts to process...")
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
        
        print("[4/7] Fetching contracts from database...")
        contracts = cursor.fetchall()
        conn.close()
        print(f"  [OK] Fetched {len(contracts)} contracts from database")
        
        if limit:
            contracts = contracts[:limit]
            print(f"  [OK] Limited to {limit} contracts")
        
        total = len(contracts)
        
        if total == 0:
            print("[OK] No contracts to process\n")
            return
        
        print(f"\n[5/7] Processing {total} contracts with {self.num_workers} workers")
        print("="*80 + "\n")
        
        # Create queue
        print("[6/7] Creating async queue and adding contracts...")
        queue = asyncio.Queue()
        
        # Add contracts to queue
        for idx, (contract_id, raw_json_str) in enumerate(contracts, 1):
            await queue.put((idx, contract_id, raw_json_str))
        
        # Add poison pills
        for _ in range(self.num_workers):
            await queue.put(None)
        
        print(f"  [OK] Added {total} contracts to queue")
        
        # Start workers
        print(f"[7/7] Starting {self.num_workers} workers...")
        start_time = time.time()
        
        workers = [
            asyncio.create_task(self.worker(queue, i+1, total))
            for i in range(self.num_workers)
        ]
        
        print(f"  [OK] All workers started, processing...\n")
        print("="*80 + "\n")
        
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

def show_stats():
    """Show LLM extraction statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("="*80)
    print("LLM EXTRACTION STATISTICS")
    print("="*80 + "\n")
    
    # Total with raw_json
    cursor.execute("SELECT COUNT(*) FROM contracts WHERE raw_json IS NOT NULL")
    total_raw = cursor.fetchone()[0]
    
    # Completed
    cursor.execute("SELECT COUNT(*) FROM contracts WHERE llm_extracted_tables IS NOT NULL")
    completed = cursor.fetchone()[0]
    
    # Pending
    pending = total_raw - completed
    
    print(f"Total contracts with raw_json: {total_raw}")
    print(f"LLM extracted (completed):     {completed}")
    print(f"Pending:                       {pending}")
    print(f"Success rate:                  {completed/total_raw*100:.1f}%\n" if total_raw > 0 else "")
    
    # Show sample of completed
    if completed > 0:
        cursor.execute("""
            SELECT id, hospital_name
            FROM contracts 
            WHERE llm_extracted_tables IS NOT NULL
            LIMIT 5
        """)
        print("Sample completed contracts:")
        for contract_id, hospital in cursor.fetchall():
            print(f"  - {contract_id[:40]} | {hospital[:50]}")
    
    print("\n" + "="*80)
    conn.close()

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='LLM table extraction with OpenAI GPT-5')
    parser.add_argument('--limit', type=int, help='Limit number of contracts')
    parser.add_argument('--reprocess', action='store_true', help='Reprocess all')
    parser.add_argument('--workers', type=int, default=5, help='Number of workers (default: 5)')
    parser.add_argument('--test', action='store_true', help='Test with one contract')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    
    args = parser.parse_args()
    
    if args.stats:
        # Show statistics
        show_stats()
    elif args.test:
        # Test with one contract
        print("Testing OpenAI GPT-5 extraction on one contract...\n")
        
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
        
        extractor = GPT5TableExtractor()
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
            existing_tests = list(samples_dir.glob('test_*_gpt5_output.json'))
            next_num = len(existing_tests) + 1
            
            # Save test output with number
            output_file = samples_dir / f'test_{next_num:03d}_gpt5_output.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            # Save the raw JSON input (no filtering)
            raw_input_file = samples_dir / f'test_{next_num:03d}_raw_input.json'
            with open(raw_input_file, 'w', encoding='utf-8') as f:
                json.dump(json.loads(raw_json_str), f, indent=2, ensure_ascii=False)
            
            # Save contract info
            info_file = samples_dir / f'test_{next_num:03d}_info.txt'
            with open(info_file, 'w', encoding='utf-8') as f:
                f.write(f"Test Number: {next_num}\n")
                f.write(f"Contract ID: {contract_id}\n")
                f.write(f"Raw JSON size: {len(raw_json_str):,} characters\n")
                f.write(f"Model: {OPENAI_MODEL}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Tables extracted: {len(result.get('extracted_tables', []))}\n")
                total_rows = sum(len(t.get('table_data', [])) for t in result.get('extracted_tables', []))
                f.write(f"Total rows: {total_rows}\n")
            
            print(f"\n[OK] Saved test #{next_num}:")
            print(f"  Input:  {raw_input_file}")
            print(f"  Output: {output_file}")
            print(f"  Info:   {info_file}")
    else:
        # Run full extraction
        print("\n[STARTUP] Initializing extractor...")
        extractor = GPT5TableExtractor(num_workers=args.workers)
        print(f"[STARTUP] Starting async extraction with {args.workers} workers...")
        asyncio.run(extractor.run_async(
            limit=args.limit,
            reprocess=args.reprocess
        ))

if __name__ == "__main__":
    main()

