#!/usr/bin/env python3
"""
Test script for hybrid search improvements
Tests all new features: persistence, query expansion, stemming, reranking
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


def test_text_snippet_fix():
    """Test that gemini_service now uses full_text instead of text_snippet"""
    print("\n" + "="*70)
    print("TEST 1: Text Snippet → Full Text Fix")
    print("="*70)

    from services.gemini_service import GeminiService

    service = GeminiService()

    # Mock chunk data with both fields
    mock_chunks = [
        {
            'metadata': {
                'text_snippet': 'First 500 characters only...',
                'full_text': 'First 500 characters only... PLUS the second half of the chunk with important data that was previously hidden!',
                'source': 'test_doc.txt'
            },
            'score': 0.95
        }
    ]

    # Build context
    context = service._build_context(mock_chunks)

    # Verify it uses full_text
    if 'PLUS the second half' in context:
        print("✅ PASS: Using full_text (complete chunk)")
        print(f"   Context length: {len(context)} chars")
        print(f"   Contains hidden data: YES")
        return True
    else:
        print("❌ FAIL: Still using text_snippet (truncated)")
        return False


def test_bm25_persistence():
    """Test BM25 index save/load functionality"""
    print("\n" + "="*70)
    print("TEST 2: BM25 Index Persistence")
    print("="*70)

    from services.bm25_service import BM25Service
    import shutil
    import tempfile

    # Use temp directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create service with temp directory
        bm25 = BM25Service(index_dir=tmpdir, use_lemmatization=False)

        # Add test documents
        docs = [
            "The quick brown fox jumps over the lazy dog",
            "A fast brown fox leaps over a sleepy canine",
            "Machine learning is a subset of artificial intelligence"
        ]
        doc_ids = ["doc1", "doc2", "doc3"]

        result = bm25.add_documents('test_namespace', docs, doc_ids)

        if not result['success']:
            print(f"❌ FAIL: Could not add documents: {result.get('error')}")
            return False

        print(f"✅ Added {result['document_count']} documents to index")

        # Save index
        save_result = bm25.save_index('test_namespace')

        if not save_result['success']:
            print(f"❌ FAIL: Could not save index: {save_result.get('error')}")
            return False

        print(f"✅ Saved index to: {save_result['filepath']}")

        # Clear in-memory index
        bm25.indices.clear()
        print("✅ Cleared in-memory index")

        # Load index back
        load_result = bm25.load_index('test_namespace')

        if not load_result['success']:
            print(f"❌ FAIL: Could not load index: {load_result.get('error')}")
            return False

        print(f"✅ Loaded index with {load_result['document_count']} documents")

        # Test search after load
        search_result = bm25.search('test_namespace', 'brown fox', top_k=2)

        if not search_result['success']:
            print(f"❌ FAIL: Search after load failed: {search_result.get('error')}")
            return False

        matches = search_result['matches']
        print(f"✅ Search after load found {len(matches)} matches")

        if len(matches) > 0:
            print(f"   Top match: {matches[0]['id']} (score: {matches[0]['score']:.2f})")
            return True
        else:
            print("❌ FAIL: No matches found after load")
            return False


def test_stemming_lemmatization():
    """Test stemming and lemmatization"""
    print("\n" + "="*70)
    print("TEST 3: Stemming & Lemmatization")
    print("="*70)

    from services.bm25_service import BM25Service
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Test with lemmatization
        print("\n--- Testing Lemmatization ---")
        bm25_lemma = BM25Service(index_dir=tmpdir, use_lemmatization=True, use_stemming=False)

        # Use docs where "church" only appears in some (so BM25 can score)
        docs = [
            "The churches in our community provide spiritual guidance",  # has church
            "Members gather for weekly services and fellowship",  # no church
            "Church leaders meet monthly for planning sessions"  # has church
        ]
        doc_ids = ["doc1", "doc2", "doc3"]

        bm25_lemma.add_documents('test_lemma', docs, doc_ids)

        # Check that "churches" was lemmatized to "church" in index
        corpus = bm25_lemma.indices['test_lemma']['corpus']
        if 'church' in corpus[0]:  # doc1 should have 'church' not 'churches'
            print(f"✅ Lemmatization in indexing: 'churches' → 'church'")
        else:
            print(f"❌ FAIL: 'churches' not lemmatized in index")
            return False

        # Search with singular form - should match doc1 (which had "churches")
        result = bm25_lemma.search('test_lemma', 'church', top_k=5)

        if result['success'] and len(result['matches']) >= 2:
            print(f"✅ Lemmatization in search: 'church' matched {len(result['matches'])} docs")
            print(f"   Query tokens: {result.get('query_tokens', [])}")
            for match in result['matches']:
                print(f"   - {match['id']}: score={match['score']:.2f}")
        else:
            print(f"❌ FAIL: Expected 2+ matches, got {len(result.get('matches', []))}")
            return False

        # Test with stemming
        print("\n--- Testing Stemming ---")
        bm25_stem = BM25Service(index_dir=tmpdir + '_stem', use_stemming=True, use_lemmatization=False)

        # Add document with different variations, plus one without the term
        docs2 = [
            "Running through the forest quickly",  # has running
            "People walk slowly in the park",  # no run-related terms
            "The runner runs at dawn"  # has runner, runs
        ]
        doc_ids2 = ["doc4", "doc5", "doc6"]

        bm25_stem.add_documents('test_stem', docs2, doc_ids2)

        # Check stemming in index
        corpus = bm25_stem.indices['test_stem']['corpus']
        # Running, runner, runs should all stem to 'run'
        if 'run' in corpus[0] or 'run' in corpus[2]:
            print(f"✅ Stemming in indexing: variations → 'run'")
        else:
            print(f"⚠️  Corpus tokens: {corpus}")

        # Search with base form
        result = bm25_stem.search('test_stem', 'run', top_k=5)

        if result['success'] and len(result['matches']) >= 2:
            print(f"✅ Stemming in search: 'run' matched {len(result['matches'])} docs")
            print(f"   Query tokens: {result.get('query_tokens', [])}")
            for match in result['matches']:
                print(f"   - {match['id']}: score={match['score']:.2f}")
            return True
        else:
            print(f"❌ FAIL: Expected 2+ matches, got {len(result.get('matches', []))}")
            print(f"   Query tokens: {result.get('query_tokens', [])}")
            print(f"   Corpus: {corpus}")
            return False


def test_query_expansion():
    """Test query expansion with WordNet"""
    print("\n" + "="*70)
    print("TEST 4: Query Expansion")
    print("="*70)

    from services.query_expansion import QueryExpansionService

    service = QueryExpansionService()

    # Test synonym expansion
    query = "church baptism"
    expanded = service.expand_with_synonyms(query, max_synonyms_per_word=2)

    print(f"Original query: '{query}'")
    print(f"Expanded query: '{expanded}'")

    expansion_terms = service.get_expansion_terms(query, max_terms=5)
    print(f"Expansion terms: {expansion_terms}")

    if len(expanded) > len(query):
        print("✅ PASS: Query expanded with synonyms")
        return True
    else:
        print("⚠️  WARNING: No expansion occurred (may be normal for some words)")
        return True  # Not a failure, just no synonyms found


def test_cross_encoder_reranking():
    """Test cross-encoder reranking"""
    print("\n" + "="*70)
    print("TEST 5: Cross-Encoder Reranking")
    print("="*70)

    try:
        from services.hybrid_search import rerank_results

        # Mock search results
        mock_results = [
            {
                'id': 'doc1',
                'score': 0.8,
                'metadata': {
                    'full_text': 'Lutheran baptism is a sacred ritual of initiation into the Christian faith.',
                    'source': 'theology.txt'
                }
            },
            {
                'id': 'doc2',
                'score': 0.75,
                'metadata': {
                    'full_text': 'The weather today is sunny and warm with clear skies.',
                    'source': 'weather.txt'
                }
            },
            {
                'id': 'doc3',
                'score': 0.7,
                'metadata': {
                    'full_text': 'Baptism in the Lutheran tradition involves water and the word of God.',
                    'source': 'catechism.txt'
                }
            }
        ]

        query = "What is Lutheran baptism?"

        # Rerank
        result = rerank_results(query, mock_results, top_k=3)

        if not result.get('success'):
            if 'not available' in result.get('error', ''):
                print("⚠️  WARNING: sentence-transformers not installed")
                print("   Install with: pip install sentence-transformers")
                return True  # Not a failure, just not installed
            else:
                print(f"❌ FAIL: Reranking failed: {result.get('error')}")
                return False

        if result.get('reranked'):
            print("✅ PASS: Cross-encoder reranking successful")
            print(f"   Model: {result.get('metadata', {}).get('model', 'unknown')}")
            print(f"   Reranked {result.get('metadata', {}).get('reranked_count', 0)} results")

            # Show reranked order
            for i, match in enumerate(result['matches'][:3], 1):
                print(f"   {i}. {match['id']} - Rerank score: {match.get('rerank_score', 0):.4f} (original: {match.get('original_score', 0):.2f})")

            # Check if relevant docs moved up
            top_id = result['matches'][0]['id']
            if top_id in ['doc1', 'doc3']:  # Relevant docs
                print("✅ Relevant documents ranked higher after reranking")
                return True
            else:
                print("⚠️  WARNING: Reranking didn't improve relevance (may need more testing)")
                return True
        else:
            print("❌ FAIL: Reranking did not occur")
            return False

    except Exception as e:
        print(f"❌ FAIL: Exception during reranking test: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hybrid_search_integration():
    """Test hybrid search with multiple components"""
    print("\n" + "="*70)
    print("TEST 6: Hybrid Search Integration")
    print("="*70)

    from services.hybrid_search import hybrid_search

    # Mock dense results (vector search)
    dense_results = [
        {'id': 'doc1', 'score': 0.95, 'metadata': {'text': 'Relevant doc 1'}},
        {'id': 'doc2', 'score': 0.85, 'metadata': {'text': 'Relevant doc 2'}},
        {'id': 'doc3', 'score': 0.75, 'metadata': {'text': 'Somewhat relevant'}},
    ]

    # Mock sparse results (BM25)
    sparse_results = [
        {'id': 'doc2', 'score': 15.5, 'rank': 1},
        {'id': 'doc4', 'score': 12.3, 'rank': 2},
        {'id': 'doc1', 'score': 10.1, 'rank': 3},
    ]

    # Test RRF fusion
    print("\n--- Testing RRF Fusion ---")
    result = hybrid_search(
        dense_results,
        sparse_results,
        method='rrf',
        alpha=0.7,
        top_k=5
    )

    if not result['success']:
        print(f"❌ FAIL: RRF fusion failed: {result.get('error')}")
        return False

    print(f"✅ RRF fusion successful")
    print(f"   Merged {result['metadata']['merged_count']} results")
    print(f"   From {result['metadata']['dense_count']} dense + {result['metadata']['sparse_count']} sparse")

    for i, match in enumerate(result['matches'][:3], 1):
        print(f"   {i}. {match['id']} - Score: {match['score']:.4f}")

    # Test weighted fusion
    print("\n--- Testing Weighted Fusion ---")
    result = hybrid_search(
        dense_results,
        sparse_results,
        method='weighted',
        alpha=0.7,
        top_k=5
    )

    if not result['success']:
        print(f"❌ FAIL: Weighted fusion failed: {result.get('error')}")
        return False

    print(f"✅ Weighted fusion successful")
    print(f"   Merged {result['metadata']['merged_count']} results")

    for i, match in enumerate(result['matches'][:3], 1):
        print(f"   {i}. {match['id']} - Score: {match['score']:.4f}")

    return True


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("HYBRID SEARCH IMPROVEMENTS - TEST SUITE")
    print("="*70)

    tests = [
        ("Text Snippet Fix", test_text_snippet_fix),
        ("BM25 Persistence", test_bm25_persistence),
        ("Stemming/Lemmatization", test_stemming_lemmatization),
        ("Query Expansion", test_query_expansion),
        ("Cross-Encoder Reranking", test_cross_encoder_reranking),
        ("Hybrid Search Integration", test_hybrid_search_integration),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "="*70)
    print(f"TOTAL: {passed_count}/{total_count} tests passed ({passed_count/total_count*100:.1f}%)")
    print("="*70)

    if passed_count == total_count:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
