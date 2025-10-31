# Google AI Studio Table Extraction

This folder contains scripts for extracting tables from PDF contracts using Google AI Studio's web interface.

## Overview

Google AI Studio (https://aistudio.google.com/) provides a web-based interface for interacting with Google's Gemini models. This approach uses Playwright automation to:

1. Download PDFs from the database
2. Upload them to Google AI Studio
3. Submit table extraction prompts
4. Capture and save the JSON responses

## Files

- `extract_tables_google_ai.py` - Fully automated extraction script (requires manual authentication)
- `interactive_extractor.py` - Semi-automated script with user guidance at each step
- `manual_extraction_guide.md` - Comprehensive guide for manual extraction
- `README.md` - This file
- `extractions/` - Output directory for extracted tables (created automatically)

## Setup

### Install Dependencies

```bash
pip install playwright requests
python -m playwright install chromium
```

### Database Access

The scripts read from the existing SQLite database at:
```
data/hospital_tables.db
```

Make sure this database exists and contains contracts with `original_pdf_url` values.

## Usage

### Option 1: Interactive Extraction (Recommended)

The interactive script guides you through each step:

```bash
cd google-ai-studio
python interactive_extractor.py
```

**Process:**
1. Script downloads PDFs to `extractions/pdfs/`
2. Opens browser to Google AI Studio
3. Waits for you to sign in
4. Prompts you to upload each PDF
5. Automatically enters the extraction prompt
6. Waits for you to send the prompt
7. Attempts to extract JSON from response
8. Saves results to `extractions/`

**Advantages:**
- You have control at each step
- Can verify uploads and prompts
- Handles authentication reliably
- Takes screenshots at each stage

### Option 2: Fully Automated (Experimental)

For more automated processing:

```bash
python extract_tables_google_ai.py
```

**Note:** This script attempts full automation but may require manual intervention for:
- Google authentication
- UI element detection
- Response parsing

### Option 3: Manual Extraction

For complete control, follow the guide in `manual_extraction_guide.md`:

1. Go to https://aistudio.google.com/prompts/new_chat
2. Upload a PDF
3. Use the provided prompt template
4. Copy the JSON response
5. Save to `extractions/` folder

## Extraction Prompt

The scripts use this prompt for table extraction:

```
Please extract all tables from this PDF document in JSON format.

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
- Clean numeric values (remove currency symbols, convert European decimals)
- Handle merged cells appropriately
- Keep values as strings to preserve precision
- Return ONLY valid JSON, no markdown or code fences
```

## Output Format

Each extraction is saved as a JSON file:

```
{contract_id}_{hospital_name}_{year}_{timestamp}.json
```

Example:
```json
{
  "contract_id": "abc123",
  "hospital_name": "Hospital Santa Maria",
  "year": 2023,
  "extraction_timestamp": "20251031_123456",
  "data": {
    "extracted_tables": [
      {
        "table_index": 0,
        "page": 5,
        "table_data": [
          {
            "Item": "Produtos farmacêuticos",
            "Valor 2023": "1234567.89",
            "Valor 2022": "987654.32"
          }
        ]
      }
    ]
  }
}
```

## Troubleshooting

### Authentication Issues

**Problem:** Can't sign in to Google AI Studio  
**Solution:**
- Make sure you have a Google account with AI Studio access
- Try signing in manually in your browser first
- Clear browser cache/cookies if issues persist

### Upload Fails

**Problem:** PDF won't upload  
**Solution:**
- Check file size (may have limits)
- Verify PDF is not corrupted
- Try a smaller/different PDF first

### JSON Extraction Fails

**Problem:** Script can't extract JSON from response  
**Solution:**
- Check the screenshot in `extractions/step4_response.png`
- Manually copy JSON from browser
- Save to `extractions/manual_{contract_id}.json`
- Verify JSON is valid using a validator

### Playwright Issues

**Problem:** Browser automation fails  
**Solution:**
```bash
# Reinstall Playwright browsers
python -m playwright install --force chromium
```

### Rate Limiting

**Problem:** "Too many requests" error  
**Solution:**
- Add delays between requests
- Process smaller batches
- Wait and retry later

## Next Steps

After extraction:

1. **Validate Results**
   - Compare with original PDFs
   - Check for missing or incorrect data
   - Verify numeric values are properly formatted

2. **Update Database**
   - Store extracted tables in `llm_extracted_tables` column
   - Update `extraction_status` to 'completed'
   - Record any errors

3. **Quality Assurance**
   - Sample random extractions for accuracy
   - Compare with existing extraction methods
   - Refine prompt if needed

## Comparison with Existing Pipeline

This approach differs from the existing OpenAI/Document AI pipeline:

**Advantages:**
- Uses Google's latest Gemini models
- Web interface is free (no API costs)
- Can handle complex PDFs with images

**Disadvantages:**
- Requires manual authentication
- Slower due to web interface
- Less reliable automation
- No batch processing API

**Recommendation:**  
Use for:
- Testing and validation
- Small batches
- PDFs that fail with other methods
- Cost-sensitive projects

Use existing pipeline for:
- Large-scale processing
- Production workflows
- Automated pipelines
- Better error handling

## Resources

- [Google AI Studio](https://aistudio.google.com/)
- [Playwright Python Docs](https://playwright.dev/python/)
- [Gemini API Docs](https://ai.google.dev/)

