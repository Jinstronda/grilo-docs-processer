"""
Test script to verify setup and database access
"""
import sqlite3
import sys
from pathlib import Path

def test_database_connection():
    """Test database connectivity and show sample data"""
    db_path = Path(__file__).parent.parent / "data" / "hospital_tables.db"
    
    print("="*80)
    print("Testing Database Connection")
    print("="*80)
    print(f"\nDatabase path: {db_path}")
    print(f"Database exists: {db_path.exists()}")
    
    if not db_path.exists():
        print("\n[ERROR] Database not found!")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get table count
        cursor.execute("SELECT COUNT(*) FROM contracts")
        total = cursor.fetchone()[0]
        print(f"\nTotal contracts: {total}")
        
        # Get contracts with PDFs
        cursor.execute("SELECT COUNT(*) FROM contracts WHERE original_pdf_url IS NOT NULL")
        with_pdf = cursor.fetchone()[0]
        print(f"Contracts with PDF URLs: {with_pdf}")
        
        # Get contracts with raw JSON
        cursor.execute("SELECT COUNT(*) FROM contracts WHERE raw_json IS NOT NULL")
        with_json = cursor.fetchone()[0]
        print(f"Contracts with raw JSON: {with_json}")
        
        # Get sample contracts
        print("\n" + "="*80)
        print("Sample Contracts (first 3 with PDFs)")
        print("="*80 + "\n")
        
        cursor.execute("""
            SELECT id, hospital_name, year, original_pdf_url
            FROM contracts 
            WHERE original_pdf_url IS NOT NULL
            LIMIT 3
        """)
        
        for i, row in enumerate(cursor.fetchall(), 1):
            contract_id, hospital, year, url = row
            print(f"Contract {i}:")
            print(f"  ID: {contract_id}")
            print(f"  Hospital: {hospital}")
            print(f"  Year: {year}")
            print(f"  URL: {url[:80]}...")
            print()
        
        conn.close()
        
        print("[OK] Database connection successful!")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Database error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dependencies():
    """Test required Python packages"""
    print("\n" + "="*80)
    print("Testing Dependencies")
    print("="*80 + "\n")
    
    required = {
        'playwright': 'Playwright',
        'requests': 'Requests'
    }
    
    missing = []
    
    for module, name in required.items():
        try:
            __import__(module)
            print(f"[OK] {name} installed")
        except ImportError:
            print(f"[MISSING] {name} not installed")
            missing.append(module)
    
    if missing:
        print("\n[WARNING] Missing dependencies!")
        print("Install with:")
        print(f"  pip install {' '.join(missing)}")
        
        if 'playwright' in missing:
            print("\nFor Playwright, also run:")
            print("  python -m playwright install chromium")
        
        return False
    
    print("\n[OK] All dependencies installed!")
    return True

def test_output_directory():
    """Test output directory creation"""
    print("\n" + "="*80)
    print("Testing Output Directory")
    print("="*80 + "\n")
    
    output_dir = Path(__file__).parent / "extractions"
    
    try:
        output_dir.mkdir(exist_ok=True)
        print(f"Output directory: {output_dir}")
        print(f"Directory exists: {output_dir.exists()}")
        print(f"Directory writable: {output_dir.is_dir()}")
        
        # Test write
        test_file = output_dir / "test.txt"
        test_file.write_text("test")
        test_file.unlink()
        
        print("\n[OK] Output directory ready!")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Output directory error: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "#"*80)
    print("Google AI Studio Extraction - Setup Test")
    print("#"*80 + "\n")
    
    results = []
    
    # Test database
    results.append(("Database", test_database_connection()))
    
    # Test dependencies
    results.append(("Dependencies", test_dependencies()))
    
    # Test output directory
    results.append(("Output Directory", test_output_directory()))
    
    # Summary
    print("\n" + "#"*80)
    print("TEST SUMMARY")
    print("#"*80 + "\n")
    
    all_passed = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} - {name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n[OK] All tests passed! Ready to run extraction scripts.")
        print("\nNext steps:")
        print("  1. Run: python interactive_extractor.py")
        print("  2. Or read: manual_extraction_guide.md")
        return 0
    else:
        print("\n[ERROR] Some tests failed. Please fix issues before proceeding.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

