# Hospital PDF Table Extraction Pipeline

## Architecture

```
hospital_agreements.csv (731 PDFs)
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 1: Extract Tables                    │
│ File: 1_extract_tables.py                  │
│ Flow: Google Vision → gpt-5-nano → gpt-5-mini │
└─────────────────────────────────────────────┘
    ↓
extracted_tables.csv
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 2: Group Similar Tables              │
│ File: 2_group_similar_tables.py            │
│ Method: TF-IDF + Cosine Similarity         │
└─────────────────────────────────────────────┘
    ↓
table_groups.json
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 3: Normalize with LLM                │
│ File: 3_normalize_with_llm.py              │
│ Model: gpt-5-mini                           │
└─────────────────────────────────────────────┘
    ↓
hospital_agreements_normalized.csv
```

## Stage 1: Table Extraction

**3-Step Extraction Flow:**

1. **Google Vision OCR**: Extract text from PDF page images
2. **gpt-5-nano Detection**: Binary check if page contains table (YES/NO)
3. **gpt-5-mini Extraction**: If YES → Extract table structure to JSON

**Detailed Flow:**
```
PDF → Convert to images (200 DPI)
    ↓
For each page:
    ↓
Google Vision API → OCR text extraction
    ↓
gpt-5-nano: "Does this text contain a table?" → YES/NO
    ↓
If YES:
    gpt-5-mini: Extract table to normalized JSON
    ↓
Combine all tables from all pages
```

**Output Schema:**
```json
{
  "contract_id": "uuid",
  "tables": [{
    "table_id": "table_0",
    "page": 3,
    "rows": [
      {"row_name": "Description", "Column1": 1234.56, "Column2": null}
    ]
  }]
}
```

**Value Parsing (in gpt-5-mini prompt):**
- `€ 1.234,56` → `1234.56` (float)
- `95,5%` → `95.5` (float)
- Empty cells → `null`

**Functions (<25 lines each):**
- `extract_ocr_text()` - Google Vision OCR
- `detect_table()` - gpt-5-nano binary detection
- `extract_table_json()` - gpt-5-mini structured extraction
- `parse_val()` - Post-process value parsing
- `process_page()` - Page orchestrator
- `process_pdf()` - PDF orchestrator

**Output:** `extracted_tables.csv` (id, tables_json)

## Stage 2: Table Grouping

**Similarity Method:**
- Extract column names from each table
- Vectorize using TF-IDF
- Calculate cosine similarity matrix
- Group tables with similarity > 0.7

**Functions (<25 lines each):**
- `load_tables()` - Parse Stage 1 output
- `extract_headers()` - Get column names
- `calculate_similarity()` - TF-IDF + cosine
- `group_tables()` - Cluster similar tables

**Output:** `table_groups.json`
```json
{
  "group_1": [table_ids],
  "group_2": [table_ids]
}
```

## Stage 3: LLM Normalization

**GPT-4 Task:**
1. Analyze tables in each group
2. Generate unified schema (column names, types)
3. Create mapping rules (old → new column names)

**Functions (<25 lines each):**
- `normalize_group_with_gpt4()` - Get schema from GPT-4
- `apply_normalization()` - Transform tables
- `merge_to_csv()` - Combine all groups

**Output:** `hospital_agreements_normalized.csv` (unified schema)

## Cost & Performance

**Google Vision OCR (Stage 1):**
- 731 PDFs × ~5 pages/PDF = ~3,655 images
- $1.50/1K images = ~$5.50

**gpt-5-nano Detection (Stage 1):**
- ~3,655 pages × ~100 tokens/check = ~365K tokens
- Cost: TBD (lightweight model)

**gpt-5-mini Extraction (Stage 1):**
- ~1,000 tables × ~500 tokens = ~500K tokens
- Cost: TBD (no temperature parameter)

**gpt-5-mini Normalization (Stage 3):**
- ~50 table groups × 1K tokens = 50K tokens
- Cost: TBD

**Total:** ~$6-8 | **Time:** ~2-3 hours

## Execution

```bash
# Test mode (3 PDFs)
python 1_extract_tables.py --test
python 2_group_similar_tables.py --input extracted_tables.csv --test
python 3_normalize_with_llm.py --input table_groups.json --test

# Production (all 731)
python 1_extract_tables.py
python 2_group_similar_tables.py --input extracted_tables.csv
python 3_normalize_with_llm.py --input table_groups.json
```

## Dependencies

```bash
pip install google-cloud-vision pdf2image openai scikit-learn pandas python-dotenv
```

**Required:**
- Poppler installed (for pdf2image)
- `.env` with:
  - `OPENAI_API_KEY` (for gpt-5-nano and gpt-5-mini)
  - `GOOGLE_PROJECT_ID`, `GOOGLE_CLIENT_EMAIL`, `GOOGLE_PRIVATE_KEY`

## Test Case

**File:** `HDS_Adenda2023-Homologada (1).pdf` page 3

**Expected Output:**
```json
{
  "table_id": "table_0",
  "page": 3,
  "rows": [
    {"row_name": "Internamento", "Doentes Equivalentes ICM N.º": 1234, "%": 95.5, "Preço Unitário (€)": 100.50}
  ]
}
```
