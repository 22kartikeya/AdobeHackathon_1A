import fitz  # PyMuPDF
import pdfplumber
import json
import os

def extract_title(doc):
    """Extract title based on the largest font size in the first page."""
    blocks = doc[0].get_text("dict")["blocks"]
    max_font_size = 0
    title_text = ""
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span["size"] > max_font_size:
                    max_font_size = span["size"]
                    title_text = span["text"]
    return title_text.strip()

def detect_tables(pdf_path):
    """Check if any page in the PDF contains tables."""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            if tables:
                return True
    return False

def extract_outline(doc):
    """Build outline based on font sizes heuristically."""
    font_sizes = {}
    outline = []

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    size = round(span["size"])
                    if text:
                        font_sizes.setdefault(size, []).append(text)

    # Get top 3 sizes and label them as H1, H2, H3
    sorted_sizes = sorted(font_sizes.keys(), reverse=True)
    size_to_tag = {size: f"H{i+1}" for i, size in enumerate(sorted_sizes[:3])}

    for size in sorted_sizes[:3]:
        tag = size_to_tag[size]
        for text in font_sizes[size]:
            outline.append({"type": tag, "text": text})

    return outline

def main():
    input_path = "input/file02.pdf"
    output_path = "output/output2.json"

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"{input_path} not found")

    doc = fitz.open(input_path)
    title = extract_title(doc)
    tables_present = detect_tables(input_path)
    outline = [] if tables_present else extract_outline(doc)

    output = {
        "title": title,
        "outline": outline
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✔️ Output written to: {output_path}")

if __name__ == "__main__":
    main()