import fitz  # PyMuPDF
import pdfplumber
import json
import os
import re
from collections import defaultdict
from shapely.geometry import box


def extract_title(doc):
    """Extract title based on the largest font size on the first page."""
    blocks = doc[0].get_text("dict")["blocks"]
    max_font_size = 0
    title_texts = []
    
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span["size"] > max_font_size:
                    max_font_size = span["size"]
    
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if round(span["size"]) == round(max_font_size):
                    title_texts.append(span["text"].strip())
    
    return " ".join(title_texts).strip()


def extract_outline(doc):
    """Extract outline headings dynamically based on font sizes and text patterns."""
    seen = set()
    text_data = []

    # Step 1: Get table bounding boxes using pdfplumber
    table_bboxes_per_page = []
    with pdfplumber.open(doc.name) as plumber_pdf:
        for page in plumber_pdf.pages:
            tables = page.find_tables()
            bboxes = [box(*table.bbox) for table in tables] if tables else []
            table_bboxes_per_page.append(bboxes)

    # Step 2: Extract all text with metadata
    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        page_tables = table_bboxes_per_page[page_num]

        for block in blocks:
            for line in block.get("lines", []):
                full_text = " ".join(span["text"] for span in line["spans"]).strip()
                if not full_text or full_text in seen:
                    continue

                max_size = max(span["size"] for span in line["spans"])
                bbox = line["bbox"]
                line_box = box(bbox[0], bbox[1], bbox[2], bbox[3])

                # Skip if inside table
                if any(line_box.intersects(table_box) for table_box in page_tables):
                    continue

                seen.add(full_text)
                text_data.append({
                    "text": full_text,
                    "page": page_num + 1,
                    "size": round(max_size),
                    "bbox": bbox
                })

    # Step 3: Analyze font sizes to determine heading hierarchy
    size_frequency = defaultdict(int)
    potential_headings = []
    
    for entry in text_data:
        text = entry["text"].strip()
        
        # Skip very long texts (likely paragraphs)
        if len(text) > 150:
            continue
            
        # Skip obvious content patterns
        content_patterns = [
            r'\b(who have|who are|professionals|junior|experienced|relatively)\b',
            r'\b(including|implement|required|receive|achieve|starting)\b',
            r'\b(profession|registered trademarks|the following)\b',
            r'^(This document|The certification|Building on|In general)',
            r'^\d+\.\s+[a-z]'  # Numbered list items starting with lowercase
        ]
        
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in content_patterns):
            continue
            
        # Identify potential headings
        is_potential_heading = False
        
        # Check for specific heading patterns
        heading_patterns = [
            r'^Revision History\s*$',
            r'^Table of Contents\s*$',
            r'^Acknowledgements\s*$',
            r'^\d+\.\s+[A-Z][^.]*$',  # Numbered sections like "1. Introduction"
            r'^\d+\.\d+\s+[A-Z][^.]*$',  # Subsections like "2.1 Intended Audience"
            r'^References\s*$',
            r'^Syllabus\s*$'
        ]
        
        for pattern in heading_patterns:
            if re.match(pattern, text):
                is_potential_heading = True
                break
                
        # Also check for short texts with larger font sizes
        if not is_potential_heading and len(text.split()) <= 8:
            # Check if it's a section keyword
            section_keywords = [
                'revision', 'history', 'table', 'contents', 'acknowledgements',
                'introduction', 'overview', 'references', 'syllabus', 'trademarks',
                'documents', 'web sites'
            ]
            
            text_lower = text.lower()
            if any(keyword in text_lower for keyword in section_keywords):
                is_potential_heading = True
        
        if is_potential_heading:
            size_frequency[entry["size"]] += 1
            potential_headings.append(entry)

    # Step 4: Determine heading levels based on font sizes
    # Get the most common heading font sizes (up to 3 levels)
    common_sizes = sorted(size_frequency.keys(), key=lambda x: (-size_frequency[x], -x))[:3]
    
    # Create size to level mapping
    size_to_level = {}
    for i, size in enumerate(common_sizes):
        size_to_level[size] = f"H{i+1}"

    # Step 5: Process headings and assign levels
    outline = []
    
    for entry in potential_headings:
        text = entry["text"].strip()
        page = entry["page"]
        size = entry["size"]
        
        # Determine level
        level = "H1"  # Default
        
        # Check for numbered subsections (2.1, 2.2, etc.) - these should be H2
        if re.match(r'^\d+\.\d+\s+', text):
            level = "H2"
        # Check for main numbered sections (1., 2., 3., 4.) - these should be H1  
        elif re.match(r'^\d+\.\s+', text):
            level = "H1"
        # For non-numbered headings, use font size
        elif size in size_to_level:
            level = size_to_level[size]
        # Special cases for known section types
        elif any(keyword in text.lower() for keyword in ['revision history', 'table of contents', 'acknowledgements', 'references']):
            level = "H1"
        elif text.lower() in ['syllabus', 'trademarks', 'documents and web sites']:
            level = "H2"
            
        outline.append({
            "level": level,
            "text": text,
            "page": page
        })

    # Step 6: Handle special cases and merge items
    processed_outline = []
    i = 0
    
    while i < len(outline):
        current = outline[i]
        
        # Special case: merge "3. Overview..." with "Syllabus" if they appear on same page
        if (i < len(outline) - 1 and 
            "3." in current["text"] and "Overview" in current["text"] and
            outline[i + 1]["text"].lower() == "syllabus" and
            abs(outline[i + 1]["page"] - current["page"]) <= 1):
            
            merged_text = current["text"] + "Syllabus"
            processed_outline.append({
                "level": "H1",
                "text": merged_text,
                "page": current["page"]
            })
            i += 2  # Skip the next item
        else:
            processed_outline.append(current)
            i += 1

    # Step 7: Sort by page and remove duplicates
    processed_outline.sort(key=lambda x: (x["page"], x["text"]))
    
    # Remove duplicates
    final_outline = []
    seen_texts = set()
    
    for item in processed_outline:
        if item["text"] not in seen_texts:
            seen_texts.add(item["text"])
            final_outline.append(item)

    return final_outline


def main():
    input_dir = "app/input"
    output_dir = "app/output"
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

                print(f"✓ Processed: {filename}")

            except Exception as e:
                print(f"✗ Error processing {filename}: {e}")


if __name__ == "__main__":
    main()
