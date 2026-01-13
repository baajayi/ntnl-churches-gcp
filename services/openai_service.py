"""
OpenAI Service
Handles embeddings generation and LLM completions for RAG
"""

import os
from typing import List, Dict, Any, Optional
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, Timeout
import tiktoken
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class OpenAIService:
    """Service for interacting with OpenAI API"""

    def __init__(self):
        """Initialize OpenAI client"""
        self.api_key = os.getenv('OPENAI_API_KEY')

        if not self.api_key:
            print("WARNING: OPENAI_API_KEY environment variable not set")
            self.client = None
            return

        # Create HTTP client with explicit timeouts to prevent hanging
        http_client = httpx.Client(
            timeout=httpx.Timeout(
                connect=10.0,   # 10 seconds to establish connection
                read=60.0,      # 60 seconds to read response
                write=10.0,     # 10 seconds to send request
                pool=5.0        # 5 seconds to acquire connection from pool
            )
        )

        self.client = OpenAI(
            api_key=self.api_key,
            http_client=http_client  # Add timeout to prevent infinite hangs
        )

        # Model configurations
        self.embedding_model = os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-ada-002')
        self.chat_model = os.getenv('OPENAI_CHAT_MODEL', 'gpt-4-turbo-preview')
        self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '1000'))

        # Initialize tokenizer for counting
        try:
            self.encoding = tiktoken.encoding_for_model(self.chat_model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def _check_client(self):
        """Check if client is initialized"""
        if self.client is None:
            return {
                'success': False,
                'error': 'OpenAI client not initialized. OPENAI_API_KEY environment variable is required.'
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

            # Create embedding
            response = self.client.embeddings.create(
                input=text,
                model=self.embedding_model
            )

            embedding = response.data[0].embedding

            return {
                'success': True,
                'embedding': embedding,
                'dimension': len(embedding),
                'model': self.embedding_model,
                'tokens_used': response.usage.total_tokens
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
            retry=retry_if_exception_type((APIConnectionError, Timeout, RateLimitError)),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(3),
            reraise=True  # We'll catch this below
        )
        def _create_embeddings_with_retry():
            return self.client.embeddings.create(
                input=texts,
                model=self.embedding_model
            )

        try:
            # Call with retry logic
            response = _create_embeddings_with_retry()

            embeddings = [item.embedding for item in response.data]

            return {
                'success': True,
                'embeddings': embeddings,
                'count': len(embeddings),
                'dimension': len(embeddings[0]) if embeddings else 0,
                'model': self.embedding_model,
                'tokens_used': response.usage.total_tokens
            }

        except (APIConnectionError, Timeout, RateLimitError) as e:
            # Retry exhausted - return error dict instead of crashing
            return {
                'success': False,
                'error': f'OpenAI API error after 3 retries: {str(e)}',
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

            # Build messages with conversation history
            messages = [
                {"role": "system", "content": system_prompt}
            ]

            # Add conversation history if provided
            if conversation_history:
                for exchange in conversation_history[-5:]:  # Keep last 5 exchanges to manage context window
                    messages.append({"role": "user", "content": exchange.get('query', '')})
                    messages.append({"role": "assistant", "content": exchange.get('answer', '')})

            # Add current query with context
            messages.append({
                "role": "user",
                "content": f"Context:\n{context_text}\n\nQuestion: {query}"
            })

            # Count tokens
            prompt_tokens = self._count_tokens(messages)

            # Generate response
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens or self.max_tokens
            )

            answer = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason

            return {
                'success': True,
                'answer': answer,
                'model': self.chat_model,
                'tokens': {
                    'prompt': prompt_tokens,
                    'completion': response.usage.completion_tokens,
                    'total': response.usage.total_tokens
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

    def _count_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Count tokens in messages"""
        try:
            num_tokens = 0
            for message in messages:
                num_tokens += 4  # Every message follows <im_start>{role/name}\n{content}<im_end>\n
                for key, value in message.items():
                    num_tokens += len(self.encoding.encode(value))
            num_tokens += 2  # Every reply is primed with <im_start>assistant
            return num_tokens
        except Exception:
            # Fallback to rough estimate
            text = " ".join([msg.get('content', '') for msg in messages])
            return len(text) // 4

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
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens or self.max_tokens
            )

            answer = response.choices[0].message.content

            return {
                'success': True,
                'answer': answer,
                'model': self.chat_model,
                'tokens': {
                    'prompt': response.usage.prompt_tokens,
                    'completion': response.usage.completion_tokens,
                    'total': response.usage.total_tokens
                },
                'finish_reason': response.choices[0].finish_reason
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> Dict[str, float]:
        """
        Estimate cost for API usage (rates as of 2024)

        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Dict with cost breakdown
        """
        # Pricing (update these based on current OpenAI pricing)
        pricing = {
            'gpt-4-turbo-preview': {
                'prompt': 0.01 / 1000,  # $0.01 per 1K tokens
                'completion': 0.03 / 1000  # $0.03 per 1K tokens
            },
            'gpt-3.5-turbo': {
                'prompt': 0.0005 / 1000,
                'completion': 0.0015 / 1000
            },
            'text-embedding-ada-002': {
                'usage': 0.0001 / 1000
            }
        }

        model_pricing = pricing.get(self.chat_model, pricing['gpt-4-turbo-preview'])

        prompt_cost = prompt_tokens * model_pricing['prompt']
        completion_cost = completion_tokens * model_pricing['completion']

        return {
            'prompt_cost': prompt_cost,
            'completion_cost': completion_cost,
            'total_cost': prompt_cost + completion_cost,
            'currency': 'USD'
        }


# Singleton instance
_openai_service = None

def get_openai_service():
    global _openai_service
    if _openai_service is None:
        _openai_service = OpenAIService()
    return _openai_service
