"""
Query Expansion Service
Expands queries with synonyms and related terms to improve recall
"""

from typing import List, Set, Optional
import nltk
from nltk.corpus import wordnet


# Download WordNet data on first import
try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet', quiet=True)

try:
    nltk.data.find('corpora/omw-1.4')
except LookupError:
    nltk.download('omw-1.4', quiet=True)


class QueryExpansionService:
    """Service for expanding queries with synonyms"""

    def __init__(self):
        """Initialize query expansion service"""
        # Common stopwords that shouldn't be expanded
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this',
            'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }

    def expand_with_synonyms(
        self,
        query: str,
        max_synonyms_per_word: int = 2,
        include_original: bool = True
    ) -> str:
        """
        Expand query with WordNet synonyms

        Args:
            query: Original query text
            max_synonyms_per_word: Maximum synonyms to add per word
            include_original: Whether to include original query terms

        Returns:
            Expanded query string
        """
        tokens = query.lower().split()
        expanded_terms = []

        for token in tokens:
            # Always add original token
            if include_original:
                expanded_terms.append(token)

            # Skip stopwords and very short words
            if token in self.stop_words or len(token) <= 2:
                continue

            # Get synonyms from WordNet
            synonyms = self._get_synonyms(token, max_count=max_synonyms_per_word)
            expanded_terms.extend(synonyms)

        return ' '.join(expanded_terms)

    def expand_with_hypernyms(
        self,
        query: str,
        max_hypernyms_per_word: int = 1,
        include_original: bool = True
    ) -> str:
        """
        Expand query with hypernyms (more general terms)

        Example: "car" → "vehicle", "automobile"

        Args:
            query: Original query text
            max_hypernyms_per_word: Maximum hypernyms to add per word
            include_original: Whether to include original query terms

        Returns:
            Expanded query string
        """
        tokens = query.lower().split()
        expanded_terms = []

        for token in tokens:
            # Always add original token
            if include_original:
                expanded_terms.append(token)

            # Skip stopwords
            if token in self.stop_words or len(token) <= 2:
                continue

            # Get hypernyms from WordNet
            hypernyms = self._get_hypernyms(token, max_count=max_hypernyms_per_word)
            expanded_terms.extend(hypernyms)

        return ' '.join(expanded_terms)

    def expand_multi_strategy(
        self,
        query: str,
        max_synonyms: int = 2,
        max_hypernyms: int = 1,
        include_original: bool = True
    ) -> str:
        """
        Expand query using multiple strategies (synonyms + hypernyms)

        Args:
            query: Original query text
            max_synonyms: Maximum synonyms per word
            max_hypernyms: Maximum hypernyms per word
            include_original: Whether to include original query terms

        Returns:
            Expanded query string
        """
        tokens = query.lower().split()
        expanded_terms = []

        for token in tokens:
            terms_for_token = set()

            # Add original token
            if include_original:
                terms_for_token.add(token)

            # Skip stopwords for expansion
            if token not in self.stop_words and len(token) > 2:
                # Add synonyms
                synonyms = self._get_synonyms(token, max_count=max_synonyms)
                terms_for_token.update(synonyms)

                # Add hypernyms
                hypernyms = self._get_hypernyms(token, max_count=max_hypernyms)
                terms_for_token.update(hypernyms)

            expanded_terms.extend(list(terms_for_token))

        return ' '.join(expanded_terms)

    def _get_synonyms(self, word: str, max_count: int = 2) -> List[str]:
        """
        Get synonyms for a word from WordNet

        Args:
            word: Word to find synonyms for
            max_count: Maximum number of synonyms to return

        Returns:
            List of synonym strings
        """
        synonyms = set()

        try:
            synsets = wordnet.synsets(word)

            for syn in synsets[:max_count * 2]:  # Look at more synsets to find max_count unique
                for lemma in syn.lemmas()[:2]:  # Get top 2 lemmas per synset
                    synonym = lemma.name().lower().replace('_', ' ')

                    # Only add if different from original and not a phrase
                    if synonym != word and ' ' not in synonym:
                        synonyms.add(synonym)

                    if len(synonyms) >= max_count:
                        break

                if len(synonyms) >= max_count:
                    break

        except Exception:
            # Fail gracefully if WordNet lookup fails
            pass

        return list(synonyms)[:max_count]

    def _get_hypernyms(self, word: str, max_count: int = 1) -> List[str]:
        """
        Get hypernyms (more general terms) for a word from WordNet

        Args:
            word: Word to find hypernyms for
            max_count: Maximum number of hypernyms to return

        Returns:
            List of hypernym strings
        """
        hypernyms = set()

        try:
            synsets = wordnet.synsets(word)

            for syn in synsets[:2]:  # Look at first 2 synsets
                for hypernym in syn.hypernyms()[:max_count]:
                    for lemma in hypernym.lemmas()[:1]:  # Just take first lemma
                        hypernym_word = lemma.name().lower().replace('_', ' ')

                        # Only add if different from original and not a phrase
                        if hypernym_word != word and ' ' not in hypernym_word:
                            hypernyms.add(hypernym_word)

                        if len(hypernyms) >= max_count:
                            break

                if len(hypernyms) >= max_count:
                    break

        except Exception:
            # Fail gracefully if WordNet lookup fails
            pass

        return list(hypernyms)[:max_count]

    def get_expansion_terms(self, query: str, max_terms: int = 5) -> List[str]:
        """
        Get list of expansion terms (without original query)

        Useful for showing users what expansions were applied

        Args:
            query: Original query text
            max_terms: Maximum expansion terms to return

        Returns:
            List of expansion terms
        """
        expanded = self.expand_multi_strategy(query, include_original=False)
        terms = expanded.split()

        # Deduplicate while preserving order
        seen = set()
        unique_terms = []
        for term in terms:
            if term not in seen:
                seen.add(term)
                unique_terms.append(term)

        return unique_terms[:max_terms]


# Singleton instance
_query_expansion_service = None


def get_query_expansion_service() -> QueryExpansionService:
    """Get or create QueryExpansionService singleton"""
    global _query_expansion_service
    if _query_expansion_service is None:
        _query_expansion_service = QueryExpansionService()
    return _query_expansion_service
