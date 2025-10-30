"""
Main Table Extraction Pipeline with SQLite Database - ASYNC VERSION
Processes PDFs with 5 concurrent workers for faster extraction
"""
import sqlite3
import json
import sys
import time
import asyncio
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading

# Add google_docai to path
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'google_docai'))

import pandas as pd
from extract_tables import create_creds, download_pdf, extract_tables_from_pdf

try:
    from PyPDF2 import PdfReader, PdfWriter
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

# Database configuration
DB_PATH = "data/hospital_tables.db"
CSV_PATH = "data/hospital_agreements.csv"

class AsyncExtractionPipeline:
    """Async extraction pipeline with concurrent workers"""
    
    def __init__(self, db_path=DB_PATH, csv_path=CSV_PATH, num_workers=5):
        self.db_path = db_path
        self.csv_path = csv_path
        self.num_workers = num_workers
        self.credentials = None
        
        # Thread-safe database connection per thread
        self.db_lock = threading.Lock()
        self.thread_local = threading.local()
        
    def get_connection(self):
        """Get thread-local database connection"""
        if not hasattr(self.thread_local, 'conn'):
            self.thread_local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self.thread_local.conn
        
    def setup_database(self):
        """Create database and table structure"""
        print("="*80)
        print("Setting up SQLite Database")
        print("="*80 + "\n")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create main table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id TEXT PRIMARY KEY,
                year INTEGER,
                hospital_name TEXT,
                region TEXT,
                contract_title TEXT,
                original_pdf_url TEXT,
                gcs_pdf_path TEXT,
                scraped_at TEXT,
                created_at TEXT,
                updated_at TEXT,
                raw_json TEXT,
                extracted_tables TEXT,
                extraction_status TEXT DEFAULT 'pending',
                extraction_timestamp TEXT,
                error_message TEXT,
                num_tables INTEGER,
                num_rows INTEGER
            )
        """)
        
        # Create processing log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id TEXT,
                timestamp TEXT,
                status TEXT,
                message TEXT,
                FOREIGN KEY (contract_id) REFERENCES contracts(id)
            )
        """)
        
        conn.commit()
        conn.close()
        print(f"[OK] Database initialized: {self.db_path}\n")
        
    def load_csv_data(self):
        """Load CSV and populate database"""
        print("="*80)
        print("Loading CSV Data")
        print("="*80 + "\n")
        
        df = pd.read_csv(self.csv_path)
        print(f"[OK] Loaded {len(df)} contracts from CSV\n")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        inserted = 0
        updated = 0
        
        for _, row in df.iterrows():
            cursor.execute("SELECT id FROM contracts WHERE id = ?", (row['id'],))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute("""
                    UPDATE contracts 
                    SET year = ?, hospital_name = ?, region = ?, contract_title = ?,
                        original_pdf_url = ?, gcs_pdf_path = ?, scraped_at = ?,
                        created_at = ?, updated_at = ?
                    WHERE id = ? AND extraction_status = 'pending'
                """, (
                    row.get('year', None), row.get('hospital_name', ''),
                    row.get('region', ''), row.get('contract_title', ''),
                    row.get('original_pdf_url', ''), row.get('gcs_pdf_path', ''),
                    row.get('scraped_at', ''), row.get('created_at', ''),
                    row.get('updated_at', ''), row['id']
                ))
                if cursor.rowcount > 0:
                    updated += 1
            else:
                cursor.execute("""
                    INSERT INTO contracts (
                        id, year, hospital_name, region, contract_title,
                        original_pdf_url, gcs_pdf_path, scraped_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row['id'], row.get('year', None), row.get('hospital_name', ''),
                    row.get('region', ''), row.get('contract_title', ''),
                    row.get('original_pdf_url', ''), row.get('gcs_pdf_path', ''),
                    row.get('scraped_at', ''), row.get('created_at', ''),
                    row.get('updated_at', '')
                ))
                inserted += 1
        
        conn.commit()
        conn.close()
        print(f"[OK] Inserted: {inserted}, Updated: {updated}\n")
        
    def log_processing(self, contract_id, status, message):
        """Thread-safe log processing event"""
        with self.db_lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO processing_log (contract_id, timestamp, status, message)
                VALUES (?, ?, ?, ?)
            """, (contract_id, datetime.now().isoformat(), status, message))
            conn.commit()
    
    def trim_large_pdf(self, pdf_path, max_pages=30, verbose=False):
        """Remove pages from start to keep exactly max_pages"""
        if not HAS_PYPDF2:
            return pdf_path
        
        try:
            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            
            if num_pages <= max_pages:
                return pdf_path
            
            # Calculate how many pages to remove from start
            pages_to_remove = num_pages - max_pages
            
            if verbose:
                print(f"    [INFO] Trimming {num_pages} pages → {max_pages} (removing first {pages_to_remove})")
            
            writer = PdfWriter()
            for page_num in range(pages_to_remove, num_pages):
                writer.add_page(reader.pages[page_num])
            
            trimmed_path = pdf_path.replace('.pdf', '_trimmed.pdf')
            with open(trimmed_path, 'wb') as f:
                writer.write(f)
            
            return trimmed_path
            
        except Exception as e:
            return pdf_path
    
    async def process_contract_async(self, contract_id, pdf_url, gcs_path, worker_id):
        """Process single contract asynchronously"""
        
        pdf_path = None
        trimmed_path = None
        
        try:
            # Run blocking I/O in thread pool
            loop = asyncio.get_event_loop()
            
            # Choose fastest method
            if gcs_path and gcs_path.startswith('gs://'):
                try:
                    # Try GCS path
                    tables, raw_api_response = await loop.run_in_executor(
                        None,
                        lambda: extract_tables_from_pdf(
                            gcs_path, self.credentials, verbose=False,
                            save_intermediate=False, use_gcs=True, return_raw=True
                        )
                    )
                except Exception as e:
                    error_str = str(e)
                    if 'PAGE_LIMIT_EXCEEDED' in error_str or 'pages exceed the limit' in error_str:
                        # Download and trim
                        pdf_path = await loop.run_in_executor(
                            None, lambda: download_pdf(pdf_url, verbose=False)
                        )
                        if not pdf_path:
                            raise Exception("PDF download failed")
                        
                        trimmed_path = self.trim_large_pdf(pdf_path, 30, False)
                        
                        # Retry with trimmed
                        tables, raw_api_response = await loop.run_in_executor(
                            None,
                            lambda: extract_tables_from_pdf(
                                trimmed_path, self.credentials, verbose=False,
                                save_intermediate=False, use_gcs=False, return_raw=True
                            )
                        )
                    else:
                        raise
            else:
                # Download PDF
                pdf_path = await loop.run_in_executor(
                    None, lambda: download_pdf(pdf_url, verbose=False)
                )
                if not pdf_path:
                    raise Exception("PDF download failed")
                
                trimmed_path = self.trim_large_pdf(pdf_path, 30, False)
                
                # Extract tables
                tables, raw_api_response = await loop.run_in_executor(
                    None,
                    lambda: extract_tables_from_pdf(
                        trimmed_path, self.credentials, verbose=False,
                        save_intermediate=False, use_gcs=False, return_raw=True
                    )
                )
            
            # Store results
            result = {"contract_id": contract_id, "tables": tables}
            num_tables = len(tables)
            num_rows = sum(len(table['rows']) for table in tables)
            
            # Thread-safe database update
            with self.db_lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE contracts 
                    SET raw_json = ?, extracted_tables = ?,
                        extraction_status = 'success', extraction_timestamp = ?,
                        num_tables = ?, num_rows = ?, error_message = NULL
                    WHERE id = ?
                """, (
                    json.dumps(raw_api_response, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    datetime.now().isoformat(), num_tables, num_rows, contract_id
                ))
                conn.commit()
            
            self.log_processing(contract_id, 'success', f"{num_tables} tables, {num_rows} rows")
            
            # Cleanup
            if pdf_path:
                Path(pdf_path).unlink(missing_ok=True)
            if trimmed_path and trimmed_path != pdf_path:
                Path(trimmed_path).unlink(missing_ok=True)
            
            return {'status': 'success', 'num_tables': num_tables, 'num_rows': num_rows}
            
        except Exception as e:
            error_msg = str(e)
            
            # Thread-safe error update
            with self.db_lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE contracts 
                    SET extraction_status = 'failed', extraction_timestamp = ?, error_message = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), error_msg, contract_id))
                conn.commit()
            
            self.log_processing(contract_id, 'failed', error_msg)
            
            # Cleanup
            if pdf_path:
                Path(pdf_path).unlink(missing_ok=True)
            if trimmed_path and trimmed_path != pdf_path:
                Path(trimmed_path).unlink(missing_ok=True)
            
            return {'status': 'failed', 'error': error_msg}
    
    async def worker(self, queue, worker_id, total):
        """Worker that processes contracts from queue"""
        processed = 0
        
        while True:
            try:
                item = await queue.get()
                if item is None:  # Poison pill
                    break
                
                idx, contract_id, pdf_url, gcs_path = item
                
                print(f"[Worker {worker_id}] [{idx}/{total}] {contract_id[:40]}")
                
                result = await self.process_contract_async(contract_id, pdf_url, gcs_path, worker_id)
                
                if result['status'] == 'success':
                    print(f"[Worker {worker_id}] [OK] {result['num_tables']} tables, {result['num_rows']} rows")
                else:
                    print(f"[Worker {worker_id}] [FAILED] {result.get('error', 'Unknown error')[:50]}")
                
                processed += 1
                queue.task_done()
                
                # Rate limiting
                await asyncio.sleep(0.4)  # 0.4s * 5 workers = ~2s average between requests
                
            except Exception as e:
                print(f"[Worker {worker_id}] [ERROR] {e}")
                queue.task_done()
        
        print(f"[Worker {worker_id}] Processed {processed} contracts")
    
    async def run_async(self, limit=None, resume=True):
        """Run async extraction pipeline"""
        print("="*80)
        print(f"ASYNC PIPELINE - {self.num_workers} CONCURRENT WORKERS")
        print("="*80 + "\n")
        
        # Setup
        self.setup_database()
        self.load_csv_data()
        
        # Load credentials
        try:
            self.credentials = create_creds()
            print("[OK] Google credentials loaded\n")
        except Exception as e:
            print(f"[ERROR] Failed to load credentials: {e}")
            return
        
        # Get contracts to process
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if resume:
            cursor.execute("""
                SELECT id, original_pdf_url, gcs_pdf_path 
                FROM contracts 
                WHERE extraction_status IN ('pending', 'failed')
                ORDER BY id
            """)
        else:
            cursor.execute("""
                SELECT id, original_pdf_url, gcs_pdf_path 
                FROM contracts 
                ORDER BY id
            """)
        
        contracts = cursor.fetchall()
        conn.close()
        
        if limit:
            contracts = contracts[:limit]
        
        total = len(contracts)
        
        if total == 0:
            print("[OK] No contracts to process\n")
            self.print_summary()
            return
        
        print(f"Processing {total} contracts with {self.num_workers} workers\n")
        print("="*80 + "\n")
        
        # Create queue
        queue = asyncio.Queue()
        
        # Add contracts to queue
        for idx, (contract_id, pdf_url, gcs_path) in enumerate(contracts, 1):
            await queue.put((idx, contract_id, pdf_url, gcs_path))
        
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
        print("PROCESSING COMPLETE")
        print("="*80)
        print(f"Time elapsed: {elapsed/60:.1f} minutes")
        print(f"Average: {elapsed/total:.1f} seconds per contract")
        print(f"Workers: {self.num_workers}")
        print("="*80 + "\n")
        
        self.print_summary()
    
    def get_processing_stats(self):
        """Get current processing statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM contracts WHERE extraction_status = 'success'")
        success = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM contracts WHERE extraction_status = 'failed'")
        failed = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM contracts WHERE extraction_status = 'pending'")
        pending = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(num_tables), SUM(num_rows) FROM contracts WHERE extraction_status = 'success'")
        totals = cursor.fetchone()
        total_tables = totals[0] or 0
        total_rows = totals[1] or 0
        
        conn.close()
        
        return {
            'success': success,
            'failed': failed,
            'pending': pending,
            'total_tables': total_tables,
            'total_rows': total_rows
        }
    
    def print_summary(self):
        """Print processing summary"""
        stats = self.get_processing_stats()
        
        print("="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Success:       {stats['success']}")
        print(f"Failed:        {stats['failed']}")
        print(f"Pending:       {stats['pending']}")
        print(f"\nTotal tables:  {stats['total_tables']}")
        print(f"Total rows:    {stats['total_rows']}")
        print("="*80)
        print(f"\nDatabase: {self.db_path}")
        print("="*80)

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Async table extraction pipeline')
    parser.add_argument('--limit', type=int, help='Limit number of contracts')
    parser.add_argument('--no-resume', action='store_true', help='Process all (ignore existing)')
    parser.add_argument('--workers', type=int, default=5, help='Number of concurrent workers (default: 5)')
    parser.add_argument('--stats', action='store_true', help='Show statistics only')
    
    args = parser.parse_args()
    
    pipeline = AsyncExtractionPipeline(num_workers=args.workers)
    
    if args.stats:
        pipeline.setup_database()
        pipeline.print_summary()
    else:
        asyncio.run(pipeline.run_async(
            limit=args.limit,
            resume=not args.no_resume
        ))

if __name__ == "__main__":
    main()

