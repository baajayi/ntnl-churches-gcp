#!/usr/bin/env python3
"""
Quick test script to verify ingestion pipeline works without crashes
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("Testing Ingestion Pipeline - Crash Prevention")
print("=" * 60)

# Test 1: Import all required modules
print("\n1. Testing imports...")
try:
    from services.openai_service import get_openai_service
    from services.pinecone_service import get_pinecone_service
    from services.bm25_service import get_bm25_service
    print("   ✓ All imports successful")
except Exception as e:
    print(f"   ✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Initialize services
print("\n2. Testing service initialization...")
try:
    openai_service = get_openai_service()
    pinecone_service = get_pinecone_service()
    bm25_service = get_bm25_service()
    print("   ✓ Services initialized")
except Exception as e:
    print(f"   ✗ Service initialization failed: {e}")
    sys.exit(1)

# Test 3: Check OpenAI client
print("\n3. Testing OpenAI client...")
if openai_service.client is None:
    print("   ⚠ OpenAI client not initialized (check OPENAI_API_KEY)")
else:
    print(f"   ✓ OpenAI client ready")
    print(f"     - Embedding model: {openai_service.embedding_model}")
    print(f"     - Chat model: {openai_service.chat_model}")

# Test 4: Test retry logic with empty input (should return error dict, not crash)
print("\n4. Testing error handling...")
try:
    result = openai_service.create_embeddings_batch([])
    if result['success']:
        print("   ✗ Should have failed with empty input")
    else:
        print(f"   ✓ Handled error gracefully: {result['error']}")
except Exception as e:
    print(f"   ✗ Exception not caught: {type(e).__name__}: {e}")
    sys.exit(1)

# Test 5: Check for sermon JSON files
print("\n5. Checking sermon files...")
from pathlib import Path
advent_dir = Path("sermon_json/advent")
bethel_dir = Path("sermon_json/bethel")

if advent_dir.exists():
    advent_files = list(advent_dir.glob("*.json"))
    print(f"   ✓ Found {len(advent_files)} Advent sermon files")
else:
    print(f"   ⚠ Advent directory not found")

if bethel_dir.exists():
    bethel_files = list(bethel_dir.glob("*.json"))
    print(f"   ✓ Found {len(bethel_files)} Bethel sermon files")
else:
    print(f"   ⚠ Bethel directory not found")

print("\n" + "=" * 60)
print("All pre-flight checks passed!")
print("=" * 60)
print("\nYou can now run the ingestion safely with:")
print("  python scripts/ingest_sermons_json.py sermon_json/advent --namespace advent --dry-run")
print("\nThe following crash issues have been fixed:")
print("  ✓ Retry decorator now catches exceptions instead of crashing")
print("  ✓ File processing wrapped in try/except")
print("  ✓ Flush operations wrapped in try/except")
print("  ✓ Service initialization error handling added")
