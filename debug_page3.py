import os
from dotenv import load_dotenv
from pdf2image import convert_from_path
import importlib.util

load_dotenv()

# Import extraction module
spec = importlib.util.spec_from_file_location("extract", "src/1_extract_tables.py")
extract_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract_module)

pdf_path = r"c:\Users\joaop\Desktop\Content Creation stuff\HDS_Adenda2023-Homologada (1).pdf"
creds = extract_module.create_creds()

print("Converting page 3 to image...")
images = convert_from_path(pdf_path, dpi=200, first_page=3, last_page=3)
image = images[0]

print("Extracting OCR text...")
ocr_text = extract_module.extract_ocr_text(image, creds)

print(f"\nOCR Text ({len(ocr_text)} chars):")
print("="*80)
print(ocr_text)
print("="*80)

# Save to file
with open("page3_ocr.txt", "w", encoding="utf-8") as f:
    f.write(ocr_text)

print("\nSaved to page3_ocr.txt")
