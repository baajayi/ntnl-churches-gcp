"""
Hybrid Search Service
Combines dense (semantic) and sparse (keyword) search using Reciprocal Rank Fusion
Includes optional cross-encoder reranking for improved precision
"""

from typing import List, Dict, Any, Optional

# Cross-encoder for reranking (lazy loaded to avoid import errors if not installed)
_cross_encoder = None


def reciprocal_rank_fusion(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    k: int = 60,
    alpha: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Combine dense and sparse search results using Reciprocal Rank Fusion (RRF)

    RRF Formula: RRF_score(d) = sum over all rankings r: 1 / (k + rank(d, r))
    where k is a constant (typically 60) that reduces the impact of high rankings

    Args:
        dense_results: Results from vector/semantic search
                      Expected format: [{'id': doc_id, 'score': float, ...}, ...]
        sparse_results: Results from BM25/keyword search
                       Expected format: [{'id': doc_id, 'score': float, 'rank': int}, ...]
        k: RRF constant (default 60, standard in literature)
        alpha: Weight for dense vs sparse (0.7 = 70% dense, 30% sparse)
               Note: alpha modifies the RRF scores before combination

    Returns:
        List of merged results sorted by RRF score, with metadata from both sources
    """
    # Build rank maps for RRF calculation
    # For dense results, use position in list as rank (already sorted by score)
    dense_ranks = {result['id']: (idx + 1) for idx, result in enumerate(dense_results)}

    # For sparse results, use provided rank or position
    sparse_ranks = {}
    for idx, result in enumerate(sparse_results):
        doc_id = result['id']
        # Use provided rank if available, otherwise use position
        rank = result.get('rank', idx + 1)
        sparse_ranks[doc_id] = rank

    # Collect all unique document IDs
    all_doc_ids = set(dense_ranks.keys()) | set(sparse_ranks.keys())

    # Calculate RRF scores for each document
    rrf_scores = {}
    for doc_id in all_doc_ids:
        # Calculate dense contribution (weighted by alpha)
        dense_rrf = 0.0
        if doc_id in dense_ranks:
            dense_rrf = alpha / (k + dense_ranks[doc_id])

        # Calculate sparse contribution (weighted by 1-alpha)
        sparse_rrf = 0.0
        if doc_id in sparse_ranks:
            sparse_rrf = (1 - alpha) / (k + sparse_ranks[doc_id])

        # Total RRF score
        rrf_scores[doc_id] = dense_rrf + sparse_rrf

    # Build result list with merged metadata
    merged_results = []

    # Create lookup dictionaries for fast access
    dense_lookup = {r['id']: r for r in dense_results}
    sparse_lookup = {r['id']: r for r in sparse_results}

    for doc_id, rrf_score in rrf_scores.items():
        result = {
            'id': doc_id,
            'score': rrf_score,
            'fusion_method': 'rrf',
            'fusion_details': {
                'k': k,
                'alpha': alpha,
                'in_dense': doc_id in dense_ranks,
                'in_sparse': doc_id in sparse_ranks
            }
        }

        # Add dense metadata if present
        if doc_id in dense_lookup:
            dense_data = dense_lookup[doc_id]
            result['dense_score'] = dense_data.get('score', 0.0)
            result['dense_rank'] = dense_ranks[doc_id]
            # Copy metadata if available
            if 'metadata' in dense_data:
                result['metadata'] = dense_data['metadata']
            # Copy namespace if available
            if 'namespace' in dense_data:
                result['namespace'] = dense_data['namespace']

        # Add sparse metadata if present
        if doc_id in sparse_lookup:
            sparse_data = sparse_lookup[doc_id]
            result['sparse_score'] = sparse_data.get('score', 0.0)
            result['sparse_rank'] = sparse_ranks[doc_id]

        merged_results.append(result)

    # Sort by RRF score (descending)
    merged_results.sort(key=lambda x: x['score'], reverse=True)

    return merged_results


def weighted_score_fusion(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    alpha: float = 0.7,
    dense_score_range: Optional[tuple] = None,
    sparse_score_range: Optional[tuple] = None
) -> List[Dict[str, Any]]:
    """
    Combine dense and sparse search results using weighted normalized scores

    Formula: final_score = alpha * norm(dense_score) + (1-alpha) * norm(sparse_score)

    Args:
        dense_results: Results from vector/semantic search
        sparse_results: Results from BM25/keyword search
        alpha: Weight for dense vs sparse (0.7 = 70% dense, 30% sparse)
        dense_score_range: Optional (min, max) for dense score normalization
        sparse_score_range: Optional (min, max) for sparse score normalization

    Returns:
        List of merged results sorted by weighted score
    """
    # Normalize scores to 0-1 range
    def normalize_scores(results: List[Dict], score_range: Optional[tuple] = None):
        if not results:
            return {}

        scores = [r['score'] for r in results]

        # Use provided range or calculate from data
        if score_range:
            min_score, max_score = score_range
        else:
            min_score = min(scores)
            max_score = max(scores)

        # Avoid division by zero
        if max_score == min_score:
            return {r['id']: 1.0 for r in results}

        # Normalize
        normalized = {}
        for r in results:
            norm_score = (r['score'] - min_score) / (max_score - min_score)
            normalized[r['id']] = norm_score

        return normalized

    # Normalize both result sets
    dense_normalized = normalize_scores(dense_results, dense_score_range)
    sparse_normalized = normalize_scores(sparse_results, sparse_score_range)

    # Get all unique doc IDs
    all_doc_ids = set(dense_normalized.keys()) | set(sparse_normalized.keys())

    # Calculate weighted scores
    weighted_scores = {}
    for doc_id in all_doc_ids:
        dense_score = dense_normalized.get(doc_id, 0.0)
        sparse_score = sparse_normalized.get(doc_id, 0.0)
        weighted_scores[doc_id] = alpha * dense_score + (1 - alpha) * sparse_score

    # Build merged results
    dense_lookup = {r['id']: r for r in dense_results}
    sparse_lookup = {r['id']: r for r in sparse_results}

    merged_results = []
    for doc_id, final_score in weighted_scores.items():
        result = {
            'id': doc_id,
            'score': final_score,
            'fusion_method': 'weighted',
            'fusion_details': {
                'alpha': alpha,
                'in_dense': doc_id in dense_lookup,
                'in_sparse': doc_id in sparse_lookup
            }
        }

        # Add metadata from dense results if available
        if doc_id in dense_lookup:
            dense_data = dense_lookup[doc_id]
            result['dense_score'] = dense_data.get('score', 0.0)
            result['dense_score_normalized'] = dense_normalized[doc_id]
            if 'metadata' in dense_data:
                result['metadata'] = dense_data['metadata']
            if 'namespace' in dense_data:
                result['namespace'] = dense_data['namespace']

        # Add sparse metadata if available
        if doc_id in sparse_lookup:
            sparse_data = sparse_lookup[doc_id]
            result['sparse_score'] = sparse_data.get('score', 0.0)
            result['sparse_score_normalized'] = sparse_normalized[doc_id]

        merged_results.append(result)

    # Sort by weighted score (descending)
    merged_results.sort(key=lambda x: x['score'], reverse=True)

    return merged_results


def hybrid_search(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    method: str = 'rrf',
    alpha: float = 0.7,
    top_k: Optional[int] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Perform hybrid search by combining dense and sparse results

    Args:
        dense_results: Results from semantic/vector search
        sparse_results: Results from BM25/keyword search
        method: Fusion method ('rrf' or 'weighted')
        alpha: Weight for dense vs sparse
        top_k: Number of results to return (None = return all)
        **kwargs: Additional arguments passed to fusion function

    Returns:
        Dict with merged results and metadata
    """
    if method == 'rrf':
        merged = reciprocal_rank_fusion(
            dense_results,
            sparse_results,
            alpha=alpha,
            **kwargs
        )
    elif method == 'weighted':
        merged = weighted_score_fusion(
            dense_results,
            sparse_results,
            alpha=alpha,
            **kwargs
        )
    else:
        return {
            'success': False,
            'error': f'Unknown fusion method: {method}',
            'matches': []
        }

    # Limit results if top_k specified
    if top_k is not None:
        merged = merged[:top_k]

    return {
        'success': True,
        'matches': merged,
        'metadata': {
            'fusion_method': method,
            'alpha': alpha,
            'dense_count': len(dense_results),
            'sparse_count': len(sparse_results),
            'merged_count': len(merged),
            'unique_docs': len(set([r['id'] for r in dense_results] + [r['id'] for r in sparse_results]))
        }
    }


def _get_cross_encoder():
    """
    Lazy load cross-encoder model to avoid import errors if not installed

    Returns:
        CrossEncoder instance or None if not available
    """
    global _cross_encoder

    if _cross_encoder is not None:
        return _cross_encoder

    try:
        from sentence_transformers import CrossEncoder
        # Use MS MARCO MiniLM model - lightweight and effective for retrieval
        _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        return _cross_encoder
    except ImportError:
        print("Warning: sentence-transformers not installed. Cross-encoder reranking unavailable.")
        print("Install with: pip install sentence-transformers")
        return None
    except Exception as e:
        print(f"Warning: Failed to load cross-encoder model: {e}")
        return None


def rerank_results(
    query: str,
    results: List[Dict[str, Any]],
    top_k: Optional[int] = None,
    model_name: str = 'cross-encoder/ms-marco-MiniLM-L-6-v2'
) -> Dict[str, Any]:
    """
    Rerank search results using a cross-encoder model

    Cross-encoders directly score query-document pairs and typically provide
    better accuracy than bi-encoders (used for initial retrieval), but are slower.
    This makes them ideal for reranking a small set of candidates.

    Args:
        query: The search query
        results: List of search results to rerank (from fusion or single method)
                 Must have 'metadata' with text content
        top_k: Number of top results to return after reranking (None = return all)
        model_name: Name of cross-encoder model to use

    Returns:
        Dict with reranked results and metadata
    """
    if not results:
        return {
            'success': True,
            'matches': [],
            'reranked': False,
            'error': 'No results to rerank'
        }

    # Get cross-encoder model
    cross_encoder = _get_cross_encoder()

    if cross_encoder is None:
        return {
            'success': False,
            'error': 'Cross-encoder not available',
            'matches': results
        }

    try:
        # Extract text from results
        # Try multiple metadata fields in order of preference
        texts = []
        valid_indices = []

        for idx, result in enumerate(results):
            metadata = result.get('metadata', {})

            # Try to get text content (prefer full_text > text_snippet > text)
            text = metadata.get('full_text') or metadata.get('text_snippet') or metadata.get('text', '')

            if text and isinstance(text, str) and text.strip():
                texts.append(text)
                valid_indices.append(idx)

        if not texts:
            return {
                'success': False,
                'error': 'No text content found in results metadata',
                'matches': results
            }

        # Create query-document pairs for cross-encoder
        pairs = [[query, text] for text in texts]

        # Score all pairs
        scores = cross_encoder.predict(pairs)

        # Create reranked results
        reranked = []
        for i, score in enumerate(scores):
            original_idx = valid_indices[i]
            result = results[original_idx].copy()

            # Store original and rerank scores
            result['rerank_score'] = float(score)
            result['original_score'] = result.get('score', 0.0)
            result['original_rank'] = original_idx + 1

            # Update main score to rerank score
            result['score'] = float(score)

            reranked.append(result)

        # Sort by rerank score (descending)
        reranked.sort(key=lambda x: x['rerank_score'], reverse=True)

        # Limit to top_k if specified
        if top_k is not None:
            reranked = reranked[:top_k]

        return {
            'success': True,
            'matches': reranked,
            'reranked': True,
            'metadata': {
                'model': model_name,
                'original_count': len(results),
                'reranked_count': len(reranked),
                'filtered_count': len(results) - len(valid_indices)  # Items without text
            }
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Reranking failed: {str(e)}',
            'matches': results
        }


def hybrid_search_with_rerank(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    query: str,
    method: str = 'rrf',
    alpha: float = 0.7,
    top_k: int = 10,
    rerank_top_k: Optional[int] = None,
    use_reranking: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    Perform hybrid search with optional cross-encoder reranking

    This is the recommended high-level function that combines:
    1. Fusion (RRF or weighted)
    2. Reranking with cross-encoder (optional but recommended)

    Args:
        dense_results: Results from semantic/vector search
        sparse_results: Results from BM25/keyword search
        query: Original query text (needed for reranking)
        method: Fusion method ('rrf' or 'weighted')
        alpha: Weight for dense vs sparse
        top_k: Final number of results to return
        rerank_top_k: Number of candidates to pass to reranker (default: top_k * 2)
                     Set higher to give reranker more candidates to choose from
        use_reranking: Whether to apply cross-encoder reranking
        **kwargs: Additional arguments passed to fusion function

    Returns:
        Dict with search results and metadata
    """
    # Step 1: Fusion
    # Retrieve more candidates for reranking (2x or rerank_top_k)
    fusion_top_k = rerank_top_k if rerank_top_k else (top_k * 2)

    fusion_result = hybrid_search(
        dense_results,
        sparse_results,
        method=method,
        alpha=alpha,
        top_k=fusion_top_k,
        **kwargs
    )

    if not fusion_result['success']:
        return fusion_result

    fused_results = fusion_result['matches']

    # Step 2: Reranking (optional)
    if use_reranking and fused_results:
        rerank_result = rerank_results(
            query=query,
            results=fused_results,
            top_k=top_k
        )

        if rerank_result['success']:
            # Combine metadata from both stages
            combined_metadata = {
                **fusion_result['metadata'],
                'reranking': rerank_result.get('metadata', {}),
                'reranked': True
            }

            return {
                'success': True,
                'matches': rerank_result['matches'],
                'metadata': combined_metadata
            }
        else:
            # Reranking failed, return fusion results
            print(f"Warning: Reranking failed, using fusion results: {rerank_result.get('error')}")
            return {
                'success': True,
                'matches': fused_results[:top_k],
                'metadata': {
                    **fusion_result['metadata'],
                    'reranked': False,
                    'rerank_error': rerank_result.get('error')
                }
            }
    else:
        # No reranking requested
        return {
            'success': True,
            'matches': fused_results[:top_k],
            'metadata': {
                **fusion_result['metadata'],
                'reranked': False
            }
        }
