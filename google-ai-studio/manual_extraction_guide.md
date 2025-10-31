# Google AI Studio Manual Extraction Guide

## Overview

This guide explains how to use Google AI Studio to extract tables from PDFs. Since Google AI Studio requires authentication and has a dynamic web interface, this document provides both manual and semi-automated approaches.

## Setup

### Prerequisites

1. Google Account with access to [Google AI Studio](https://aistudio.google.com/)
2. Python environment with required packages:
   ```bash
   pip install playwright requests
   python -m playwright install chromium
   ```

### Authentication

Google AI Studio requires Google account authentication. The automation script will:
1. Open a browser window
2. Navigate to Google AI Studio
3. Wait for you to sign in manually
4. Continue with automation after sign-in

## Manual Process

### Step 1: Access Google AI Studio

1. Go to https://aistudio.google.com/prompts/new_chat
2. Sign in with your Google account
3. Wait for the chat interface to load

### Step 2: Upload PDF

1. Look for the attachment/upload button (usually a paperclip or plus icon)
2. Click the button and select your PDF file
3. Wait for the file to upload

### Step 3: Enter Extraction Prompt

Use this prompt:

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
- Clean numeric values (remove currency symbols like €, convert European decimals from 1.234,56 to 1234.56)
- Handle merged cells appropriately
- Keep values as strings to preserve precision
- Return ONLY valid JSON, no markdown or code fences
```

### Step 4: Get Response

1. Click Send or press Enter
2. Wait for the AI to process the PDF and respond
3. Copy the JSON response

### Step 5: Save Results

Save the JSON response to a file in the `extractions` folder with the naming convention:
```
{contract_id}_{hospital_name}_{year}_{timestamp}.json
```

## Automated Process

### Using the Python Script

```bash
cd google-ai-studio
python extract_tables_google_ai.py
```

The script will:
1. Query the database for contracts with PDFs
2. Download each PDF to a temporary location
3. Open a browser window to Google AI Studio
4. **Pause for you to sign in manually**
5. Attempt to automate the upload and extraction process
6. Save results to the `extractions` folder

### Script Limitations

The automation has limitations due to:
- Google authentication requirements
- Dynamic UI that may change
- Rate limits on AI Studio API

You may need to manually complete some steps when the script pauses.

## Understanding the UI

### Chrome DevTools Inspection

To better understand the Google AI Studio interface for automation:

1. Open Google AI Studio in your browser
2. Press F12 to open DevTools
3. Inspect elements to find:
   - File upload input: `input[type="file"]`
   - Prompt textarea: `textarea` or `[contenteditable="true"]`
   - Send button: `button[type="submit"]` or similar
   - Response container: varies by implementation

### Key UI Elements to Locate

- **File Upload Button**: Look for paperclip, attach, or plus icon
- **Prompt Input**: Large text area for entering prompts
- **Send Button**: Button to submit the prompt
- **Response Area**: Where the AI output appears
- **Copy Button**: To copy the response JSON

## Troubleshooting

### Authentication Issues

**Problem**: Can't sign in or session expires  
**Solution**: 
- Clear browser cache and cookies
- Sign in manually first in your default browser
- Use an incognito/private window if needed

### Upload Fails

**Problem**: PDF won't upload  
**Solution**:
- Check file size (Google AI Studio may have limits)
- Verify PDF is not corrupted
- Try a different browser
- Check network connection

### Invalid JSON Response

**Problem**: Response is not valid JSON  
**Solution**:
- Ask AI to regenerate response
- Manually clean up the JSON
- Check for markdown code fences and remove them
- Use a JSON validator

### Rate Limiting

**Problem**: "Too many requests" or similar error  
**Solution**:
- Add delays between requests
- Process smaller batches
- Use API access if available
- Wait and retry later

## Next Steps

After extraction:

1. **Validate Results**: Compare extracted tables with original PDF
2. **Store in Database**: Update the `llm_extracted_tables` column
3. **Quality Check**: Review sample extractions for accuracy
4. **Iterate**: Refine the prompt if needed

## Alternative Approaches

If Google AI Studio automation proves difficult:

1. **Google Cloud Document AI**: Use the existing pipeline with better error handling
2. **Claude/GPT Vision API**: Direct API calls with PDF upload
3. **Local LLM**: Use open-source models like LLaVA for table extraction
4. **Hybrid Approach**: Use Document AI for OCR, then LLM for structuring

## Resources

- [Google AI Studio Documentation](https://ai.google.dev/tutorials/ai-studio_quickstart)
- [Playwright Documentation](https://playwright.dev/python/)
- [Chrome DevTools Guide](https://developer.chrome.com/docs/devtools/)

