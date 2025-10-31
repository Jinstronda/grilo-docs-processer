import pandas as pd
import camelot
import json
import re
import requests
import tempfile
import os
import warnings
from pathlib import Path
from google.cloud import vision
from google.oauth2 import service_account
from dotenv import load_dotenv

warnings.filterwarnings('ignore')
load_dotenv()

def create_creds():
    """Create Google credentials from .env (<25 lines)"""
    return service_account.Credentials.from_service_account_info({
        "type": "service_account",
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace('\\n', '\n'),
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "token_uri": "https://oauth2.googleapis.com/token",
    })

def parse_val(text):
    """Parse cell value by type (<25 lines)"""
    if not text or not isinstance(text, str):
        return text
    text = text.strip().replace('\n', ' ')
    if '€' in text:
        try:
            return float(text.replace('€', '').replace(' ', '').replace('.', '').replace(',', '.')) or text
        except:
            return text
    if '%' in text:
        try:
            return float(text.replace('%', '').replace(' ', '').replace(',', '.')) or text
        except:
            return text
    if re.match(r'^[\d\s.]+$', text):
        try:
            return int(text.replace(' ', '').replace('.', '')) or text
        except:
            return text
    if ',' in text and re.match(r'^[\d\s.,]+$', text):
        try:
            return float(text.replace(' ', '').replace(',', '.')) or text
        except:
            return text
    return text

def fetch_pdf(url):
    """Download PDF from URL (<25 lines)"""
    temp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        temp.write(r.content)
        temp.flush()
        return temp.name
    except Exception as e:
        print(f"Download error: {e}")
        return None

def try_camelot(pdf_path):
    """Try camelot extraction (<25 lines)"""
    try:
        tables = camelot.read_pdf(pdf_path, flavor='lattice', pages='all', suppress_stdout=True)
        if len(tables) == 0:
            return []

        result = []
        for i, t in enumerate(tables):
            df = t.df
            if df.empty or len(df) < 2:
                continue

            headers = [str(h).strip() for h in df.iloc[0].tolist()]
            rows = []

            for idx in range(1, len(df)):
                row_dict = {}
                first_col = df.iloc[idx, 0]
                row_dict["row_name"] = parse_val(first_col) if first_col else None

                for j in range(1, len(headers)):
                    col_name = headers[j] if headers[j] else f"col_{j}"
                    cell_val = df.iloc[idx, j]
                    row_dict[col_name] = parse_val(cell_val) if cell_val and str(cell_val).strip() else None

                rows.append(row_dict)

            result.append({"table_id": f"table_{i}", "page": t.parsing_report['page'], "rows": rows})
        return result
    except:
        return []

def try_vision_ocr(pdf_path, creds):
    """Extract tables using Google Vision OCR (<25 lines)"""
    try:
        client = vision.ImageAnnotatorClient(credentials=creds)
        with open(pdf_path, 'rb') as f:
            content = f.read()

        config = vision.InputConfig(content=content, mime_type='application/pdf')
        features = [vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)]
        req = vision.AnnotateFileRequest(input_config=config, features=features, pages=[1, 2, 3, 4, 5])
        resp = client.batch_annotate_files(requests=[req])

        tables = []
        for i, page in enumerate(resp.responses[0].responses, 1):
            if page.full_text_annotation:
                text = page.full_text_annotation.text
                table = parse_ocr_to_table(text, i)
                if table:
                    tables.append(table)
        return tables
    except Exception as e:
        print(f"Vision OCR error: {e}")
        return []

def parse_ocr_to_table(text, page_num):
    """Convert OCR text to table structure (<25 lines)"""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) < 2:
        return None

    rows = []
    for line in lines:
        parts = re.split(r'\s{2,}|\t', line)
        if len(parts) > 1:
            row = {f"col_{j}": parse_val(p) for j, p in enumerate(parts)}
            rows.append(row)

    return {"table_id": f"table_{page_num}", "page": page_num, "rows": rows} if rows else None

def process_row(row, creds):
    """Process one CSV row (<25 lines)"""
    try:
        url = row.get('original_pdf_url', '')
        if not url:
            return json.dumps({"error": "No URL"})

        pdf_path = fetch_pdf(url)
        if not pdf_path:
            return json.dumps({"error": "Download failed"})

        tables = try_camelot(pdf_path)
        if not tables:
            tables = try_vision_ocr(pdf_path, creds)

        Path(pdf_path).unlink(missing_ok=True)
        return json.dumps({"contract_id": row.get('id'), "tables": tables}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Failed: {str(e)}"})

def main(test_mode=True):
    """Main function"""
    csv_path = r"C:\Users\joaop\Documents\Augusta Labs\Grilo Pdf Extraction\hospital_agreements.csv"
    output_path = r"C:\Users\joaop\Documents\Augusta Labs\Grilo Pdf Extraction\hospital_agreements_with_tables.csv"

    creds = create_creds()
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows")

    if test_mode:
        df = df.head(3)
        output_path = output_path.replace('.csv', '_test.csv')
        print(f"TEST MODE: Processing {len(df)} rows\n")
    else:
        print(f"Processing ALL {len(df)} rows...\n")

    results = []
    for idx, row in df.iterrows():
        result = process_row(row, creds)
        results.append(result)

        if (idx + 1) % 10 == 0 or test_mode:
            print(f"Processed {idx + 1}/{len(df)}")

        data = json.loads(result)
        if 'error' not in data and len(data.get('tables', [])) > 0:
            print(f"  Row {idx}: {len(data['tables'])} tables")
        elif test_mode and 'error' in data:
            print(f"  Row {idx}: {data['error']}")

    df['json_non_normalized'] = results
    df.to_csv(output_path, index=False)
    print(f"\nDone! Saved to: {output_path}")

if __name__ == "__main__":
    main()
