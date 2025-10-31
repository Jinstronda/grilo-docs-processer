# Interactive Extraction Running

## What's Happening Now

The `interactive_extractor.py` script is running and will:

1. **Download 2 PDFs** from the database to `extractions/pdfs/`
2. **Open a Chrome browser** (visible, non-headless mode)
3. **Navigate to Google AI Studio** (https://aistudio.google.com/prompts/new_chat)
4. **Wait for you to sign in** if not already authenticated

## Your Actions Required

### Step 1: Sign In
- When the browser opens, sign in to Google AI Studio
- Press Enter in the terminal when done

### Step 2: For Each PDF (2 total)

**Upload PDF:**
- The script will pause and show you the PDF path
- Click the attachment/upload button in Google AI Studio
- Select the PDF file from the path shown
- Press Enter in terminal when uploaded

**Review Prompt:**
- The script will automatically enter the extraction prompt
- Review it and click the Send button
- Press Enter in terminal after sending

**Wait for Response:**
- Wait for AI to generate the response
- Press Enter in terminal when response is complete

**Automatic Save:**
- Script will try to extract JSON automatically
- Results saved to:
  - File: `extractions/{contract_id}_{hospital}_{year}_{timestamp}.json`
  - Database: `aistudio_json` column in contracts table

### Step 3: Screenshots

The script takes screenshots at each step:
- `step1_initial.png` - Initial page
- `step2_uploaded.png` - After PDF upload
- `step3_prompt_entered.png` - After entering prompt
- `step4_response.png` - AI response

## Database Updates

Results are automatically saved to the database:
```sql
UPDATE contracts 
SET aistudio_json = <extracted_json>
WHERE id = <contract_id>
```

## Manual JSON Extraction (if needed)

If automatic extraction fails:
1. Manually copy the JSON from the browser
2. Save to: `extractions/manual_{contract_id}.json`

## Expected Output

For each successful extraction:
```
[OK] Saved result to file: extractions/...json
[OK] Saved result to database (aistudio_json column)
```

## Troubleshooting

**Browser doesn't open:**
- Check if Playwright is installed: `python -m playwright install chromium`

**Can't find upload button:**
- Look for paperclip, attach, or plus icon
- Take your time, the script waits for you

**JSON extraction fails:**
- The page HTML is saved to `manual_extract_{contract_id}.html`
- Manually copy JSON from browser

## Stop the Script

Press Ctrl+C in the terminal at any time to stop.

## After Completion

Check the database:
```python
import sqlite3
conn = sqlite3.connect("data/hospital_tables.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT id, hospital_name, aistudio_json 
    FROM contracts 
    WHERE aistudio_json IS NOT NULL
""")

for row in cursor.fetchall():
    print(f"Contract: {row[0]} - {row[1]}")
    print(f"Has data: {len(row[2])} chars\n")
```

---

**Note:** This is an interactive process. Take your time with each step and ensure accuracy!

