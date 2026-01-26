"""
RAG Routes
Core endpoints for RAG (Retrieval Augmented Generation) functionality
"""

from flask import Blueprint, request, jsonify, g, current_app
from services.pinecone_service import get_pinecone_service
from services.gemini_service import get_gemini_service
from services.bm25_service import get_bm25_service
import time

rag_bp = Blueprint("rag", __name__)

# Get services
pinecone_service = get_pinecone_service()
gemini_service = get_gemini_service()
bm25_service = get_bm25_service()

@rag_bp.route("/rag-query", methods=["POST"])
def rag_query():
    """
    Answer a question using RAG (with lazy service loading)

    This endpoint demonstrates lazy service fetching - services are retrieved
    inside the function rather than at module import time. This ensures the
    services are initialized when needed and handles cases where API keys
    might not be available at import time.

    Request body: Same as /query endpoint
    """
    start_time = time.time()

    # Lazy fetch services here, not at module import
    gemini_svc = get_gemini_service()
    pinecone_svc = get_pinecone_service()

    try:
        data = request.get_json()

        if not data or 'query' not in data:
            return jsonify({
                'success': False,
                'error': 'Query is required'
            }), 400

        query_text = data['query']

        # Get tenant's default RAG settings
        rag_settings = g.tenant_config.get('rag_settings', {})

        # Use request params or fall back to tenant defaults
        top_k = data.get('top_k', rag_settings.get('top_k', 5))
        temperature = data.get('temperature', rag_settings.get('temperature', 0.7))
        max_tokens = data.get('max_tokens', rag_settings.get('max_tokens'))

        # Namespace boost parameter (for multi-namespace searches)
        tenant_namespace_boost = data.get('tenant_namespace_boost', rag_settings.get('tenant_namespace_boost', 1.25))

        # Use request system_prompt or tenant default
        system_prompt = data.get('system_prompt', g.tenant_config.get('system_prompt'))

        use_cache = data.get('use_cache', True)

        # Check cache first
        cache_service = current_app.cache_service
        if use_cache:
            cached_result = cache_service.get_cached_query_result(g.tenant_id, query_text)
            if cached_result:
                cached_result['cached'] = True
                cached_result['latency_ms'] = int((time.time() - start_time) * 1000)
                return jsonify(cached_result), 200

        # Generate embedding for query using lazy-loaded service
        embedding_result = gemini_svc.create_embedding(query_text)

        if not embedding_result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to create query embedding',
                'details': embedding_result.get('error')
            }), 500

        query_embedding = embedding_result['embedding']

        # Search Pinecone for relevant context using lazy-loaded service
        accessible_namespaces = g.tenant_config.get('accessible_namespaces', [g.tenant_config['pinecone_namespace']])

        if len(accessible_namespaces) > 1:
            # Search across multiple namespaces
            search_result = pinecone_svc.query_multiple_namespaces(
                namespaces=accessible_namespaces,
                query_vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                tenant_namespace_boost=tenant_namespace_boost
            )
        else:
            # Single namespace search
            search_result = pinecone_svc.query_vectors(
                tenant_namespace=accessible_namespaces[0],
                query_vector=query_embedding,
                top_k=top_k,
                include_metadata=True
            )

        if not search_result['success']:
            return jsonify({
                'success': False,
                'error': 'Vector search failed',
                'details': search_result.get('error')
            }), 500

        # Get conversation history for context-aware responses
        conversation_history = data.get('conversation_history', [])

        # Generate response using RAG
        rag_result = gemini_svc.generate_rag_response(
            query=query_text,
            context_chunks=search_result['matches'],
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            conversation_history=conversation_history
        )

        if not rag_result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to generate response',
                'details': rag_result.get('error')
            }), 500

        # Build response
        response_data = {
            'success': True,
            'answer': rag_result['answer'],
            'sources': [
                {
                    'id': match['id'],
                    'score': match['score'],
                    'namespace': match.get('namespace', accessible_namespaces[0]),
                    'metadata': match.get('metadata', {})
                }
                for match in search_result['matches']
            ],
            'metadata': {
                'model': rag_result['model'],
                'tokens': rag_result['tokens'],
                'finish_reason': rag_result['finish_reason'],
                'context_chunks': len(search_result['matches']),
                'namespaces_searched': search_result.get('namespaces_searched', accessible_namespaces),
                'latency_ms': int((time.time() - start_time) * 1000)
            },
            'cached': False
        }

        # Cache the result
        if use_cache:
            cache_service.cache_query_result(g.tenant_id, query_text, response_data, ttl=3600)

        # Log the query with response
        current_app.logging_service.log_query(
            tenant_id=g.tenant_id,
            query=query_text,
            response=rag_result['answer'],
            time_ms=response_data['metadata']['latency_ms'],
            metadata={
                'tokens_used': rag_result['tokens']['total'],
                'sources_count': len(search_result['matches'])
            }
        )

        return jsonify(response_data), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500

@rag_bp.route('/query', methods=['POST', 'OPTIONS'])
def query():
    """
    Answer a question using RAG with conversation history support and hybrid search

    Request body:
        {
            "query": "What is...",
            "top_k": 5,  // optional, uses tenant default or 5
            "temperature": 0.7,  // optional, uses tenant default or 0.7
            "max_tokens": 1000,  // optional, uses tenant default
            "system_prompt": "...",  // optional, uses tenant default
            "use_cache": true,  // optional, default true
            "use_hybrid": true,  // optional, enable hybrid search (default true)
            "alpha": 0.7,  // optional, dense vs sparse weight (default 0.7)
            "fusion_method": "rrf",  // optional, 'rrf' or 'weighted' (default 'rrf')
            "conversation_history": [  // optional, for follow-up questions
                {"query": "Previous question", "answer": "Previous answer"},
                ...
            ]
        }

    Note: All optional parameters will use the tenant's configured defaults
          from TENANT_CONFIG if not provided in the request.

          Hybrid search combines semantic (dense vectors) and keyword (BM25) retrieval.
          Alpha controls the balance: 1.0 = pure semantic, 0.0 = pure keyword.

          For follow-up questions, include conversation_history array to maintain context.
          The system will use the last 5 exchanges for context-aware responses.

    Returns:
        {
            "success": true,
            "answer": "The answer is...",
            "sources": [...],
            "metadata": {...}
        }
    """
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-Tenant-ID')
        return response, 200

    start_time = time.time()

    try:
        data = request.get_json()

        if not data or 'query' not in data:
            return jsonify({
                'success': False,
                'error': 'Query is required'
            }), 400

        query_text = data['query']

        # Get tenant's default RAG settings
        rag_settings = g.tenant_config.get('rag_settings', {})

        # Use request params or fall back to tenant defaults
        top_k = data.get('top_k', rag_settings.get('top_k', 5))
        temperature = data.get('temperature', rag_settings.get('temperature', 0.7))
        max_tokens = data.get('max_tokens', rag_settings.get('max_tokens'))

        # Hybrid search parameters
        use_hybrid = data.get('use_hybrid', rag_settings.get('use_hybrid', True))
        alpha = data.get('alpha', rag_settings.get('alpha', 0.7))
        fusion_method = data.get('fusion_method', rag_settings.get('fusion_method', 'rrf'))

        # Namespace boost parameter (for multi-namespace searches)
        tenant_namespace_boost = data.get('tenant_namespace_boost', rag_settings.get('tenant_namespace_boost', 1.25))

        # Use request system_prompt or tenant default
        system_prompt = data.get('system_prompt', g.tenant_config.get('system_prompt'))

        use_cache = data.get('use_cache', True)

        # Check cache first
        cache_service = current_app.cache_service
        if use_cache:
            cached_result = cache_service.get_cached_query_result(g.tenant_id, query_text)
            if cached_result:
                cached_result['cached'] = True
                cached_result['latency_ms'] = int((time.time() - start_time) * 1000)
                return jsonify(cached_result), 200

        # Generate embedding for query
        embedding_result = gemini_service.create_embedding(query_text)

        if not embedding_result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to create query embedding',
                'details': embedding_result.get('error')
            }), 500

        query_embedding = embedding_result['embedding']

        # Search for relevant context using hybrid or pure vector search
        # Use accessible_namespaces if configured (for shared embeddings)
        accessible_namespaces = g.tenant_config.get('accessible_namespaces', [g.tenant_config['pinecone_namespace']])

        if use_hybrid:
            # Hybrid search (semantic + keyword)
            if len(accessible_namespaces) > 1:
                # Search across multiple namespaces with hybrid
                search_result = pinecone_service.hybrid_query_multiple_namespaces(
                    namespaces=accessible_namespaces,
                    query_vector=query_embedding,
                    query_text=query_text,
                    bm25_service=bm25_service,
                    top_k=top_k,
                    alpha=alpha,
                    fusion_method=fusion_method,
                    tenant_namespace_boost=tenant_namespace_boost
                )
            else:
                # Single namespace hybrid search
                search_result = pinecone_service.hybrid_query(
                    tenant_namespace=accessible_namespaces[0],
                    query_vector=query_embedding,
                    query_text=query_text,
                    bm25_service=bm25_service,
                    top_k=top_k,
                    alpha=alpha,
                    fusion_method=fusion_method,
                    include_metadata=True
                )
        else:
            # Pure vector search (existing behavior)
            if len(accessible_namespaces) > 1:
                # Search across multiple namespaces
                search_result = pinecone_service.query_multiple_namespaces(
                    namespaces=accessible_namespaces,
                    query_vector=query_embedding,
                    top_k=top_k,
                    include_metadata=True,
                    tenant_namespace_boost=tenant_namespace_boost
                )
            else:
                # Single namespace search
                search_result = pinecone_service.query_vectors(
                    tenant_namespace=accessible_namespaces[0],
                    query_vector=query_embedding,
                    top_k=top_k,
                    include_metadata=True
                )

        if not search_result['success']:
            return jsonify({
                'success': False,
                'error': 'Vector search failed',
                'details': search_result.get('error')
            }), 500

        # Get conversation history for context-aware responses
        conversation_history = data.get('conversation_history', [])

        # Generate response using RAG
        rag_result = gemini_service.generate_rag_response(
            query=query_text,
            context_chunks=search_result['matches'],
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            conversation_history=conversation_history
        )

        if not rag_result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to generate response',
                'details': rag_result.get('error')
            }), 500

        # Build response
        response_data = {
            'success': True,
            'answer': rag_result['answer'],
            'sources': [
                {
                    'id': match['id'],
                    'score': match['score'],
                    'namespace': match.get('namespace', accessible_namespaces[0]),  # Include namespace source
                    'metadata': match.get('metadata', {}),
                    # Include hybrid search details if available
                    'dense_score': match.get('dense_score'),
                    'sparse_score': match.get('sparse_score'),
                    'fusion_details': match.get('fusion_details')
                }
                for match in search_result['matches']
            ],
            'metadata': {
                'model': rag_result['model'],
                'tokens': rag_result['tokens'],
                'finish_reason': rag_result['finish_reason'],
                'context_chunks': len(search_result['matches']),
                'namespaces_searched': search_result.get('namespaces_searched', accessible_namespaces),
                'latency_ms': int((time.time() - start_time) * 1000),
                # Add hybrid search metadata
                'search_type': search_result.get('search_type', 'vector'),
                'hybrid_enabled': use_hybrid,
                'alpha': alpha if use_hybrid else None,
                'fusion_method': fusion_method if use_hybrid else None,
                'fusion_metadata': search_result.get('fusion_metadata')
            },
            'cached': False
        }

        # Cache the result
        if use_cache:
            cache_service.cache_query_result(g.tenant_id, query_text, response_data, ttl=3600)

        # Log the query with response
        current_app.logging_service.log_query(
            tenant_id=g.tenant_id,
            query=query_text,
            response=rag_result['answer'],
            time_ms=response_data['metadata']['latency_ms'],
            metadata={
                'tokens_used': rag_result['tokens']['total'],
                'sources_count': len(search_result['matches'])
            }
        )

        return jsonify(response_data), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500


@rag_bp.route('/search', methods=['POST'])
def search():
    """
    Search for similar vectors (without LLM generation)

    Request body:
        {
            "query": "search text...",
            "top_k": 10,  // optional, default 10
            "filter": {...}  // optional metadata filter
        }

    Returns:
        {
            "success": true,
            "results": [...],
            "count": 10
        }
    """
    start_time = time.time()

    try:
        data = request.get_json()

        if not data or 'query' not in data:
            return jsonify({
                'success': False,
                'error': 'Query is required'
            }), 400

        query_text = data['query']
        top_k = data.get('top_k', 10)
        metadata_filter = data.get('filter')

        # Generate embedding for query
        embedding_result = gemini_service.create_embedding(query_text)

        if not embedding_result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to create query embedding',
                'details': embedding_result.get('error')
            }), 500

        # Search Pinecone
        search_result = pinecone_service.query_vectors(
            tenant_namespace=g.tenant_config['pinecone_namespace'],
            query_vector=embedding_result['embedding'],
            top_k=top_k,
            filter_metadata=metadata_filter,
            include_metadata=True
        )

        if not search_result['success']:
            return jsonify({
                'success': False,
                'error': 'Vector search failed',
                'details': search_result.get('error')
            }), 500

        return jsonify({
            'success': True,
            'results': search_result['matches'],
            'count': len(search_result['matches']),
            'metadata': {
                'latency_ms': int((time.time() - start_time) * 1000),
                'embedding_tokens': embedding_result['tokens_used']
            }
        }), 200

    except Exception as e:
        current_app.logging_service.log_event(
            tenant_id=g.tenant_id,
            event_type='search_error',
            data={'error': str(e)},
            severity='error'
        )
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500


@rag_bp.route('/stats', methods=['GET'])
def stats():
    """
    Get statistics for tenant

    Returns:
        {
            "success": true,
            "stats": {
                "vector_count": 1234,
                "namespace": "tenant1",
                "cache_stats": {...}
            }
        }
    """
    try:
        # Get Pinecone stats
        pinecone_stats = pinecone_service.get_namespace_stats(
            g.tenant_config['pinecone_namespace']
        )

        # Get cache stats
        cache_stats = current_app.cache_service.get_stats()

        return jsonify({
            'success': True,
            'tenant': {
                'id': g.tenant_id,
                'name': g.tenant_config['name']
            },
            'stats': {
                'pinecone': pinecone_stats,
                'cache': cache_stats
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve stats',
            'details': str(e) if current_app.debug else None
        }), 500
