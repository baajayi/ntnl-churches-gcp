"""
BM25 Service
Handles keyword search using BM25 algorithm for hybrid retrieval
"""

import os
import re
import string
import pickle
import io
from pathlib import Path
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer, WordNetLemmatizer

# S3 support (optional)
try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    print("Note: boto3 not installed. S3 persistence unavailable for BM25 indices.")


# Download NLTK data on first import (only downloads if not already present)
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords', quiet=True)

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet', quiet=True)

try:
    nltk.data.find('corpora/omw-1.4')
except LookupError:
    nltk.download('omw-1.4', quiet=True)


class BM25Service:
    """Service for BM25 keyword-based search"""

    def __init__(
        self,
        index_dir: Optional[str] = None,
        use_stemming: bool = False,
        use_lemmatization: bool = True,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = 'bm25_indices'
    ):
        """
        Initialize BM25 service with empty indices

        Args:
            index_dir: Directory to store/load persisted indices (defaults to ./bm25_indices)
            use_stemming: Whether to use Porter Stemmer (aggressive, may reduce precision)
            use_lemmatization: Whether to use WordNet Lemmatizer (preserves real words, recommended)
            s3_bucket: Optional S3 bucket name for persistent storage (production deployment)
            s3_prefix: S3 key prefix for BM25 indices (default: 'bm25_indices')
        """
        # Store BM25 indices per namespace: {namespace: {'index': BM25Okapi, 'doc_ids': [], 'corpus': []}}
        self.indices = {}
        self.stop_words = set(stopwords.words('english'))

        # Morphological normalization options
        self.use_stemming = use_stemming
        self.use_lemmatization = use_lemmatization

        # Initialize stemmer and lemmatizer if needed
        self.stemmer = PorterStemmer() if use_stemming else None
        self.lemmatizer = WordNetLemmatizer() if use_lemmatization else None

        # Set up persistence (local or S3)
        self.s3_bucket = s3_bucket or os.getenv('BM25_S3_BUCKET')
        self.s3_prefix = s3_prefix
        self.index_dir = Path(index_dir) if index_dir else Path('./bm25_indices')
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Initialize S3 client if bucket provided
        self.s3_client = None
        if self.s3_bucket and S3_AVAILABLE:
            try:
                self.s3_client = boto3.client('s3')
                print(f"BM25: S3 persistence enabled (bucket: {self.s3_bucket}, prefix: {self.s3_prefix})")
            except Exception as e:
                print(f"BM25: Warning - Failed to initialize S3 client: {e}")
                self.s3_bucket = None

        # Auto-load existing indices on initialization
        # DISABLED: Auto-loading can cause WSL crashes due to S3 API timeouts at startup
        # Indices will be loaded on-demand when first accessed instead
        # self._auto_load_indices()

    def _preprocess(self, text: str) -> str:
        """
        Preprocess text for tokenization

        Args:
            text: Raw text string

        Returns:
            Preprocessed text (lowercase, no extra whitespace)
        """
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Remove extra whitespace
        text = ' '.join(text.split())

        return text

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize and clean text for BM25

        Applies optional stemming/lemmatization for morphological normalization

        Args:
            text: Text to tokenize

        Returns:
            List of cleaned and normalized tokens
        """
        # Preprocess
        text = self._preprocess(text)

        # Tokenize using NLTK
        try:
            tokens = word_tokenize(text)
        except Exception:
            # Fallback to simple split if NLTK fails
            tokens = text.split()

        # Remove punctuation and filter
        cleaned_tokens = []
        for token in tokens:
            # Remove punctuation
            token = token.translate(str.maketrans('', '', string.punctuation))

            # Keep if:
            # - Not empty after punctuation removal
            # - Not a stopword
            # - Length > 1 (filter out single chars)
            if token and token not in self.stop_words and len(token) > 1:
                # Apply morphological normalization
                normalized_token = self._normalize_token(token)
                cleaned_tokens.append(normalized_token)

        return cleaned_tokens

    def _normalize_token(self, token: str) -> str:
        """
        Apply morphological normalization to a token

        Args:
            token: Token to normalize

        Returns:
            Normalized token
        """
        # Priority: stemming > lemmatization (if both enabled, only stem)
        if self.use_stemming and self.stemmer:
            return self.stemmer.stem(token)
        elif self.use_lemmatization and self.lemmatizer:
            # Lemmatize as noun (most common case)
            # Could be enhanced to detect POS tags for better accuracy
            return self.lemmatizer.lemmatize(token, pos='n')
        else:
            return token

    def add_documents(
        self,
        namespace: str,
        documents: List[str],
        doc_ids: List[str],
        append: bool = False
    ) -> Dict[str, Any]:
        """
        Add documents to BM25 index for a namespace

        Args:
            namespace: Namespace identifier
            documents: List of document texts
            doc_ids: Corresponding document IDs
            append: If True, append to existing namespace instead of replacing

        Returns:
            Dict with success status and statistics
        """
        if len(documents) != len(doc_ids):
            return {
                'success': False,
                'error': 'Documents and doc_ids must have same length'
            }

        if not documents:
            return {
                'success': False,
                'error': 'No documents provided'
            }

        try:
            # Tokenize all documents
            tokenized_corpus = [self._tokenize(doc) for doc in documents]

            # Filter out empty documents
            valid_docs = []
            valid_ids = []
            valid_corpus = []

            for doc, doc_id, tokens in zip(documents, doc_ids, tokenized_corpus):
                if tokens:  # Only keep documents with at least one token
                    valid_docs.append(doc)
                    valid_ids.append(doc_id)
                    valid_corpus.append(tokens)

            if not valid_corpus:
                return {
                    'success': False,
                    'error': 'No valid documents after tokenization'
                }

            # Append to existing namespace if requested and available
            if append and namespace in self.indices:
                existing = self.indices[namespace]
                # In-place extension instead of copying (fixes memory exhaustion)
                existing['documents'].extend(valid_docs)
                existing['doc_ids'].extend(valid_ids)
                existing['corpus'].extend(valid_corpus)

                combined_docs = existing['documents']
                combined_ids = existing['doc_ids']
                combined_corpus = existing['corpus']
            else:
                combined_docs = valid_docs
                combined_ids = valid_ids
                combined_corpus = valid_corpus

            # Create BM25 index
            bm25_index = BM25Okapi(combined_corpus)

            # Store index
            self.indices[namespace] = {
                'index': bm25_index,
                'doc_ids': combined_ids,
                'corpus': combined_corpus,
                'documents': combined_docs  # Store original texts for reference
            }

            return {
                'success': True,
                'namespace': namespace,
                'document_count': len(combined_ids),
                'filtered_count': len(documents) - len(valid_ids),
                'appended': append
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to create BM25 index: {str(e)}'
            }

    def search(
        self,
        namespace: str,
        query: str,
        top_k: int = 10
    ) -> Dict[str, Any]:
        """
        Search BM25 index for relevant documents

        Args:
            namespace: Namespace to search in
            query: Query text
            top_k: Number of results to return

        Returns:
            Dict with search results
        """
        # Check if namespace exists
        if namespace not in self.indices:
            return {
                'success': False,
                'error': f'Namespace {namespace} not found in BM25 index',
                'matches': []
            }

        if not query or not query.strip():
            return {
                'success': False,
                'error': 'Empty query',
                'matches': []
            }

        try:
            # Get index data
            index_data = self.indices[namespace]
            bm25_index = index_data['index']
            doc_ids = index_data['doc_ids']

            # Tokenize query
            query_tokens = self._tokenize(query)

            if not query_tokens:
                return {
                    'success': False,
                    'error': 'Query has no valid tokens after preprocessing',
                    'matches': []
                }

            # Get BM25 scores for all documents
            scores = bm25_index.get_scores(query_tokens)

            # Sort by score (descending)
            # Create list of (score, doc_id, index) tuples
            scored_docs = [(score, doc_ids[i], i) for i, score in enumerate(scores)]
            scored_docs.sort(reverse=True, key=lambda x: x[0])

            # Take top_k results
            top_results = scored_docs[:top_k]

            # Format results
            matches = []
            for score, doc_id, idx in top_results:
                # Only include if score > 0 (has some relevance)
                if score > 0:
                    matches.append({
                        'id': doc_id,
                        'score': float(score),
                        'rank': len(matches) + 1
                    })

            return {
                'success': True,
                'matches': matches,
                'namespace': namespace,
                'query_tokens': query_tokens,
                'total_docs': len(doc_ids)
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Search failed: {str(e)}',
                'matches': []
            }

    def update_document(
        self,
        namespace: str,
        doc_id: str,
        new_text: str
    ) -> Dict[str, Any]:
        """
        Update a single document in the index
        Note: This requires rebuilding the entire index due to BM25's nature

        Args:
            namespace: Namespace identifier
            doc_id: Document ID to update
            new_text: New document text

        Returns:
            Dict with success status
        """
        if namespace not in self.indices:
            return {
                'success': False,
                'error': f'Namespace {namespace} not found'
            }

        try:
            index_data = self.indices[namespace]
            doc_ids = index_data['doc_ids']
            documents = index_data['documents']

            # Find document index
            if doc_id not in doc_ids:
                return {
                    'success': False,
                    'error': f'Document {doc_id} not found in namespace {namespace}'
                }

            doc_idx = doc_ids.index(doc_id)
            documents[doc_idx] = new_text

            # Rebuild index
            return self.add_documents(namespace, documents, doc_ids)

        except Exception as e:
            return {
                'success': False,
                'error': f'Update failed: {str(e)}'
            }

    def remove_document(
        self,
        namespace: str,
        doc_id: str
    ) -> Dict[str, Any]:
        """
        Remove a document from the index

        Args:
            namespace: Namespace identifier
            doc_id: Document ID to remove

        Returns:
            Dict with success status
        """
        if namespace not in self.indices:
            return {
                'success': False,
                'error': f'Namespace {namespace} not found'
            }

        try:
            index_data = self.indices[namespace]
            doc_ids = index_data['doc_ids']
            documents = index_data['documents']

            if doc_id not in doc_ids:
                return {
                    'success': False,
                    'error': f'Document {doc_id} not found'
                }

            # Remove document
            doc_idx = doc_ids.index(doc_id)
            del doc_ids[doc_idx]
            del documents[doc_idx]

            # Rebuild index if documents remain
            if documents:
                return self.add_documents(namespace, documents, doc_ids)
            else:
                # Clear namespace
                del self.indices[namespace]
                return {
                    'success': True,
                    'message': f'Removed last document, cleared namespace {namespace}'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Removal failed: {str(e)}'
            }

    def get_namespace_stats(self, namespace: str) -> Dict[str, Any]:
        """
        Get statistics for a namespace

        Args:
            namespace: Namespace identifier

        Returns:
            Dict with namespace statistics
        """
        if namespace not in self.indices:
            return {
                'success': False,
                'error': f'Namespace {namespace} not found',
                'document_count': 0
            }

        index_data = self.indices[namespace]

        return {
            'success': True,
            'namespace': namespace,
            'document_count': len(index_data['doc_ids']),
            'avg_doc_length': sum(len(tokens) for tokens in index_data['corpus']) / len(index_data['corpus']) if index_data['corpus'] else 0
        }

    def clear_namespace(self, namespace: str) -> Dict[str, Any]:
        """
        Clear all documents from a namespace

        Args:
            namespace: Namespace to clear

        Returns:
            Dict with success status
        """
        if namespace in self.indices:
            del self.indices[namespace]
            return {
                'success': True,
                'message': f'Cleared namespace {namespace}'
            }
        else:
            return {
                'success': False,
                'error': f'Namespace {namespace} not found'
            }

    def get_all_namespaces(self) -> List[str]:
        """
        Get list of all namespaces with BM25 indices

        Returns:
            List of namespace identifiers
        """
        return list(self.indices.keys())

    def save_index(self, namespace: str) -> Dict[str, Any]:
        """
        Save BM25 index for a namespace to S3 or local disk

        Args:
            namespace: Namespace identifier

        Returns:
            Dict with success status
        """
        if namespace not in self.indices:
            return {
                'success': False,
                'error': f'Namespace {namespace} not found'
            }

        try:
            index_data = self.indices[namespace]

            # Serialize to bytes
            buffer = io.BytesIO()
            pickle.dump(index_data, buffer)
            buffer.seek(0)
            pickle_bytes = buffer.getvalue()

            # Save to S3 if configured
            if self.s3_client and self.s3_bucket:
                s3_key = f"{self.s3_prefix}/{namespace}.pkl"

                self.s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=pickle_bytes,
                    ContentType='application/octet-stream',
                    Metadata={
                        'namespace': namespace,
                        'document_count': str(len(index_data['doc_ids'])),
                        'service': 'bm25'
                    }
                )

                return {
                    'success': True,
                    'namespace': namespace,
                    'storage': 's3',
                    's3_bucket': self.s3_bucket,
                    's3_key': s3_key,
                    'document_count': len(index_data['doc_ids']),
                    'size_bytes': len(pickle_bytes)
                }

            # Fallback to local storage
            else:
                filepath = self.index_dir / f"{namespace}.pkl"

                with open(filepath, 'wb') as f:
                    f.write(pickle_bytes)

                return {
                    'success': True,
                    'namespace': namespace,
                    'storage': 'local',
                    'filepath': str(filepath),
                    'document_count': len(index_data['doc_ids']),
                    'size_bytes': len(pickle_bytes)
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to save index: {str(e)}'
            }

    def load_index(self, namespace: str) -> Dict[str, Any]:
        """
        Load BM25 index for a namespace from S3 or local disk

        Args:
            namespace: Namespace identifier

        Returns:
            Dict with success status
        """
        try:
            # Try S3 first if configured
            if self.s3_client and self.s3_bucket:
                s3_key = f"{self.s3_prefix}/{namespace}.pkl"

                try:
                    response = self.s3_client.get_object(
                        Bucket=self.s3_bucket,
                        Key=s3_key
                    )

                    # Load from S3 bytes
                    pickle_bytes = response['Body'].read()
                    index_data = pickle.loads(pickle_bytes)

                    # Validate loaded data
                    if not isinstance(index_data, dict) or 'index' not in index_data:
                        return {
                            'success': False,
                            'error': 'Invalid index data format'
                        }

                    # Store in memory
                    self.indices[namespace] = index_data

                    return {
                        'success': True,
                        'namespace': namespace,
                        'storage': 's3',
                        's3_key': s3_key,
                        'document_count': len(index_data['doc_ids'])
                    }

                except ClientError as e:
                    if e.response['Error']['Code'] == 'NoSuchKey':
                        return {
                            'success': False,
                            'error': f'No saved index found in S3 for namespace {namespace}'
                        }
                    raise

            # Fallback to local storage
            filepath = self.index_dir / f"{namespace}.pkl"

            if not filepath.exists():
                return {
                    'success': False,
                    'error': f'No saved index found for namespace {namespace}'
                }

            # Load index data
            with open(filepath, 'rb') as f:
                index_data = pickle.load(f)

            # Validate loaded data
            if not isinstance(index_data, dict) or 'index' not in index_data:
                return {
                    'success': False,
                    'error': 'Invalid index data format'
                }

            # Store in memory
            self.indices[namespace] = index_data

            return {
                'success': True,
                'namespace': namespace,
                'storage': 'local',
                'filepath': str(filepath),
                'document_count': len(index_data['doc_ids'])
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to load index: {str(e)}'
            }

    def save_all_indices(self) -> Dict[str, Any]:
        """
        Save all BM25 indices to disk

        Returns:
            Dict with success status and results per namespace
        """
        results = {}
        for namespace in self.indices.keys():
            results[namespace] = self.save_index(namespace)

        success_count = sum(1 for r in results.values() if r.get('success'))

        return {
            'success': success_count == len(results) if results else True,
            'saved_count': success_count,
            'total_count': len(results),
            'results': results
        }

    def _auto_load_indices(self) -> None:
        """
        Automatically load all saved indices on initialization from S3 or local
        """
        try:
            # Try S3 first if configured
            if self.s3_client and self.s3_bucket:
                try:
                    response = self.s3_client.list_objects_v2(
                        Bucket=self.s3_bucket,
                        Prefix=f"{self.s3_prefix}/"
                    )

                    for obj in response.get('Contents', []):
                        key = obj['Key']
                        if key.endswith('.pkl'):
                            # Extract namespace from key: bm25_indices/namespace.pkl
                            namespace = key.split('/')[-1].replace('.pkl', '')
                            result = self.load_index(namespace)
                            if result.get('success'):
                                storage = result.get('storage', 'unknown')
                                print(f"BM25: Loaded index for namespace '{namespace}' from {storage} ({result.get('document_count', 0)} docs)")

                    return  # Exit after S3 load attempt

                except Exception as e:
                    print(f"BM25: Warning - Failed to load from S3, trying local: {str(e)}")

            # Fallback to local directory
            for filepath in self.index_dir.glob('*.pkl'):
                namespace = filepath.stem  # Filename without extension
                result = self.load_index(namespace)
                if result.get('success'):
                    print(f"BM25: Loaded index for namespace '{namespace}' from local ({result.get('document_count', 0)} docs)")

        except Exception as e:
            print(f"BM25: Warning - Failed to auto-load indices: {str(e)}")

    def delete_saved_index(self, namespace: str) -> Dict[str, Any]:
        """
        Delete saved index file from S3 or local disk

        Args:
            namespace: Namespace identifier

        Returns:
            Dict with success status
        """
        try:
            # Try S3 first if configured
            if self.s3_client and self.s3_bucket:
                s3_key = f"{self.s3_prefix}/{namespace}.pkl"

                try:
                    self.s3_client.delete_object(
                        Bucket=self.s3_bucket,
                        Key=s3_key
                    )

                    return {
                        'success': True,
                        'storage': 's3',
                        'message': f'Deleted saved index for namespace {namespace} from S3'
                    }

                except ClientError as e:
                    if e.response['Error']['Code'] != 'NoSuchKey':
                        raise

            # Fallback to local storage
            filepath = self.index_dir / f"{namespace}.pkl"

            if not filepath.exists():
                return {
                    'success': False,
                    'error': f'No saved index found for namespace {namespace}'
                }

            filepath.unlink()

            return {
                'success': True,
                'storage': 'local',
                'message': f'Deleted saved index for namespace {namespace}'
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to delete index: {str(e)}'
            }


# Singleton instance
_bm25_service = None


def get_bm25_service() -> BM25Service:
    """Get or create BM25Service singleton"""
    global _bm25_service
    if _bm25_service is None:
        _bm25_service = BM25Service()
    return _bm25_service
