# Google AI Studio Automated Table Extraction

Fully automated pipeline for extracting tables from PDF contracts using Google AI Studio and Gemini 2.5 Pro.

## 🎯 Overview

This script automates the entire process of:
1. Downloading PDFs from the database
2. Uploading them to Google AI Studio
3. Extracting tables using Gemini 2.5 Pro
4. Saving results to the database (`aistudio_json` column)

**Status:** ✅ FULLY WORKING - Tested and operational!

## 🚀 Quick Start

### 1. Setup

```bash
# Install dependencies
cd google-ai-studio
pip install -r requirements.txt

# Test setup
python test_setup.py
```

### 2. Configure Number of PDFs

Open `interactive_extractor.py` and find this line (around line 563):

```python
LIMIT 2  # Change this number or remove LIMIT to process all PDFs
```

**Options:**
- `LIMIT 2` - Process 2 PDFs (testing)
- `LIMIT 100` - Process 100 PDFs
- Remove `LIMIT 2` entirely - Process ALL 731 PDFs

### 3. Run

```powershell
python interactive_extractor.py
```

**That's it!** The script is fully automated:
- Loads cookies → Auto-login ✅
- Clicks Gemini 2.5 Pro ✅
- Uploads PDFs ✅
- Extracts tables ✅
- Saves to database ✅

## 📊 What Gets Saved

### Database
Results are automatically saved to the `contracts` table:

```sql
UPDATE contracts 
SET aistudio_json = '<extracted_json>'
WHERE id = '<contract_id>'
```

### Files
Also saved to `extractions/` folder:
```
{contract_id}_{hospital_name}_{year}_{timestamp}.json
```

## ⚙️ Configuration

### Test Mode

To test the extraction without PDFs (quick test with simple JSON):

```python
# In interactive_extractor.py, line 18:
TEST_MODE = True  # Set to True for testing
```

Test mode:
- Skips PDF download and upload
- Uses simple prompt (numbers 1-100)
- Tests JSON detection and extraction
- Fast for debugging

### Processing Limits

Edit line 563 in `interactive_extractor.py`:

```python
# Process 10 PDFs
LIMIT 10

# Process all PDFs (remove LIMIT)
# Just delete the entire "LIMIT 2" line
```

## 🔐 Authentication

The script uses cookies for auto-login:

1. **First Run:** Sign in manually when browser opens
2. **Cookies Saved:** Your session is saved to `cookies.json`
3. **Future Runs:** Automatically logged in!

### Cookie Expiry

If cookies expire (usually after a few weeks):
- Script will ask you to sign in again
- New cookies automatically saved
- Good to go!

## 📋 Complete Flow

```
1. Load cookies → Auto-login to Google AI Studio
2. Navigate to AI Studio home page
3. Click "Gemini 2.5 Pro" card
4. For each PDF:
   a. Click "Insert assets" button
   b. Click "Upload File"
   c. Upload PDF automatically
   d. Type extraction prompt
   e. Press Ctrl+Enter
   f. Wait for JSON code block to appear (polling every 5s)
   g. Extract JSON from code block
   h. Save to database (aistudio_json column)
   i. Save to file (extractions/ folder)
   j. Start new chat
   k. Click "Gemini 2.5 Pro" again
   l. Repeat!
```

## 🎛️ Features

### Automatic Detection
- Polls page every 5 seconds
- Looks for JSON code block UI element
- Waits up to 15 minutes per PDF
- Shows progress every minute

### Robust Extraction
- Targets `region[aria-label="JSON"]` elements
- Gets full content (handles large JSON)
- Cleans HTML entities
- Removes success markers
- Validates JSON structure

### Error Handling
- Falls back to manual steps if automation fails
- Saves debug files for troubleshooting
- Takes screenshots at each step
- Comprehensive error messages

## 📁 Files

- `interactive_extractor.py` - Main automation script (FULLY WORKING!)
- `extract_tables_google_ai.py` - Alternative automation (experimental)
- `test_setup.py` - Setup verification
- `cookies.json` - Saved authentication (auto-generated, in .gitignore)
- `cookies.example.json` - Cookie format example
- `requirements.txt` - Python dependencies
- `extractions/` - Output folder
- `README.md` - This file

## 🔧 Troubleshooting

### "No code blocks found"

**Cause:** Response not ready yet  
**Fix:** Script now waits longer (15 min timeout)

### "JSON parse error"

**Cause:** Truncated or malformed JSON  
**Fix:** Script now gets full content from region elements

### Upload fails

**Cause:** Button selectors changed  
**Fix:** Script uses role-based selectors (more stable)

### Not logged in

**Cause:** Cookies expired  
**Fix:** Delete `cookies.json`, run script, sign in again

## 📈 Running at Scale

### Process All 731 PDFs

1. Edit `interactive_extractor.py` line 563
2. Remove `LIMIT 2` entirely
3. Run: `python interactive_extractor.py`
4. **Important:** This will take a LONG time!
   - ~400 seconds per PDF
   - 731 PDFs × 400s = ~81 hours
   - Consider running overnight or in batches

### Recommended Approach

```python
# Process in batches of 50
LIMIT 50
```

Run multiple times to process all PDFs in manageable chunks.

### Resume Processing

To process only PDFs that haven't been extracted yet:

```sql
WHERE original_pdf_url IS NOT NULL 
  AND aistudio_json IS NULL  -- Only unprocessed
LIMIT 50
```

## 📊 Check Results

Query the database to see extracted data:

```python
import sqlite3
conn = sqlite3.connect("data/hospital_tables.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT id, hospital_name, aistudio_json IS NOT NULL as has_data
    FROM contracts 
    WHERE aistudio_json IS NOT NULL
""")

for row in cursor.fetchall():
    print(f"{row[0]}: {row[1]} - Extracted: {row[2]}")
```

## 🎉 Success!

The automation is **fully working** and tested! It successfully:
- ✅ Auto-logs in with cookies
- ✅ Clicks Gemini 2.5 Pro
- ✅ Uploads PDFs automatically
- ✅ Submits prompts
- ✅ Detects completion (JSON code block)
- ✅ Extracts complete JSON (even very large responses)
- ✅ Saves to database
- ✅ Processes multiple PDFs in sequence

## 🚦 Current Settings

**Default:** Processes 2 PDFs for testing

**To change:** Edit line 563 in `interactive_extractor.py`

**Test mode:** Set `TEST_MODE = True` (line 18) for quick testing without PDFs

---

**Ready to process all your contracts!** 🎯

Just change the LIMIT and run the script. Everything else is automatic!
