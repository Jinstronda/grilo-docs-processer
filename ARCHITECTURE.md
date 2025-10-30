# System Architecture

## Two-Phase Extraction Pipeline

### Phase 1: Google Document AI (Table Detection)

**Input:** PDF files from CSV  
**Process:** Google Document AI Layout Parser API  
**Output:** Raw JSON with tableBlocks  
**Stored in:** `data/hospital_tables.db` column `raw_json`

```
PDF → Google Document AI → Raw JSON (tableBlocks) → Database
```

**What it does:**
- Detects all tables in PDF (most of the tables are images so we needed to use the docs ai)
- Preserves exact structure (merged cells, headers, all text)
- Handles scanned PDFs and native PDFs
- Returns nested JSON with cell-level granularity

**Script:** `main_extraction_pipeline_async.py`
- 5 concurrent workers
- GCS path optimization
- Auto-trims PDFs >30 pages (Keeping the last pages bcs they have the tables)
- Resume support

### Phase 2: Gemini 2.5 Flash (Data Formatting)

**Input:** Raw JSON from database  
**Process:** Pre-filter tableBlocks → Gemini 2.5 Flash → Parse response  
**Output:** Clean structured JSON  
**Stored in:** `data/hospital_tables.db` column `llm_extracted_tables`

```
Raw JSON → Filter tableBlocks → Gemini LLM → Structured JSON → Database
```

**What it does:**
- Filters out non-table blocks (7.5% size reduction)
- Sends only tableBlocks to LLM
- LLM extracts data, splits merged cells, cleans numbers
- Handles ID-Description patterns (616-Matérias → ItemID + ItemDesc)
- Cleans European formats (12.706.784,46 € → 12706784.46)

**Script:** `llm_extract_tables_openai.py` (uses Gemini despite name)
- 5 concurrent workers
- Unlimited output tokens
- Handles thinking tags
- Numbered test outputs

## File Organization

```
grilo-pdf-extraction/
├── main_extraction_pipeline_async.py     # Phase 1: Extract raw JSON
├── llm_extract_tables_openai.py          # Phase 2: Parse with Gemini
├── README.md                             # Main documentation
├── requirements.txt                      # Dependencies
│
├── data/
│   ├── hospital_agreements.csv           # Input (731 contracts)
│   └── hospital_tables.db                # Output (raw_json + llm_extracted_tables)
│
├── src/google_docai/                     # Core extraction (Phase 1)
│   ├── api_client.py                     # Document AI API calls
│   ├── extract_tables.py                 # Pipeline orchestration
│   ├── filter_tables.py                  # Recursive tableBlock extraction
│   └── setup_auth.py                     # OAuth setup
│
└── samples/                              # Test outputs
    ├── test_XXX_filtered_input.json      # Input to Gemini
    ├── test_XXX_gemini_output.json       # Output from Gemini
    └── test_XXX_info.txt                 # Test metadata
```

## Database Schema

```sql
contracts (
    -- Input data
    id TEXT PRIMARY KEY,
    hospital_name TEXT,
    year INTEGER,
    original_pdf_url TEXT,
    gcs_pdf_path TEXT,
    
    -- Phase 1 output
    raw_json TEXT,              -- Complete Google API response
    extraction_status TEXT,     -- 'success', 'failed', 'pending'
    num_tables INTEGER,
    
    -- Phase 2 output
    llm_extracted_tables TEXT   -- Gemini parsed tables
)
```

## Why Two Phases

**Separation of Concerns:**
- Google Document AI: Expert at OCR and table detection
- Gemini LLM: Expert at data extraction and cleaning

**Benefits:**
- Can iterate on parsing (Phase 2) without re-processing PDFs
- Raw JSON preserved for future improvements
- Each phase optimized for its task
- Failure in one phase doesn't affect the other

**Cost Optimization:**
- Pre-filtering reduces Gemini input size
- Saves ~60% on LLM costs
- Google API cost is one-time
- LLM parsing can be retried cheaply

## Data Flow

```
hospital_agreements.csv (731 contracts)
    ↓
Phase 1: main_extraction_pipeline_async.py
    ├─ Download or use GCS path
    ├─ Trim if >30 pages
    ├─ Call Google Document AI
    └─ Store raw_json
    ↓
data/hospital_tables.db (raw_json column)
    ↓
Phase 2: llm_extract_tables_openai.py
    ├─ Load raw_json from database
    ├─ Filter to tableBlocks only
    ├─ Send to Gemini 2.5 Flash
    ├─ Parse response (handle thinking tags)
    └─ Store llm_extracted_tables
    ↓
data/hospital_tables.db (llm_extracted_tables column)
    ↓
Query and analyze clean structured data
```

## Performance

**Phase 1:**
- Time: ~25 minutes (731 contracts, 5 workers)
- Cost: ~$37 (Google Document AI)
- Success: 729/731 (99.7%)

**Phase 2:**
- Time: ~15-20 minutes (729 contracts, 5 workers)
- Cost: ~$6 (with pre-filtering)
- Output: Clean JSON tables

**Total:** ~40 minutes, ~$43 for complete pipeline

## Core Components

### Phase 1 Components

**`api_client.py`** - Google Document AI API
- Handles authentication
- Supports local files and GCS URIs
- Retry logic with backoff
- ~114 lines

**`extract_tables.py`** - Pipeline orchestration
- Downloads PDFs
- Trims if needed
- Calls API
- Returns raw JSON
- ~218 lines

**`filter_tables.py`** - Recursive table extraction
- Searches for tableBlocks at any nesting level
- Preserves blockId and pageSpan
- ~86 lines

**`setup_auth.py`** - OAuth authentication
- Browser-based OAuth flow
- Saves credentials locally
- ~63 lines

### Phase 2 Components

**`llm_extract_tables_openai.py`** - Gemini extraction (single file)
- Filters tableBlocks
- Calls Gemini API
- Parses response
- Handles thinking tags
- Async worker pool
- ~630 lines

## Testing

**Phase 1 test:**
```bash
python main_extraction_pipeline_async.py --limit 1
```

**Phase 2 test:**
```bash
python llm_extract_tables_openai.py --test
```

**Test outputs saved to:** `samples/test_XXX_*`

---

**System Status:** Production ready. Phase 1 complete (729/731). Phase 2 configured with Gemini 2.5 Flash.

