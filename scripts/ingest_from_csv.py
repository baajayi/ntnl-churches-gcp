#!/usr/bin/env python3
"""
CSV Bulk Ingestion Script
Ingests structured data from CSV file into Pinecone
"""

import os
import sys
import argparse
import csv
from typing import List, Dict
import time
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pinecone_service import get_pinecone_service
from services.openai_service import get_openai_service
from dotenv import load_dotenv

load_dotenv()


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks"""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            for delimiter in ['. ', '! ', '? ', '\n\n']:
                last_delim = text[start:end].rfind(delimiter)
                if last_delim != -1:
                    end = start + last_delim + len(delimiter)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks


def ingest_from_csv(csv_file: str, namespace: str, chunk_content: bool = True, batch_size: int = 100):
    """
    Ingest data from CSV file

    CSV Format:
        content,title,source,category,custom_field1,custom_field2,...

    Required column: content
    Optional columns: title, source, category, and any custom fields
    """
    if not os.path.exists(csv_file):
        print(f"Error: File not found: {csv_file}")
        return

    print("CSV Bulk Ingestion")
    print("=" * 60)
    print(f"File: {csv_file}")
    print(f"Namespace: {namespace}")
    print("=" * 60)

    pinecone_service = get_pinecone_service()
    openai_service = get_openai_service()

    all_vectors = []
    total_tokens = 0
    row_count = 0
    error_count = 0

    # Read CSV
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        if 'content' not in reader.fieldnames:
            print("Error: CSV must have a 'content' column")
            return

        print(f"\nProcessing CSV rows...")
        print(f"Columns: {', '.join(reader.fieldnames)}\n")

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
            row_count += 1

            content = row.get('content', '').strip()
            if not content:
                print(f"Row {row_num}: Skipping - empty content")
                error_count += 1
                continue

            # Chunk if needed
            if chunk_content:
                chunks = chunk_text(content)
            else:
                chunks = [content]

            # Create embeddings
            embeddings_result = openai_service.create_embeddings_batch(chunks)

            if not embeddings_result['success']:
                print(f"Row {row_num}: Error creating embeddings - {embeddings_result.get('error')}")
                error_count += 1
                continue

            total_tokens += embeddings_result['tokens_used']

            # Prepare metadata from CSV columns
            base_metadata = {}
            for key, value in row.items():
                if key != 'content' and value.strip():
                    base_metadata[key] = value.strip()

            # Create vectors
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings_result['embeddings'])):
                metadata = {
                    **base_metadata,
                    'text': chunk,
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'ingested_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'source_row': row_num
                }

                all_vectors.append({
                    'id': str(uuid.uuid4()),
                    'values': embedding,
                    'metadata': metadata
                })

            if row_count % 10 == 0:
                print(f"Processed {row_count} rows ({len(all_vectors)} vectors)...")

    print("\n" + "=" * 60)
    print(f"Processing complete:")
    print(f"  Total rows: {row_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total vectors: {len(all_vectors)}")
    print(f"  Total tokens: {total_tokens:,}")
    print(f"  Estimated cost: ${(total_tokens * 0.0001 / 1000):.4f}")

    if not all_vectors:
        print("\nNo vectors to upload")
        return

    # Upload to Pinecone
    print(f"\nUploading to Pinecone namespace '{namespace}'...")
    uploaded_count = 0

    for i in range(0, len(all_vectors), batch_size):
        batch = all_vectors[i:i + batch_size]
        result = pinecone_service.upsert_vectors(namespace, batch)

        if result['success']:
            uploaded_count += result['upserted_count']
            print(f"  Uploaded batch {i//batch_size + 1}: {result['upserted_count']} vectors")
        else:
            print(f"  Error uploading batch: {result.get('error')}")

    print(f"\n✓ Successfully uploaded {uploaded_count} vectors to '{namespace}'")


def main():
    parser = argparse.ArgumentParser(
        description='Ingest structured data from CSV into Pinecone',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CSV Format:
  Required column: content
  Optional columns: title, source, category, and any custom fields

  Example CSV:
    content,title,source,category
    "Product return policy text...","Return Policy","policies.pdf","policy"
    "Shipping information text...","Shipping Info","faq.md","faq"

Examples:
  # Ingest CSV to shared namespace
  python scripts/ingest_from_csv.py data.csv --namespace shared

  # Don't chunk content (keep as single vectors)
  python scripts/ingest_from_csv.py data.csv --namespace tenant1 --no-chunk
        """
    )

    parser.add_argument('csv_file', help='Path to CSV file')
    parser.add_argument('--namespace', required=True, help='Pinecone namespace')
    parser.add_argument('--no-chunk', action='store_true', help='Don\'t chunk content (keep as single vectors)')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for uploads (default: 100)')

    args = parser.parse_args()

    ingest_from_csv(
        csv_file=args.csv_file,
        namespace=args.namespace,
        chunk_content=not args.no_chunk,
        batch_size=args.batch_size
    )


if __name__ == '__main__':
    main()
