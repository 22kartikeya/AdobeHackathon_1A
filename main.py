# main.py
import json
import os
from pathlib import Path
import fitz
from src.extractor import extract_outline, extract_title, detect_tables

if os.environ.get("RUN_IN_CONTAINER") == "1":
    INPUT_DIR = Path("/app/input")
    OUTPUT_DIR = Path("/app/output")
else:
    INPUT_DIR = Path("app/input")
    OUTPUT_DIR = Path("app/output")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)



def main():
    pdf_files = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        print("No PDFs found in /app/input")
        return

    for pdf_path in pdf_files:
        print(f"Processing {pdf_path.name}")
        doc = fitz.open(pdf_path)

        title = extract_title(doc)
        tables_present = detect_tables(pdf_path)
        outline = [] if tables_present else extract_outline(doc)

        result = {
            "title": title,
            "outline": outline
        }

        out_path = OUTPUT_DIR / (pdf_path.stem + ".json")
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f" → Saved {out_path.relative_to(OUTPUT_DIR.parent)}")


if __name__ == "__main__":
    main()
