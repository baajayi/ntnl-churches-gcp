#!/usr/bin/env python3
"""
PDF Sermon to JSON Converter
Extracts sermon content and metadata from PDF files and structures them as JSON
for ingestion via ingest_sermons_json.py
"""

import os
import sys
import json
import argparse
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import Counter

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber is required. Install with: pip install pdfplumber")
    sys.exit(1)


def extract_text_from_pdf(pdf_path: Path) -> tuple[str, Dict[str, Any]]:
    """
    Extract text and metadata from PDF using pdfplumber.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Tuple of (full_text, pdf_metadata_dict)
    """
    full_text = ""
    pdf_metadata = {}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Extract metadata
            if hasattr(pdf, 'metadata') and pdf.metadata:
                pdf_metadata = pdf.metadata

            # Extract text from all pages
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n\n"

    except Exception as e:
        print(f"Error extracting from {pdf_path.name}: {e}")
        return "", {}

    return full_text.strip(), pdf_metadata


def parse_filename_metadata(filename: str) -> Dict[str, str]:
    """
    Extract metadata from filename patterns.

    Examples:
        "NTNL Advent_Beta Sermon Content.pdf" → church="Advent Lutheran Church"
        "NTNL Bethel_beta local sermon.pdf" → church="Bethel Lutheran Church"

    Args:
        filename: PDF filename

    Returns:
        Dict with church, status extracted from filename
    """
    metadata = {}

    # Extract church name
    if "advent" in filename.lower():
        metadata['church'] = "Advent Lutheran Church"
    elif "bethel" in filename.lower():
        metadata['church'] = "Bethel Lutheran Church"
    else:
        metadata['church'] = "Unknown Church"

    # Extract status
    if "beta" in filename.lower():
        metadata['status'] = "beta"

    return metadata


def extract_date_from_text(text: str) -> Optional[str]:
    """
    Extract sermon date from text using regex patterns.

    Patterns:
        - "September 28, 2025"
        - "December 8, 2024"
        - "second Sunday of Advent"

    Args:
        text: Sermon text

    Returns:
        Extracted date string or None
    """
    # Pattern 1: Full date (September 28, 2025)
    date_pattern1 = r'([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})'
    match = re.search(date_pattern1, text[:1000])  # Search first 1000 chars
    if match:
        return match.group(1)

    # Pattern 2: Liturgical date (second Sunday of Advent)
    date_pattern2 = r'((?:first|second|third|fourth|1st|2nd|3rd|4th)\s+Sunday\s+of\s+\w+)'
    match = re.search(date_pattern2, text[:1000], re.IGNORECASE)
    if match:
        return match.group(1).title()

    return None


def extract_scripture_references(text: str) -> List[str]:
    """
    Extract biblical citations from text.

    Patterns:
        - "Matthew 3"
        - "Isaiah 11:1-10"
        - "1 Timothy"
        - "Psalm 72"

    Args:
        text: Sermon text

    Returns:
        List of unique scripture references
    """
    # Pattern matches book names followed by chapter[:verse]
    scripture_pattern = r'\b(\d?\s?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+\d+(?::\d+(?:-\d+)?)?)\b'

    # Common biblical book names for filtering
    biblical_books = {
        'genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy',
        'joshua', 'judges', 'ruth', 'samuel', 'kings', 'chronicles',
        'ezra', 'nehemiah', 'esther', 'job', 'psalms', 'psalm', 'proverbs',
        'ecclesiastes', 'song', 'isaiah', 'jeremiah', 'lamentations',
        'ezekiel', 'daniel', 'hosea', 'joel', 'amos', 'obadiah',
        'jonah', 'micah', 'nahum', 'habakkuk', 'zephaniah', 'haggai',
        'zechariah', 'malachi', 'matthew', 'mark', 'luke', 'john',
        'acts', 'romans', 'corinthians', 'galatians', 'ephesians',
        'philippians', 'colossians', 'thessalonians', 'timothy',
        'titus', 'philemon', 'hebrews', 'james', 'peter', 'jude',
        'revelation'
    }

    matches = re.findall(scripture_pattern, text)

    # Filter to only include likely biblical references
    references = []
    for match in matches:
        # Check if any biblical book name is in the match
        if any(book in match.lower() for book in biblical_books):
            references.append(match.strip())

    # Remove duplicates while preserving order
    unique_refs = []
    seen = set()
    for ref in references:
        ref_lower = ref.lower()
        if ref_lower not in seen:
            seen.add(ref_lower)
            unique_refs.append(ref)

    return unique_refs[:10]  # Limit to top 10 to avoid noise


def extract_themes(text: str) -> List[str]:
    """
    Extract key themes from sermon text using keyword frequency analysis.

    Args:
        text: Sermon text

    Returns:
        List of identified themes
    """
    # Lutheran theological keywords
    theme_keywords = {
        'faith': 'Faith',
        'grace': 'Grace',
        'baptism': 'Baptism',
        'repentance': 'Repentance',
        'repent': 'Repentance',
        'love': 'Love',
        'trust': 'Trust',
        'justice': 'Justice',
        'peace': 'Peace',
        'hope': 'Hope',
        'joy': 'Joy',
        'compassion': 'Compassion',
        'righteousness': 'Righteousness',
        'mercy': 'Mercy',
        'money': 'Money',
        'wealth': 'Wealth',
        'evil': 'Evil',
        'sin': 'Sin',
        'salvation': 'Salvation',
        'forgiveness': 'Forgiveness',
        'holy spirit': 'Holy Spirit',
        'prayer': 'Prayer',
        'worship': 'Worship',
        'discipleship': 'Discipleship',
        'community': 'Community',
        'service': 'Service'
    }

    text_lower = text.lower()

    # Count keyword occurrences
    keyword_counts = Counter()
    for keyword, theme in theme_keywords.items():
        count = text_lower.count(keyword)
        if count >= 3:  # Must appear at least 3 times
            keyword_counts[theme] = count

    # Return top themes
    top_themes = [theme for theme, count in keyword_counts.most_common(7)]

    return top_themes if top_themes else ["General Teaching"]


def build_json_structure(
    filename: str,
    full_text: str,
    pdf_metadata: Dict[str, Any],
    preacher: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build JSON structure compatible with ingest_sermons_json.py

    Args:
        filename: Original PDF filename
        full_text: Complete sermon text
        pdf_metadata: Metadata from PDF file
        preacher: Optional preacher name override

    Returns:
        Structured JSON dict
    """
    # Extract metadata from different sources
    filename_meta = parse_filename_metadata(filename)
    date = extract_date_from_text(full_text)
    scriptures = extract_scripture_references(full_text)
    themes = extract_themes(full_text)

    church = filename_meta.get('church', 'Unknown Church')

    # Build title
    if date:
        title = f"Sermon - {church} - {date}"
    else:
        title = f"Sermon - {church}"

    # Build metadata preamble
    preamble_parts = []
    if date:
        preamble_parts.append(f"Preached on {date}")
    if scriptures:
        preamble_parts.append(f"based on {', '.join(scriptures[:3])}")
    if themes:
        preamble_parts.append(f"exploring themes of {', '.join(themes[:3])}")

    metadata_preamble = f"A sermon from {church}"
    if preamble_parts:
        metadata_preamble += ", " + ", ".join(preamble_parts) + "."

    # Build final JSON
    json_data = {
        "Title": title,
        "Preacher": preacher or pdf_metadata.get('Author', 'Unknown'),
        "Church": church,
        "Denomination": "ELCA",
        "Date Preached": date or "Unknown",
        "Scripture References": scriptures,
        "Key Themes / Topics": themes,
        "Tone / Style": ["Teaching", "Expository"],
        "Intended Audience": ["General Congregation"],
        "Metadata Preamble": metadata_preamble,
        "Full Text": full_text
    }

    return json_data


def convert_pdf_to_json(
    pdf_path: Path,
    output_dir: Path,
    preacher: Optional[str] = None,
    preview: bool = False
) -> Optional[Path]:
    """
    Convert a single PDF to JSON format.

    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save JSON
        preacher: Optional preacher name
        preview: If True, print JSON without saving

    Returns:
        Path to saved JSON file or None
    """
    print(f"\nProcessing: {pdf_path.name}")
    print("=" * 60)

    # Extract text and metadata
    full_text, pdf_metadata = extract_text_from_pdf(pdf_path)

    if not full_text:
        print(f"ERROR: No text extracted from {pdf_path.name}")
        return None

    print(f"Extracted {len(full_text)} characters")

    # Build JSON structure
    json_data = build_json_structure(
        filename=pdf_path.name,
        full_text=full_text,
        pdf_metadata=pdf_metadata,
        preacher=preacher
    )

    # Preview mode: display metadata
    if preview:
        print("\nExtracted Metadata:")
        print(f"  Title: {json_data['Title']}")
        print(f"  Preacher: {json_data['Preacher']}")
        print(f"  Church: {json_data['Church']}")
        print(f"  Date: {json_data['Date Preached']}")
        print(f"  Scripture Refs: {', '.join(json_data['Scripture References'][:5])}")
        print(f"  Themes: {', '.join(json_data['Key Themes / Topics'])}")
        print(f"  Preamble: {json_data['Metadata Preamble']}")
        print(f"  Text Length: {len(json_data['Full Text'])} chars")
        return None

    # Generate output filename
    church_slug = json_data['Church'].lower().replace(' ', '_').replace('lutheran_church', '').strip('_')
    date_slug = json_data['Date Preached'].lower().replace(' ', '_').replace(',', '')
    output_filename = f"{church_slug}_sermon_{date_slug}.json"
    output_path = output_dir / output_filename

    # Save JSON
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Saved to: {output_path}")
        return output_path

    except Exception as e:
        print(f"\nERROR: Failed to save JSON: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Convert sermon PDFs to JSON format for ingestion',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'input_dir',
        type=str,
        help='Directory containing sermon PDF files'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default='sermon_json',
        help='Directory to save JSON files (default: sermon_json)'
    )

    parser.add_argument(
        '--advent-preacher',
        type=str,
        help='Preacher name for Advent sermons'
    )

    parser.add_argument(
        '--bethel-preacher',
        type=str,
        help='Preacher name for Bethel sermons'
    )

    parser.add_argument(
        '--preview',
        action='store_true',
        help='Preview extracted metadata without saving JSON'
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"ERROR: Input directory not found: {input_dir}")
        sys.exit(1)

    # Find all PDF files (exclude Zone.Identifier files)
    pdf_files = [f for f in input_dir.glob('*.pdf') if ':Zone.Identifier' not in f.name]

    if not pdf_files:
        print(f"ERROR: No PDF files found in {input_dir}")
        sys.exit(1)

    print(f"\nFound {len(pdf_files)} PDF file(s) to convert")
    if args.preview:
        print("PREVIEW MODE - No files will be saved\n")

    # Process each PDF
    converted = []
    for pdf_path in pdf_files:
        # Determine preacher based on filename
        preacher = None
        if 'advent' in pdf_path.name.lower() and args.advent_preacher:
            preacher = args.advent_preacher
        elif 'bethel' in pdf_path.name.lower() and args.bethel_preacher:
            preacher = args.bethel_preacher

        result = convert_pdf_to_json(
            pdf_path=pdf_path,
            output_dir=output_dir,
            preacher=preacher,
            preview=args.preview
        )

        if result:
            converted.append(result)

    # Summary
    print("\n" + "=" * 60)
    if args.preview:
        print(f"Preview complete for {len(pdf_files)} file(s)")
        print("Run without --preview to save JSON files")
    else:
        print(f"Conversion complete: {len(converted)}/{len(pdf_files)} files converted")
        if converted:
            print("\nNext steps:")
            print(f"1. Review JSON files in {output_dir}/")
            print(f"2. Ingest using: python scripts/ingest_sermons_json.py {output_dir}/ --namespace <namespace>")


if __name__ == '__main__':
    main()
