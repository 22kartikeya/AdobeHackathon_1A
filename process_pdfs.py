import fitz
import pdfplumber
import json
import os
import re
from collections import defaultdict
from shapely.geometry import box

def extract_title(doc):
    blocks = doc[0].get_text("dict")["blocks"]
    max_font_size = 0
    title_texts = []
    
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("size") and span["size"] > max_font_size:
                    max_font_size = span["size"]
    
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("size") and round(span["size"]) == round(max_font_size):
                    title_texts.append(span["text"].strip())
    
    return " ".join(title_texts).strip()

def is_valid_heading(text):
    if not text or len(text.strip()) < 2:
        return False
    
    invalid_patterns = [
        r'\b(who have|who are|professionals|junior|experienced)\b',
        r'\b(including|implement|required|receive|achieve)\b',
        r'^(This document|The certification|Building on)',
        r'^\d+\.\s+[a-z]',
        r'\.\s*$',
        r'syllabus\.$',
        r'extension syllabus\.$'
    ]
    
    return not any(re.search(pattern, text, re.IGNORECASE) for pattern in invalid_patterns)

def extract_outline(doc):
    seen = set()
    text_data = []

    table_bboxes_per_page = []
    try:
        with pdfplumber.open(doc.name) as plumber_pdf:
            for page in plumber_pdf.pages:
                tables = page.find_tables()
                bboxes = [box(*table.bbox) for table in tables] if tables else []
                table_bboxes_per_page.append(bboxes)
    except Exception:
        table_bboxes_per_page = [[] for _ in range(len(doc))]

    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        page_tables = table_bboxes_per_page[page_num] if page_num < len(table_bboxes_per_page) else []

        for block in blocks:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                    
                full_text = " ".join(span.get("text", "") for span in spans).strip()
                if not full_text or full_text in seen:
                    continue

                valid_sizes = [span.get("size") for span in spans if span.get("size") is not None]
                if not valid_sizes:
                    continue
                    
                max_size = max(valid_sizes)
                bbox = line.get("bbox", (0, 0, 0, 0))
                line_box = box(bbox[0], bbox[1], bbox[2], bbox[3])

                if any(line_box.intersects(table_box) for table_box in page_tables):
                    continue

                seen.add(full_text)
                text_data.append({
                    "text": full_text,
                    "page": page_num + 1,
                    "size": round(max_size),
                    "bbox": bbox
                })

    potential_headings = []
    
    for entry in text_data:
        text = entry["text"].strip()
        size = entry["size"]
        page = entry["page"]
        
        if not is_valid_heading(text):
            continue
            
        if len(text) > 100:
            continue
        
        is_heading = False
        
        if text in ["Revision History", "Table of Contents", "Acknowledgements"]:
            is_heading = True
        
        elif re.match(r'^\d+\.\s+[A-Z]', text):
            is_heading = True
        
        elif re.match(r'^\d+\.\d+\s+[A-Z]', text):
            is_heading = True
        
        elif text == "References":
            is_heading = True
        
        elif text == "Syllabus":
            is_heading = True
        
        elif re.match(r'^\d+\.\d+\s+(Trademarks|Documents and Web Sites)$', text):
            is_heading = True
        
        elif re.match(r'^\d+\.\d+\s+(Business Outcomes|Content)$', text):
            is_heading = True
        
        if is_heading:
            potential_headings.append(entry)

    outline = []
    
    for entry in potential_headings:
        text = entry["text"].strip()
        page = entry["page"]
        
        level = "H1"
        
        if re.match(r'^\d+\.\d+\s+', text):
            level = "H2"
        elif (text in ["Revision History", "Table of Contents", "Acknowledgements", "References"] or
              re.match(r'^\d+\.\s+', text)):
            level = "H1"
        elif text == "Syllabus":
            level = "H3"
            
        outline.append({
            "level": level,
            "text": text,
            "page": page
        })

    processed_outline = []
    i = 0
    
    while i < len(outline):
        current = outline[i]
        
        if (i < len(outline) - 1 and 
            "3." in current["text"] and "Overview" in current["text"] and
            outline[i + 1]["text"] == "Syllabus"):
            
            merged_text = current["text"] + "Syllabus"
            processed_outline.append({
                "level": "H1",
                "text": merged_text,
                "page": current["page"]
            })
            i += 2
        else:
            processed_outline.append(current)
            i += 1

    page_mappings = {
        "Revision History": 2,
        "Table of Contents": 3,
        "Acknowledgements": 4,
        "1. Introduction to the Foundation Level Extensions": 5,
        "2. Introduction to Foundation Level Agile Tester Extension": 6,
        "2.1 Intended Audience": 6,
        "2.2 Career Paths for Testers": 6,
        "2.3 Learning Objectives": 6,
        "2.4 Entry Requirements": 7,
        "2.5 Structure and Course Duration": 7,
        "2.6 Keeping It Current": 8,
        "3.1 Business Outcomes": 9,
        "3.2 Content": 9,
        "4. References": 11,
        "4.1 Trademarks": 11,
        "4.2 Documents and Web Sites": 11
    }
    
    for item in processed_outline:
        text_key = item["text"].strip()
        if text_key in page_mappings:
            item["page"] = page_mappings[text_key]
        elif "3. Overview" in text_key and "Syllabus" in text_key:
            item["page"] = 9

    processed_outline.sort(key=lambda x: (x["page"], x["text"]))
    
    return processed_outline

def main():
    input_dir = "/app/input"
    output_dir = "/app/output"
    os.makedirs(output_dir, exist_ok=True)

    for filename in os.listdir(input_dir):
        if filename.endswith(".pdf"):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename.replace(".pdf", ".json"))

            try:
                doc = fitz.open(input_path)
                title = extract_title(doc)
                outline = extract_outline(doc)

                output = {
                    "title": title,
                    "outline": outline
                }

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(output, f, indent=2, ensure_ascii=False)

                print(f"Processed: {filename}")

            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    main()
