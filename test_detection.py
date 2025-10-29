import os
from dotenv import load_dotenv
from openai import OpenAI
from src.PROMPTS import TABLE_DETECTION_PROMPT

load_dotenv()

# Read the OCR text from page 3
with open("page3_ocr.txt", "r", encoding="utf-8") as f:
    ocr_text = f.read()

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

print("Testing table detection on page 3 OCR text...")
print(f"Text length: {len(ocr_text)} chars\n")

prompt = TABLE_DETECTION_PROMPT.format(text=ocr_text[:2000])

print("Prompt:")
print("="*80)
print(prompt)
print("="*80)

print("\nCalling gpt-5-nano...")
response = client.chat.completions.create(
    model="gpt-5-nano",
    messages=[{"role": "user", "content": prompt}],
    max_completion_tokens=100
)

print(f"Full response: {response}")
print(f"\nChoice 0: {response.choices[0]}")
result = response.choices[0].message.content
print(f"\nGPT-5-nano response: '{result}'")
print(f"Response length: {len(result) if result else 0}")
if result:
    print(f"Upper: '{result.upper()}'")
    print(f"'YES' in result: {'YES' in result.upper()}")
