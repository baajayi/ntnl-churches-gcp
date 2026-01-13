"""
Document Ingestion Routes
API endpoints for uploading and processing documents into embeddings
"""

from flask import Blueprint, request, jsonify, g, current_app
from services.pinecone_service import get_pinecone_service
from services.openai_service import get_openai_service
from werkzeug.utils import secure_filename
import os
import uuid
import time
import re
import requests
from typing import List, Dict, Any

# PDF and DOCX support
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    import docx
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False

ingestion_bp = Blueprint('ingestion', __name__)

# Get services
pinecone_service = get_pinecone_service()
openai_service = get_openai_service()

# Allowed file extensions
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'md'}
MAX_CHUNK_SIZE = 1000  # characters
CHUNK_OVERLAP = 200  # characters overlap between chunks
EMBED_BATCH_SIZE = int(os.getenv('INGEST_EMBED_BATCH_SIZE', '32'))
UPSERT_BATCH_SIZE = int(os.getenv('INGEST_UPSERT_BATCH_SIZE', '100'))


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def chunk_text(text: str, chunk_size: int = MAX_CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping chunks

    Args:
        text: Text to chunk
        chunk_size: Maximum size of each chunk
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence endings
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


def embed_chunks_iter(chunks: List[str]):
    """Yield chunk index, chunk text, and embedding in manageable batches."""
    total = len(chunks)
    for start in range(0, total, EMBED_BATCH_SIZE):
        batch = chunks[start:start + EMBED_BATCH_SIZE]
        result = openai_service.create_embeddings_batch(batch)
        if not result['success']:
            raise RuntimeError(f"Embedding batch failed: {result.get('error', 'unknown error')}")

        for offset, embedding in enumerate(result['embeddings']):
            yield start + offset, batch[offset], embedding


def upsert_vector_batch(namespace: str, vectors: List[Dict[str, Any]]):
    """Upload a batch of vectors to Pinecone."""
    if not vectors:
        return

    result = pinecone_service.upsert_vectors(
        tenant_namespace=namespace,
        vectors=vectors
    )

    if not result['success']:
        raise RuntimeError(f"Pinecone upsert failed: {result.get('error', 'unknown error')}")


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF file"""
    if not PDF_SUPPORT:
        raise Exception("PDF support not installed. Install PyPDF2.")

    text = ""
    with open(file_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"

    return text


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX file"""
    if not DOCX_SUPPORT:
        raise Exception("DOCX support not installed. Install python-docx.")

    doc = docx.Document(file_path)
    text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
    return text


def extract_text_from_file(file_path: str, file_ext: str) -> str:
    """Extract text from various file formats"""
    if file_ext == 'pdf':
        return extract_text_from_pdf(file_path)
    elif file_ext == 'docx':
        return extract_text_from_docx(file_path)
    elif file_ext in ['txt', 'md']:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        raise Exception(f"Unsupported file type: {file_ext}")


@ingestion_bp.route('/ingest/text', methods=['POST'])
def ingest_text():
    """
    Ingest raw text documents

    Request body:
        {
            "texts": [
                {
                    "content": "Document text...",
                    "metadata": {"source": "doc1", ...}  // optional
                }
            ],
            "chunk_size": 1000,  // optional
            "chunk_overlap": 200  // optional
        }

    Returns:
        {
            "success": true,
            "ingested_chunks": 45,
            "vector_ids": [...]
        }
    """
    start_time = time.time()

    try:
        data = request.get_json()

        if not data or 'texts' not in data:
            return jsonify({
                'success': False,
                'error': 'texts array is required'
            }), 400

        texts = data['texts']
        chunk_size = data.get('chunk_size', MAX_CHUNK_SIZE)
        overlap = data.get('chunk_overlap', CHUNK_OVERLAP)

        namespace = g.tenant_config['pinecone_namespace']
        vector_ids: List[str] = []
        chunk_count = 0
        buffer: List[Dict[str, Any]] = []

        # Process each text document
        for doc in texts:
            if not isinstance(doc, dict) or 'content' not in doc:
                continue

            content = doc['content']
            if not content or not content.strip():
                continue
            metadata = doc.get('metadata', {})

            # Chunk the text
            chunks = chunk_text(content, chunk_size, overlap)

            # Stream embeddings and upload in batches to reduce memory usage
            try:
                total_chunks = len(chunks)
                for chunk_index, chunk_text_value, embedding in embed_chunks_iter(chunks):
                    vector_id = str(uuid.uuid4())
                    chunk_metadata = {
                        **metadata,
                        'text': chunk_text_value,
                        'chunk_index': chunk_index,
                        'total_chunks': total_chunks,
                        'ingested_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    }

                    buffer.append({
                        'id': vector_id,
                        'values': embedding,
                        'metadata': chunk_metadata
                    })

                    vector_ids.append(vector_id)
                    chunk_count += 1

                    if len(buffer) >= UPSERT_BATCH_SIZE:
                        upsert_vector_batch(namespace, buffer)
                        buffer.clear()
            except RuntimeError as err:
                return jsonify({
                    'success': False,
                    'error': 'Failed to create embeddings',
                    'details': str(err)
                }), 500

        # Flush remaining vectors
        try:
            upsert_vector_batch(namespace, buffer)
        except RuntimeError as err:
            return jsonify({
                'success': False,
                'error': 'Failed to upsert vectors',
                'details': str(err)
            }), 500

        # Log ingestion
        current_app.logging_service.log_event(
            tenant_id=g.tenant_id,
            event_type='text_ingestion',
            data={
                'documents_count': len(texts),
                'chunks_count': chunk_count,
                'latency_ms': int((time.time() - start_time) * 1000)
            }
        )

        return jsonify({
            'success': True,
            'ingested_documents': len(texts),
            'ingested_chunks': chunk_count,
            'vector_ids': vector_ids,
            'metadata': {
                'latency_ms': int((time.time() - start_time) * 1000)
            }
        }), 200

    except Exception as e:
        current_app.logging_service.log_event(
            tenant_id=g.tenant_id,
            event_type='ingestion_error',
            data={'error': str(e)},
            severity='error'
        )
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500


@ingestion_bp.route('/ingest/file', methods=['POST'])
def ingest_file():
    """
    Ingest document files (PDF, DOCX, TXT, MD)

    Form data:
        file: Document file
        metadata: JSON string with optional metadata

    Returns:
        {
            "success": true,
            "ingested_chunks": 23,
            "vector_ids": [...]
        }
    """
    start_time = time.time()

    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'Empty filename'
            }), 400

        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': f'File type not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'
            }), 400

        # Get metadata if provided
        import json as json_lib
        metadata = {}
        if 'metadata' in request.form:
            try:
                metadata = json_lib.loads(request.form['metadata'])
            except json_lib.JSONDecodeError:
                pass

        # Save file temporarily
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        temp_path = f"/tmp/{uuid.uuid4()}_{filename}"

        file.save(temp_path)

        try:
            # Extract text
            text = extract_text_from_file(temp_path, file_ext)

            # Add source to metadata
            metadata['source'] = filename
            metadata['file_type'] = file_ext

            # Chunk text
            chunks = chunk_text(text)

            namespace = g.tenant_config['pinecone_namespace']
            vector_ids: List[str] = []
            buffer: List[Dict[str, Any]] = []

            try:
                total_chunks = len(chunks)
                for chunk_index, chunk_text_value, embedding in embed_chunks_iter(chunks):
                    vector_id = str(uuid.uuid4())
                    chunk_metadata = {
                        **metadata,
                        'text': chunk_text_value,
                        'chunk_index': chunk_index,
                        'total_chunks': total_chunks,
                        'ingested_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    }

                    buffer.append({
                        'id': vector_id,
                        'values': embedding,
                        'metadata': chunk_metadata
                    })

                    vector_ids.append(vector_id)

                    if len(buffer) >= UPSERT_BATCH_SIZE:
                        upsert_vector_batch(namespace, buffer)
                        buffer.clear()

                upsert_vector_batch(namespace, buffer)
            except RuntimeError as err:
                return jsonify({
                    'success': False,
                    'error': 'Failed to upsert vectors',
                    'details': str(err)
                }), 500

            # Log ingestion
            current_app.logging_service.log_event(
                tenant_id=g.tenant_id,
                event_type='file_ingestion',
                data={
                    'filename': filename,
                    'file_type': file_ext,
                    'chunks_count': len(chunks),
                    'latency_ms': int((time.time() - start_time) * 1000)
                }
            )

            return jsonify({
                'success': True,
                'filename': filename,
                'ingested_chunks': len(chunks),
                'vector_ids': vector_ids,
                'metadata': {
                    'latency_ms': int((time.time() - start_time) * 1000)
                }
            }), 200

        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        current_app.logging_service.log_event(
            tenant_id=g.tenant_id,
            event_type='file_ingestion_error',
            data={'error': str(e)},
            severity='error'
        )
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500


@ingestion_bp.route('/ingest/url', methods=['POST'])
def ingest_url():
    """
    Fetch and ingest content from URL

    Request body:
        {
            "url": "https://example.com/article",
            "metadata": {...}  // optional
        }

    Returns:
        {
            "success": true,
            "ingested_chunks": 15,
            "vector_ids": [...]
        }
    """
    start_time = time.time()

    try:
        data = request.get_json()

        if not data or 'url' not in data:
            return jsonify({
                'success': False,
                'error': 'URL is required'
            }), 400

        url = data['url']
        metadata = data.get('metadata', {})

        # Fetch URL content
        try:
            response = requests.get(url, timeout=30, headers={
                'User-Agent': 'MultitentantRAG/1.0'
            })
            response.raise_for_status()
            content = response.text

            # Simple HTML to text (you may want to use BeautifulSoup for better extraction)
            # Remove HTML tags
            content = re.sub('<script.*?</script>', '', content, flags=re.DOTALL)
            content = re.sub('<style.*?</style>', '', content, flags=re.DOTALL)
            content = re.sub('<.*?>', '', content)
            content = re.sub(r'\s+', ' ', content).strip()

        except requests.RequestException as e:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch URL',
                'details': str(e)
            }), 400

        # Add source to metadata
        metadata['source'] = url
        metadata['source_type'] = 'url'

        # Chunk text
        chunks = chunk_text(content)

        namespace = g.tenant_config['pinecone_namespace']
        vector_ids: List[str] = []
        buffer: List[Dict[str, Any]] = []

        try:
            total_chunks = len(chunks)
            for chunk_index, chunk_text_value, embedding in embed_chunks_iter(chunks):
                vector_id = str(uuid.uuid4())
                chunk_metadata = {
                    **metadata,
                    'text': chunk_text_value,
                    'chunk_index': chunk_index,
                    'total_chunks': total_chunks,
                    'ingested_at': time.strftime('%Y-%m-%d %H:%M:%S')
                }

                buffer.append({
                    'id': vector_id,
                    'values': embedding,
                    'metadata': chunk_metadata
                })

                vector_ids.append(vector_id)

                if len(buffer) >= UPSERT_BATCH_SIZE:
                    upsert_vector_batch(namespace, buffer)
                    buffer.clear()

            upsert_vector_batch(namespace, buffer)
        except RuntimeError as err:
            return jsonify({
                'success': False,
                'error': 'Failed to upsert vectors',
                'details': str(err)
            }), 500

        # Log ingestion
        current_app.logging_service.log_event(
            tenant_id=g.tenant_id,
            event_type='url_ingestion',
            data={
                'url': url,
                'chunks_count': len(chunks),
                'latency_ms': int((time.time() - start_time) * 1000)
            }
        )

        return jsonify({
            'success': True,
            'url': url,
            'ingested_chunks': len(chunks),
            'vector_ids': vector_ids,
            'metadata': {
                'latency_ms': int((time.time() - start_time) * 1000)
            }
        }), 200

    except Exception as e:
        current_app.logging_service.log_event(
            tenant_id=g.tenant_id,
            event_type='url_ingestion_error',
            data={'error': str(e)},
            severity='error'
        )
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500


@ingestion_bp.route('/delete', methods=['POST'])
def delete_vectors():
    """
    Delete vectors by ID or filter

    Request body:
        {
            "ids": ["id1", "id2"],  // optional
            "filter": {...},  // optional
            "delete_all": false  // optional
        }

    Returns:
        {
            "success": true,
            "message": "..."
        }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body required'
            }), 400

        result = pinecone_service.delete_vectors(
            tenant_namespace=g.tenant_config['pinecone_namespace'],
            ids=data.get('ids'),
            delete_all=data.get('delete_all', False),
            filter_metadata=data.get('filter')
        )

        if not result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to delete vectors',
                'details': result.get('error')
            }), 500

        # Log deletion
        current_app.logging_service.log_event(
            tenant_id=g.tenant_id,
            event_type='vectors_deleted',
            data={
                'ids_count': len(data.get('ids', [])),
                'delete_all': data.get('delete_all', False)
            }
        )

        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500
