# Table Extraction Schema & Pipeline

## Overview
3-tier extraction approach for both text-based and image-based PDFs.

---

## Extraction Flow

### Tier 1: Text-based PDFs (Camelot)
**When**: PDF contains selectable text and structured tables
**Method**: Camelot with `lattice` flavor
**Speed**: Fast (~1-2 sec/page)

```
PDF → Camelot → Clean JSON
```

### Tier 2: Image-based PDFs (Google Vision + GPT)
**When**: Camelot fails (scanned/image PDFs)
**Method**: Google Vision OCR → GPT-4o-mini structuring
**Speed**: Medium (~5-10 sec/page)

```
PDF → Convert to Images → Google Vision OCR → Extract Text → GPT-4o-mini → Clean JSON
```

**Steps**:
1. Convert PDF page to image (200 DPI)
2. Google Vision OCR extracts all text
3. Pass text to GPT-4o-mini with 2 prompts:
   - **Prompt 1 (Detection)**: "Does this text represent a table? TRUE/FALSE"
   - **Prompt 2 (Extraction)**: "Extract table into JSON format"

---

## JSON Output Schema

### Structure
```json
{
  "contract_id": "uuid-or-identifier",
  "tables": [
    {
      "table_id": "table_0",
      "page": 3,
      "rows": [
        {
          "row_name": "Description text",
          "Column Header 1": value_or_null,
          "Column Header 2": value_or_null,
          "Column Header 3": value_or_null
        }
      ]
    }
  ]
}
```

### Example (HDS Hospital Agreement Page 3)
```json
{
  "contract_id": "HDS_2023",
  "tables": [
    {
      "table_id": "table_0",
      "page": 3,
      "rows": [
        {
          "row_name": "Nº de 1ªs consultas médicas (s/ majoração)",
          "ICM": null,
          "N.º": null,
          "%": null,
          "Preço Unitário (€)": 49.0,
          "Quantidade": 23664,
          "Valor (€)": 1159536.0
        },
        {
          "row_name": "Nº de 1ªs consultas referenciadas (CTH)",
          "ICM": null,
          "N.º": null,
          "%": null,
          "Preço Unitário (€)": 54.0,
          "Quantidade": 18644,
          "Valor (€)": 1006776.0
        }
      ]
    }
  ]
}
```

---

## Column Naming Rules

1. **First Column**: Always `"row_name"` (contains row description)
2. **Other Columns**: Use exact header text from PDF
3. **Empty Headers**: Use `"col_N"` where N is column index
4. **Special Characters**: Keep original (€, %, º, etc.)

---

## Value Parsing Rules

### Currency (€)
- Input: `"€ 1.234,56"` or `"1.234,56 €"`
- Steps:
  1. Remove `€` symbol
  2. Remove spaces
  3. Remove thousand separators (`.`)
  4. Replace decimal comma (`,`) with period (`.`)
- Output: `1234.56` (float)

### Percentages (%)
- Input: `"95,5%"` or `"95.5 %"`
- Steps:
  1. Remove `%` symbol
  2. Remove spaces
  3. Replace comma with period
- Output: `95.5` (float)

### Integers
- Input: `"1.234"` or `"1 234"`
- Steps:
  1. Remove spaces
  2. Remove thousand separators (`.`)
- Output: `1234` (int)

### Decimals
- Input: `"1.234,56"`
- Steps:
  1. Remove spaces
  2. Remove thousand separators (`.`)
  3. Replace comma with period
- Output: `1234.56` (float)

### Text
- Input: Any non-numeric string
- Output: Keep as-is (string)

### Empty Cells
- Output: `null`

---

## GPT Prompts

### Prompt 1: Table Detection
```
Given the following OCR text from a PDF page, determine if it contains a structured table with rows and columns.

TEXT:
{ocr_text}

Respond with ONLY "TRUE" if this represents a table, or "FALSE" if not.
```

### Prompt 2: Table Extraction
```
Extract the table data from this OCR text and convert it to JSON format.

OCR TEXT:
{ocr_text}

Required JSON structure:
{
  "rows": [
    {
      "row_name": "description from first column",
      "Column Header 1": value_or_null,
      "Column Header 2": value_or_null
    }
  ]
}

Rules:
1. First column data goes in "row_name"
2. Use exact column headers from the text
3. Parse numbers correctly (remove € and %, convert to float/int)
4. Empty cells = null
5. Preserve special characters in headers

Respond with ONLY valid JSON, no markdown or explanation.
```

---

## Cost Analysis

### Per 731 PDFs (assuming 70% image-based)

**Google Vision OCR**:
- ~512 image-based PDFs × 5 pages average = 2,560 pages
- Free tier: 1,000 pages/month
- Paid: $1.50/1,000 pages after free tier
- **Cost**: ~$2.34

**GPT-4o-mini**:
- Detection: 512 PDFs × 5 pages × ~500 tokens = 1.28M tokens
- Extraction: ~512 tables × ~1,500 tokens = 0.77M tokens
- Total: ~2.05M tokens
- **Cost**: ~$0.31 (input) + ~$0.62 (output) = **$0.93**

**Total**: ~$3.30 for full pipeline

---

## Error Handling

### Camelot Fails
→ Fall back to Google Vision + GPT

### Google Vision Fails
→ Log error: `{"error": "OCR failed"}`

### GPT Detection = FALSE
→ Skip page (no table)

### GPT Extraction Fails
→ Log error: `{"error": "Table extraction failed"}`

### Invalid JSON from GPT
→ Retry once, then log error

---

## Performance Targets

- **Camelot (text PDFs)**: 1-2 sec/page
- **Vision OCR**: 3-5 sec/page
- **GPT Processing**: 2-3 sec/table
- **Total**: ~10 sec/page (worst case)

**Estimated Runtime**: 2-3 hours for 731 PDFs

---

## Files Modified

1. `1_extract_tables.py` - Main extraction logic
2. `hospital_agreements_with_tables.csv` - Output with JSON column
3. Error logs - `extraction_errors.log`
