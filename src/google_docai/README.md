# Google Document AI - Table Extraction

Extract tables from PDF hospital agreements using Google Document AI Layout Parser.

## Architecture

```
extract_tables.py       # Main orchestrator
├── api_client.py      # Google Document AI API calls
├── filter_tables.py   # Extract tableBlock elements
├── transform_to_json.py # Transform to final JSON format
└── parse_values.py    # Parse European number formats
```

## Pipeline

1. **API Call** → Call Document AI Layout Parser
2. **Filter** → Extract only tableBlock elements
3. **Transform** → Convert to final JSON format with parsed values

## Setup

### 1. Install Dependencies

```bash
conda activate turing0.1
pip install google-auth google-auth-oauthlib
```

### 2. Configure OAuth Credentials

OAuth credentials are already configured in `.env`:
- `DOCAI_OAUTH_CLIENT_ID`
- `DOCAI_OAUTH_CLIENT_SECRET`

### 3. Authenticate

```bash
python setup_auth.py
```

This will:
- Open browser for OAuth login
- Save credentials to `~/.google_docai_credentials.json`

## Usage

### Test Single Contract

```bash
python test_single.py
```

This will:
- Process first contract from CSV
- Save intermediate files: `debug_api_response.json`, `debug_filtered_tables.json`
- Save final output: `test_output.json`

### Extract All Tables

```python
from extract_tables import create_creds, extract_tables_from_pdf

creds = create_creds()
tables = extract_tables_from_pdf(
    pdf_path="path/to/file.pdf",
    credentials=creds,
    verbose=True,
    save_intermediate=True
)
```

## Output Format

```json
{
  "contract_id": "...",
  "tables": [
    {
      "table_id": "1",
      "page": 1,
      "rows": [
        {
          "row_name": "Row label",
          "Column1": 1234.56,
          "Column2": 95.5
        }
      ]
    }
  ]
}
```

## Value Parsing

European formats are automatically parsed:
- `€ 1.234,56` → `1234.56` (float)
- `95,5%` → `95.5` (float)
- `1.234` → `1234` (int)
- `-`, `N/A` → `null`

## Cost

- **Price**: $10 per 1000 pages
- **731 PDFs estimate**: ~$164 (assuming avg 16 pages per PDF)
