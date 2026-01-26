"""
Gemini Service (Vertex AI)
Handles embeddings generation and LLM completions for RAG using Google Vertex AI
Uses IAM authentication (no API keys required)
"""

import os
from typing import List, Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Vertex AI imports
import vertexai
from vertexai.generative_models import GenerativeModel, Part, Content
from vertexai.language_models import TextEmbeddingModel
from google.api_core import exceptions as google_exceptions


class GeminiService:
    """Service for interacting with Google Vertex AI (Gemini)"""

    def __init__(self):
        """Initialize Vertex AI client with IAM authentication"""
        self.project_id = os.getenv('GCP_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT')
        self.location = os.getenv('GCP_LOCATION', 'us-central1')

        if not self.project_id:
            print("WARNING: GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable not set")
            self.initialized = False
            return

        try:
            # Initialize Vertex AI with project and location
            # Uses Application Default Credentials (ADC) automatically
            vertexai.init(project=self.project_id, location=self.location)

            # Model configurations
            self.chat_model_name = os.getenv('GEMINI_CHAT_MODEL', 'gemini-2.0-flash')
            self.embedding_model_name = os.getenv('GEMINI_EMBEDDING_MODEL', 'text-embedding-005')
            self.embedding_dimension = int(os.getenv('GEMINI_EMBEDDING_DIMENSION', '3072'))
            self.max_tokens = int(os.getenv('GEMINI_MAX_TOKENS', '1000'))

            # Initialize models
            self.chat_model = GenerativeModel(self.chat_model_name)
            self.embedding_model = TextEmbeddingModel.from_pretrained(self.embedding_model_name)

            self.initialized = True
            print(f"Gemini service initialized (project: {self.project_id}, location: {self.location})")

        except Exception as e:
            print(f"WARNING: Failed to initialize Vertex AI: {e}")
            self.initialized = False

    def _check_client(self):
        """Check if client is initialized"""
        if not self.initialized:
            return {
                'success': False,
                'error': 'Gemini client not initialized. GCP_PROJECT_ID environment variable is required.'
            }
        return None

    def create_embedding(self, text: str) -> Dict[str, Any]:
        """
        Create embedding for text

        Args:
            text: Text to embed

        Returns:
            Dict with embedding vector and metadata
        """
        error = self._check_client()
        if error:
            return error

        try:
            # Clean text
            text = text.replace("\n", " ").strip()

            if not text:
                return {
                    'success': False,
                    'error': 'Empty text provided'
                }

            # Create embedding using Vertex AI with specified dimension
            embeddings = self.embedding_model.get_embeddings(
                [text],
                output_dimensionality=self.embedding_dimension
            )

            if not embeddings or not embeddings[0].values:
                return {
                    'success': False,
                    'error': 'No embedding returned from model'
                }

            embedding = embeddings[0].values

            return {
                'success': True,
                'embedding': embedding,
                'dimension': len(embedding),
                'model': self.embedding_model_name,
                'tokens_used': self._estimate_tokens(text)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def create_embeddings_batch(self, texts: List[str]) -> Dict[str, Any]:
        """
        Create embeddings for multiple texts with automatic retry on transient failures

        Args:
            texts: List of texts to embed

        Returns:
            Dict with list of embeddings and metadata
        """
        error = self._check_client()
        if error:
            return error

        # Clean texts first
        texts = [text.replace("\n", " ").strip() for text in texts]
        texts = [text for text in texts if text]  # Remove empty strings

        if not texts:
            return {
                'success': False,
                'error': 'No valid texts provided'
            }

        # Define the retry-able function
        @retry(
            retry=retry_if_exception_type((
                google_exceptions.ServiceUnavailable,
                google_exceptions.DeadlineExceeded,
                google_exceptions.ResourceExhausted
            )),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(3),
            reraise=True
        )
        def _create_embeddings_with_retry():
            return self.embedding_model.get_embeddings(
                texts,
                output_dimensionality=self.embedding_dimension
            )

        try:
            # Call with retry logic
            embeddings_response = _create_embeddings_with_retry()

            embeddings = [emb.values for emb in embeddings_response]

            # Estimate tokens (Vertex AI doesn't return token count for embeddings)
            tokens_used = sum(self._estimate_tokens(text) for text in texts)

            return {
                'success': True,
                'embeddings': embeddings,
                'count': len(embeddings),
                'dimension': len(embeddings[0]) if embeddings else 0,
                'model': self.embedding_model_name,
                'tokens_used': tokens_used
            }

        except (google_exceptions.ServiceUnavailable, google_exceptions.DeadlineExceeded,
                google_exceptions.ResourceExhausted) as e:
            # Retry exhausted - return error dict instead of crashing
            return {
                'success': False,
                'error': f'Vertex AI API error after 3 retries: {str(e)}',
                'error_type': type(e).__name__
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def generate_rag_response(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate response using RAG (Retrieval Augmented Generation)

        Args:
            query: User's question
            context_chunks: List of relevant context chunks from vector search
            system_prompt: Optional system prompt
            temperature: Response randomness (0-1)
            max_tokens: Maximum tokens in response
            conversation_history: Optional list of previous Q&A pairs [{"query": "...", "answer": "..."}]

        Returns:
            Dict with generated response and metadata
        """
        error = self._check_client()
        if error:
            return error

        try:
            # Build context from chunks
            context_text = self._build_context(context_chunks)

            # Default system prompt with conversation awareness
            if not system_prompt:
                system_prompt = (
                    "You are a helpful assistant engaged in a conversation with the user. "
                    "Answer the user's question based on the provided context. "
                    "IMPORTANT: You are having a conversation with the user. Pay attention to the conversation history provided. "
                    "When the user asks follow-up questions or uses pronouns (it, that, they, etc.), "
                    "refer back to the conversation history to understand what they're referring to. "
                    "If the context doesn't contain relevant information, say so clearly. "
                    "Be conversational and maintain continuity with previous exchanges."
                )

            # Build conversation contents for Gemini
            contents = []

            # Add conversation history if provided
            if conversation_history:
                for exchange in conversation_history[-5:]:  # Keep last 5 exchanges
                    # User message
                    contents.append(Content(
                        role="user",
                        parts=[Part.from_text(exchange.get('query', ''))]
                    ))
                    # Model response
                    contents.append(Content(
                        role="model",
                        parts=[Part.from_text(exchange.get('answer', ''))]
                    ))

            # Add current query with context
            current_message = f"Context:\n{context_text}\n\nQuestion: {query}"
            contents.append(Content(
                role="user",
                parts=[Part.from_text(current_message)]
            ))

            # Count tokens for prompt
            prompt_tokens = self._count_tokens_contents(contents, system_prompt)

            # Generate response using Gemini
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens or self.max_tokens,
            }

            # Create model with system instruction
            model_with_system = GenerativeModel(
                self.chat_model_name,
                system_instruction=system_prompt
            )

            response = model_with_system.generate_content(
                contents,
                generation_config=generation_config
            )

            answer = response.text
            finish_reason = response.candidates[0].finish_reason.name if response.candidates else 'UNKNOWN'

            # Get token counts from response metadata if available
            completion_tokens = self._estimate_tokens(answer)

            return {
                'success': True,
                'answer': answer,
                'model': self.chat_model_name,
                'tokens': {
                    'prompt': prompt_tokens,
                    'completion': completion_tokens,
                    'total': prompt_tokens + completion_tokens
                },
                'finish_reason': finish_reason,
                'context_chunks_used': len(context_chunks)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _build_context(self, chunks: List[Dict[str, Any]]) -> str:
        """Build context string from retrieved chunks with full metadata"""
        context_parts = []

        for i, chunk in enumerate(chunks, 1):
            metadata = chunk.get('metadata', {})
            # Prefer full_text (complete chunk) over text_snippet (truncated) for better context
            text = metadata.get('full_text') or metadata.get('text_snippet') or metadata.get('text', '')
            source = metadata.get('source', 'Unknown')
            score = chunk.get('score', 0)

            # Skip empty chunks
            if not text.strip():
                continue

            # Build context entry with metadata
            context_entry = f"[{i}] (Relevance: {score:.2f}, Source: {source})"

            # If this is a sermon with metadata_context, include it
            if metadata.get('metadata_context'):
                context_entry += f"\n{metadata['metadata_context']}\n"
            # Otherwise, include basic metadata if available
            elif metadata.get('title') or metadata.get('preacher'):
                meta_parts = []
                if metadata.get('title'):
                    meta_parts.append(f"Title: {metadata['title']}")
                if metadata.get('preacher'):
                    meta_parts.append(f"Preacher: {metadata['preacher']}")
                if metadata.get('date_preached'):
                    meta_parts.append(f"Date: {metadata['date_preached']}")
                if metadata.get('scripture_references'):
                    meta_parts.append(f"Scripture: {metadata['scripture_references']}")
                if metadata.get('key_themes'):
                    meta_parts.append(f"Themes: {metadata['key_themes']}")

                if meta_parts:
                    context_entry += f"\n{', '.join(meta_parts)}\n"

            # Add the actual text content
            context_entry += f"\n{text}"

            context_parts.append(context_entry)

        return "\n\n".join(context_parts)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation for Gemini)"""
        # Gemini uses a similar tokenization to other modern LLMs
        # Rough estimate: ~4 characters per token
        return len(text) // 4

    def _count_tokens_contents(self, contents: List[Content], system_prompt: str) -> int:
        """Count tokens in conversation contents"""
        total = self._estimate_tokens(system_prompt)
        for content in contents:
            for part in content.parts:
                if hasattr(part, 'text'):
                    total += self._estimate_tokens(part.text)
        return total

    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a chat response without RAG context

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Response randomness (0-1)
            max_tokens: Maximum tokens in response

        Returns:
            Dict with generated response and metadata
        """
        error = self._check_client()
        if error:
            return error

        try:
            # Convert messages to Gemini format
            contents = []
            system_prompt = None

            for msg in messages:
                role = msg.get('role', '')
                content = msg.get('content', '')

                if role == 'system':
                    system_prompt = content
                elif role == 'user':
                    contents.append(Content(
                        role="user",
                        parts=[Part.from_text(content)]
                    ))
                elif role == 'assistant':
                    contents.append(Content(
                        role="model",
                        parts=[Part.from_text(content)]
                    ))

            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens or self.max_tokens,
            }

            # Create model with system instruction if provided
            if system_prompt:
                model = GenerativeModel(
                    self.chat_model_name,
                    system_instruction=system_prompt
                )
            else:
                model = self.chat_model

            response = model.generate_content(
                contents,
                generation_config=generation_config
            )

            answer = response.text
            prompt_tokens = self._count_tokens_contents(contents, system_prompt or "")
            completion_tokens = self._estimate_tokens(answer)

            return {
                'success': True,
                'answer': answer,
                'model': self.chat_model_name,
                'tokens': {
                    'prompt': prompt_tokens,
                    'completion': completion_tokens,
                    'total': prompt_tokens + completion_tokens
                },
                'finish_reason': response.candidates[0].finish_reason.name if response.candidates else 'UNKNOWN'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> Dict[str, float]:
        """
        Estimate cost for API usage (Vertex AI pricing as of 2024)

        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Dict with cost breakdown
        """
        # Vertex AI Gemini pricing (approximate, varies by region)
        # Gemini Pro: ~$0.00025/1K chars input, ~$0.0005/1K chars output
        # text-embedding-004: ~$0.00001/1K chars
        pricing = {
            'gemini-2.0-flash': {
                'prompt': 0.00025 / 1000,
                'completion': 0.0005 / 1000
            },
            'gemini-1.5-pro': {
                'prompt': 0.00125 / 1000,
                'completion': 0.005 / 1000
            },
            'gemini-1.5-flash': {
                'prompt': 0.000075 / 1000,
                'completion': 0.0003 / 1000
            },
            'text-embedding-004': {
                'usage': 0.00001 / 1000
            }
        }

        model_pricing = pricing.get(self.chat_model_name, pricing['gemini-2.0-flash'])

        prompt_cost = prompt_tokens * model_pricing.get('prompt', 0.00025 / 1000)
        completion_cost = completion_tokens * model_pricing.get('completion', 0.0005 / 1000)

        return {
            'prompt_cost': prompt_cost,
            'completion_cost': completion_cost,
            'total_cost': prompt_cost + completion_cost,
            'currency': 'USD'
        }


# Singleton instance
_gemini_service = None


def get_gemini_service():
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
