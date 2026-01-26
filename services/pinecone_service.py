"""
Pinecone Service
Handles vector database operations with namespace-based tenant isolation
"""

import os
from typing import List, Dict, Any, Optional
from pinecone import Pinecone, ServerlessSpec
import time
from dotenv import load_dotenv

load_dotenv()


class PineconeService:
    """Service for interacting with Pinecone vector database"""

    def __init__(self):
        """Initialize Pinecone client"""
        self.api_key = os.getenv('PINECONE_API_KEY')
        self.environment = os.getenv('PINECONE_ENVIRONMENT', 'us-east-1')
        self.index_name = os.getenv('PINECONE_INDEX_NAME', 'multitenant-rag')

        if not self.api_key:
            print("WARNING: PINECONE_API_KEY environment variable not set")
            self.pc = None
            self.index = None
            return

        # Initialize Pinecone
        self.pc = Pinecone(api_key=self.api_key)

        # Get or create index
        self.index = self._get_or_create_index()

    def _check_client(self):
        """Check if client is initialized"""
        if self.pc is None or self.index is None:
            return {
                'success': False,
                'error': 'Pinecone client not initialized. PINECONE_API_KEY environment variable is required.'
            }
        return None

    def _get_or_create_index(self):
        """Get existing index or create new one"""
        try:
            # Check if index exists
            if self.index_name not in self.pc.list_indexes().names():
                print(f"Creating Pinecone index: {self.index_name}")

                # Create index with serverless spec
                self.pc.create_index(
                    name=self.index_name,
                    dimension=3072,  # Gemini gemini-embedding-001 with output_dimensionality=3072
                    metric='cosine',
                    spec=ServerlessSpec(
                        cloud='aws',
                        region=self.environment
                    )
                )

                # Wait for index to be ready
                while not self.pc.describe_index(self.index_name).status['ready']:
                    time.sleep(1)

            return self.pc.Index(self.index_name)

        except Exception as e:
            raise Exception(f"Failed to initialize Pinecone index: {str(e)}")

    def upsert_vectors(
        self,
        tenant_namespace: str,
        vectors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Upsert vectors to Pinecone with tenant isolation

        Args:
            tenant_namespace: Tenant's namespace for isolation
            vectors: List of dicts with 'id', 'values', and optional 'metadata'

        Returns:
            Dict with upsert statistics
        """
        error = self._check_client()
        if error:
            return error

        try:
            # Upsert to tenant's namespace
            result = self.index.upsert(
                vectors=vectors,
                namespace=tenant_namespace
            )

            return {
                'success': True,
                'upserted_count': result.upserted_count,
                'namespace': tenant_namespace
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def query_vectors(
        self,
        tenant_namespace: str,
        query_vector: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True,
        include_values: bool = False
    ) -> Dict[str, Any]:
        """
        Query vectors in tenant's namespace

        Args:
            tenant_namespace: Tenant's namespace
            query_vector: Query embedding vector
            top_k: Number of results to return
            filter_metadata: Optional metadata filters
            include_metadata: Include metadata in results
            include_values: Include vector values in results

        Returns:
            Dict with query results
        """
        error = self._check_client()
        if error:
            return error

        try:
            result = self.index.query(
                namespace=tenant_namespace,
                vector=query_vector,
                top_k=top_k,
                filter=filter_metadata,
                include_metadata=include_metadata,
                include_values=include_values
            )

            # Format results
            matches = []
            for match in result.matches:
                match_data = {
                    'id': match.id,
                    'score': match.score
                }

                if include_metadata and hasattr(match, 'metadata'):
                    match_data['metadata'] = match.metadata

                if include_values and hasattr(match, 'values'):
                    match_data['values'] = match.values

                matches.append(match_data)

            return {
                'success': True,
                'matches': matches,
                'namespace': tenant_namespace
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'matches': []
            }

    def delete_vectors(
        self,
        tenant_namespace: str,
        ids: Optional[List[str]] = None,
        delete_all: bool = False,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Delete vectors from tenant's namespace

        Args:
            tenant_namespace: Tenant's namespace
            ids: List of vector IDs to delete
            delete_all: Delete all vectors in namespace
            filter_metadata: Delete vectors matching filter

        Returns:
            Dict with deletion status
        """
        error = self._check_client()
        if error:
            return error

        try:
            if delete_all:
                self.index.delete(
                    delete_all=True,
                    namespace=tenant_namespace
                )
                message = f"Deleted all vectors in namespace {tenant_namespace}"

            elif ids:
                self.index.delete(
                    ids=ids,
                    namespace=tenant_namespace
                )
                message = f"Deleted {len(ids)} vectors"

            elif filter_metadata:
                self.index.delete(
                    filter=filter_metadata,
                    namespace=tenant_namespace
                )
                message = "Deleted vectors matching filter"

            else:
                return {
                    'success': False,
                    'error': 'Must provide ids, delete_all=True, or filter_metadata'
                }

            return {
                'success': True,
                'message': message,
                'namespace': tenant_namespace
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_namespace_stats(self, tenant_namespace: str) -> Dict[str, Any]:
        """
        Get statistics for tenant's namespace

        Args:
            tenant_namespace: Tenant's namespace

        Returns:
            Dict with namespace statistics
        """
        error = self._check_client()
        if error:
            return error

        try:
            stats = self.index.describe_index_stats()

            # Get namespace-specific stats
            namespace_stats = stats.namespaces.get(tenant_namespace, {})

            return {
                'success': True,
                'namespace': tenant_namespace,
                'vector_count': namespace_stats.get('vector_count', 0),
                'index_fullness': stats.index_fullness,
                'dimension': stats.dimension,
                'total_vector_count': stats.total_vector_count
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def query_multiple_namespaces(
        self,
        namespaces: List[str],
        query_vector: List[float],
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True,
        tenant_namespace_boost: float = 1.25
    ) -> Dict[str, Any]:
        """
        Query vectors across multiple namespaces and merge results

        IMPORTANT: The first namespace in the list is considered the "primary tenant namespace"
        and its scores will be boosted to ensure tenant-specific content is prioritized over
        generic shared content.

        Args:
            namespaces: List of namespaces to search (first is primary/tenant namespace)
            query_vector: Query embedding vector
            top_k: Total number of results to return (across all namespaces)
            filter_metadata: Optional metadata filters
            include_metadata: Include metadata in results
            tenant_namespace_boost: Multiplier for primary namespace scores (default 1.25 = 25% boost)

        Returns:
            Dict with merged query results sorted by score
        """
        error = self._check_client()
        if error:
            return error

        try:
            all_matches = []
            primary_namespace = namespaces[0] if namespaces else None

            # Query each namespace
            for namespace in namespaces:
                result = self.index.query(
                    namespace=namespace,
                    vector=query_vector,
                    top_k=top_k,  # Get top_k from each namespace
                    filter=filter_metadata,
                    include_metadata=include_metadata,
                    include_values=False
                )

                # Add namespace to each match and apply score boost for primary namespace
                for match in result.matches:
                    # Boost primary tenant namespace scores to prioritize tenant-specific content
                    boosted_score = match.score
                    if namespace == primary_namespace and tenant_namespace_boost > 1.0:
                        boosted_score = match.score * tenant_namespace_boost

                    match_data = {
                        'id': match.id,
                        'score': boosted_score,  # Use boosted score for sorting
                        'original_score': match.score,  # Keep original for debugging
                        'namespace': namespace  # Track which namespace it came from
                    }

                    if include_metadata and hasattr(match, 'metadata'):
                        match_data['metadata'] = match.metadata

                    all_matches.append(match_data)

            # Sort all matches by boosted score (highest first)
            all_matches.sort(key=lambda x: x['score'], reverse=True)

            # Return top_k results across all namespaces
            top_matches = all_matches[:top_k]

            return {
                'success': True,
                'matches': top_matches,
                'namespaces_searched': namespaces,
                'total_candidates': len(all_matches),
                'boost_applied': tenant_namespace_boost if primary_namespace else None
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'matches': []
            }

    def fetch_vectors(
        self,
        tenant_namespace: str,
        ids: List[str]
    ) -> Dict[str, Any]:
        """
        Fetch specific vectors by ID

        Args:
            tenant_namespace: Tenant's namespace
            ids: List of vector IDs to fetch

        Returns:
            Dict with fetched vectors
        """
        error = self._check_client()
        if error:
            return error

        try:
            result = self.index.fetch(
                ids=ids,
                namespace=tenant_namespace
            )

            vectors = {}
            for vector_id, vector_data in result.vectors.items():
                vectors[vector_id] = {
                    'id': vector_id,
                    'values': vector_data.values if hasattr(vector_data, 'values') else None,
                    'metadata': vector_data.metadata if hasattr(vector_data, 'metadata') else None
                }

            return {
                'success': True,
                'vectors': vectors,
                'namespace': tenant_namespace
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'vectors': {}
            }

    def hybrid_query(
        self,
        tenant_namespace: str,
        query_vector: List[float],
        query_text: str,
        bm25_service,
        top_k: int = 5,
        alpha: float = 0.7,
        fusion_method: str = 'rrf',
        filter_metadata: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Perform hybrid search combining dense (vector) and sparse (BM25) retrieval

        Args:
            tenant_namespace: Tenant's namespace
            query_vector: Query embedding vector (dense)
            query_text: Query text for BM25 (sparse)
            bm25_service: BM25Service instance
            top_k: Number of results to return
            alpha: Weight for dense vs sparse (0.7 = 70% dense, 30% sparse)
            fusion_method: 'rrf' (Reciprocal Rank Fusion) or 'weighted'
            filter_metadata: Optional metadata filters
            include_metadata: Include metadata in results

        Returns:
            Dict with hybrid search results
        """
        from services.hybrid_search import hybrid_search

        error = self._check_client()
        if error:
            return error

        try:
            # 1. Perform dense (semantic) search via Pinecone
            dense_result = self.query_vectors(
                tenant_namespace=tenant_namespace,
                query_vector=query_vector,
                top_k=top_k * 2,  # Retrieve more for better fusion
                filter_metadata=filter_metadata,
                include_metadata=include_metadata
            )

            if not dense_result['success']:
                return dense_result

            # 2. Perform sparse (keyword) search via BM25
            sparse_result = bm25_service.search(
                namespace=tenant_namespace,
                query=query_text,
                top_k=top_k * 2  # Retrieve more for better fusion
            )

            # If BM25 search fails, fall back to pure dense search
            if not sparse_result['success']:
                print(f"Warning: BM25 search failed, falling back to pure vector search: {sparse_result.get('error')}")
                # Return dense results only
                dense_matches = dense_result['matches'][:top_k]
                return {
                    'success': True,
                    'matches': dense_matches,
                    'namespace': tenant_namespace,
                    'search_type': 'dense_only',
                    'warning': 'BM25 search failed, using dense search only'
                }

            # 3. Merge results using hybrid fusion
            fusion_result = hybrid_search(
                dense_results=dense_result['matches'],
                sparse_results=sparse_result['matches'],
                method=fusion_method,
                alpha=alpha,
                top_k=top_k
            )

            if not fusion_result['success']:
                # Fall back to dense search if fusion fails
                print(f"Warning: Fusion failed, falling back to pure vector search: {fusion_result.get('error')}")
                dense_matches = dense_result['matches'][:top_k]
                return {
                    'success': True,
                    'matches': dense_matches,
                    'namespace': tenant_namespace,
                    'search_type': 'dense_only',
                    'warning': 'Fusion failed, using dense search only'
                }

            # Add namespace to results
            for match in fusion_result['matches']:
                if 'namespace' not in match:
                    match['namespace'] = tenant_namespace

            return {
                'success': True,
                'matches': fusion_result['matches'],
                'namespace': tenant_namespace,
                'search_type': 'hybrid',
                'fusion_metadata': fusion_result['metadata']
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Hybrid search failed: {str(e)}',
                'matches': []
            }

    def hybrid_query_multiple_namespaces(
        self,
        namespaces: List[str],
        query_vector: List[float],
        query_text: str,
        bm25_service,
        top_k: int = 5,
        alpha: float = 0.7,
        fusion_method: str = 'rrf',
        tenant_namespace_boost: float = 1.25,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perform hybrid search across multiple namespaces with result merging

        Args:
            namespaces: List of namespaces to search (first is primary)
            query_vector: Query embedding vector
            query_text: Query text for BM25
            bm25_service: BM25Service instance
            top_k: Total number of results to return
            alpha: Weight for dense vs sparse
            fusion_method: 'rrf' or 'weighted'
            tenant_namespace_boost: Score multiplier for primary namespace
            filter_metadata: Optional metadata filters

        Returns:
            Dict with merged hybrid search results
        """
        from services.hybrid_search import hybrid_search

        error = self._check_client()
        if error:
            return error

        try:
            all_matches = []
            primary_namespace = namespaces[0] if namespaces else None

            # Perform hybrid search in each namespace
            for namespace in namespaces:
                namespace_result = self.hybrid_query(
                    tenant_namespace=namespace,
                    query_vector=query_vector,
                    query_text=query_text,
                    bm25_service=bm25_service,
                    top_k=top_k,  # Get top_k from each namespace
                    alpha=alpha,
                    fusion_method=fusion_method,
                    filter_metadata=filter_metadata,
                    include_metadata=True
                )

                if namespace_result['success']:
                    # Apply boost to primary namespace
                    for match in namespace_result['matches']:
                        if namespace == primary_namespace and tenant_namespace_boost > 1.0:
                            match['score'] = match['score'] * tenant_namespace_boost
                            match['boosted'] = True
                        match['namespace'] = namespace
                        all_matches.append(match)

            # Sort all matches by score (highest first)
            all_matches.sort(key=lambda x: x['score'], reverse=True)

            # Return top_k results across all namespaces
            top_matches = all_matches[:top_k]

            return {
                'success': True,
                'matches': top_matches,
                'namespaces_searched': namespaces,
                'total_candidates': len(all_matches),
                'boost_applied': tenant_namespace_boost if primary_namespace else None,
                'search_type': 'hybrid_multi_namespace'
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Multi-namespace hybrid search failed: {str(e)}',
                'matches': []
            }


# Singleton instance
_pinecone_service = None


def get_pinecone_service() -> PineconeService:
    """Get or create PineconeService singleton"""
    global _pinecone_service
    if _pinecone_service is None:
        _pinecone_service = PineconeService()
    return _pinecone_service
