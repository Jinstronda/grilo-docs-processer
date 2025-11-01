# Cleanup Plan for google-ai-studio/

## Files to DELETE (no longer needed):

### Debug/Testing Scripts:
- `check_tables.py` - Was just for checking DB structure
- `validate_debug.py` - Temporary debug script
- `validate_extractions.py` - Duplicate of check_quality.py
- `validate_simple.py` - Duplicate of check_quality.py

### Old Scripts:
- `extract_tables_google_ai.py` - Old manual extraction (replaced by interactive_extractor.py)

### Debug Output Files:
- `extractions/debug_extract_*.txt` - All 27 debug files
- `extractions/debug_json_parse_error.txt` - Temporary debug file

## Files to KEEP:

### Core:
- `interactive_extractor.py` - Main extraction script ✓
- `cookies.json` - Browser cookies for login ✓
- `requirements.txt` - Dependencies ✓
- `README.md` - Documentation ✓

### Utilities:
- `check_pdf_stats.py` - Shows extraction progress ✓
- `check_quality.py` - Validates extraction quality ✓
- `check_and_fix_status.py` - Fixes stuck worker status ✓
- `fix_encoding.py` - Fixes encoding in old JSONs ✓
- `test_setup.py` - Tests database setup ✓

## Code Simplifications in interactive_extractor.py:

### To Remove:
1. **TEST_MODE** - No longer needed, can be removed
2. **wait_for_user_action()** - Manual intervention function, not used in automated mode
3. **DEBUG output generation** - The detailed debug prints and file saves
4. **Screenshot code** - All commented out, can be deleted
5. **Manual extract HTML saves** - Only needed for debugging

### To Simplify:
1. Reduce excessive logging (too many print statements)
2. Remove old commented-out code
3. Consolidate duplicate checks

