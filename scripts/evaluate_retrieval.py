"""
Evaluation Framework for Retrieval Quality
Measures precision, recall, MRR, NDCG for vector, BM25, and hybrid search
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.pinecone_service import get_pinecone_service
from services.gemini_service import get_gemini_service


class RetrievalEvaluator:
    """Evaluate retrieval systems with standard metrics"""

    def __init__(self, namespace: str):
        """
        Initialize evaluator

        Args:
            namespace: Pinecone namespace to evaluate
        """
        self.namespace = namespace
        self.pinecone_service = get_pinecone_service()
        self.gemini_service = get_gemini_service()

    def precision_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """
        Calculate Precision@K

        Precision = (# relevant items in top-k) / k

        Args:
            retrieved: List of retrieved document IDs (ordered by rank)
            relevant: List of ground truth relevant document IDs
            k: Number of top results to consider

        Returns:
            Precision@K score (0-1)
        """
        if k == 0:
            return 0.0

        retrieved_k = retrieved[:k]
        relevant_retrieved = len(set(retrieved_k) & set(relevant))
        return relevant_retrieved / k

    def recall_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """
        Calculate Recall@K

        Recall = (# relevant items in top-k) / (total # relevant items)

        Args:
            retrieved: List of retrieved document IDs (ordered by rank)
            relevant: List of ground truth relevant document IDs
            k: Number of top results to consider

        Returns:
            Recall@K score (0-1)
        """
        if len(relevant) == 0:
            return 0.0

        retrieved_k = retrieved[:k]
        relevant_retrieved = len(set(retrieved_k) & set(relevant))
        return relevant_retrieved / len(relevant)

    def average_precision(self, retrieved: List[str], relevant: List[str]) -> float:
        """
        Calculate Average Precision (AP)

        AP = (sum of P@k for each relevant item) / (total # relevant items)

        Args:
            retrieved: List of retrieved document IDs (ordered by rank)
            relevant: List of ground truth relevant document IDs

        Returns:
            Average Precision score (0-1)
        """
        if len(relevant) == 0:
            return 0.0

        num_relevant = 0
        precision_sum = 0.0

        for k, doc_id in enumerate(retrieved, 1):
            if doc_id in relevant:
                num_relevant += 1
                precision_sum += num_relevant / k

        return precision_sum / len(relevant)

    def mean_reciprocal_rank(self, retrieved: List[str], relevant: List[str]) -> float:
        """
        Calculate Reciprocal Rank (RR)

        RR = 1 / (rank of first relevant item)

        Args:
            retrieved: List of retrieved document IDs (ordered by rank)
            relevant: List of ground truth relevant document IDs

        Returns:
            Reciprocal Rank score (0-1)
        """
        for rank, doc_id in enumerate(retrieved, 1):
            if doc_id in relevant:
                return 1.0 / rank
        return 0.0

    def dcg_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """
        Calculate Discounted Cumulative Gain @ K

        DCG = sum(rel_i / log2(i+1)) for i=1 to k

        Args:
            retrieved: List of retrieved document IDs (ordered by rank)
            relevant: List of ground truth relevant document IDs
            k: Number of top results to consider

        Returns:
            DCG@K score
        """
        import math

        dcg = 0.0
        for i, doc_id in enumerate(retrieved[:k], 1):
            # Binary relevance: 1 if relevant, 0 otherwise
            rel = 1 if doc_id in relevant else 0
            dcg += rel / math.log2(i + 1)

        return dcg

    def ndcg_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """
        Calculate Normalized Discounted Cumulative Gain @ K

        NDCG = DCG / IDCG (ideal DCG)

        Args:
            retrieved: List of retrieved document IDs (ordered by rank)
            relevant: List of ground truth relevant document IDs
            k: Number of top results to consider

        Returns:
            NDCG@K score (0-1)
        """
        import math

        # Calculate DCG
        dcg = self.dcg_at_k(retrieved, relevant, k)

        # Calculate ideal DCG (all relevant docs at top)
        ideal_retrieved = list(relevant) + [f"dummy_{i}" for i in range(k - len(relevant))]
        idcg = self.dcg_at_k(ideal_retrieved[:k], relevant, k)

        if idcg == 0:
            return 0.0

        return dcg / idcg

    def evaluate_query(
        self,
        query: str,
        relevant_ids: List[str],
        top_k: int = 10,
        search_method: str = 'vector'
    ) -> Dict[str, float]:
        """
        Evaluate a single query

        Args:
            query: Query text
            relevant_ids: Ground truth relevant document IDs
            top_k: Number of results to retrieve
            search_method: 'vector', 'hybrid', or 'bm25'

        Returns:
            Dict of metric scores
        """
        # Perform search based on method
        if search_method == 'vector':
            # Create query embedding
            embed_result = self.gemini_service.create_embedding(query)
            if not embed_result['success']:
                print(f"Error creating embedding: {embed_result.get('error')}")
                return {}

            # Vector search
            search_result = self.pinecone_service.query(
                namespace=self.namespace,
                query_vector=embed_result['embedding'],
                top_k=top_k
            )

        elif search_method == 'hybrid':
            # Hybrid search (requires query text embedding internally)
            search_result = self.pinecone_service.hybrid_query(
                namespace=self.namespace,
                query_text=query,
                top_k=top_k,
                alpha=0.7  # Default 70% semantic, 30% keyword
            )

        elif search_method == 'bm25':
            # BM25 only
            from services.bm25_service import get_bm25_service
            bm25_service = get_bm25_service()
            search_result = bm25_service.search(self.namespace, query, top_k=top_k)

        else:
            raise ValueError(f"Unknown search method: {search_method}")

        # Extract retrieved IDs
        if not search_result.get('success'):
            print(f"Search failed: {search_result.get('error')}")
            return {}

        retrieved_ids = [match['id'] for match in search_result.get('matches', [])]

        # Calculate metrics
        metrics = {
            'precision@1': self.precision_at_k(retrieved_ids, relevant_ids, 1),
            'precision@5': self.precision_at_k(retrieved_ids, relevant_ids, 5),
            'precision@10': self.precision_at_k(retrieved_ids, relevant_ids, 10),
            'recall@5': self.recall_at_k(retrieved_ids, relevant_ids, 5),
            'recall@10': self.recall_at_k(retrieved_ids, relevant_ids, 10),
            'mrr': self.mean_reciprocal_rank(retrieved_ids, relevant_ids),
            'map': self.average_precision(retrieved_ids, relevant_ids),
            'ndcg@5': self.ndcg_at_k(retrieved_ids, relevant_ids, 5),
            'ndcg@10': self.ndcg_at_k(retrieved_ids, relevant_ids, 10),
            'num_retrieved': len(retrieved_ids),
            'num_relevant': len(relevant_ids)
        }

        return metrics

    def evaluate_dataset(
        self,
        queries: List[Dict[str, Any]],
        search_method: str = 'vector',
        top_k: int = 10
    ) -> Dict[str, Any]:
        """
        Evaluate multiple queries

        Args:
            queries: List of query dicts with 'query' and 'relevant_ids' keys
            search_method: 'vector', 'hybrid', or 'bm25'
            top_k: Number of results to retrieve

        Returns:
            Dict with aggregated metrics and per-query results
        """
        all_metrics = defaultdict(list)
        per_query_results = []

        for i, query_data in enumerate(queries, 1):
            query = query_data['query']
            relevant_ids = query_data['relevant_ids']

            print(f"Evaluating query {i}/{len(queries)}: {query[:60]}...")

            metrics = self.evaluate_query(query, relevant_ids, top_k, search_method)

            # Store per-query results
            per_query_results.append({
                'query': query,
                'relevant_ids': relevant_ids,
                'metrics': metrics
            })

            # Aggregate metrics
            for metric_name, value in metrics.items():
                if isinstance(value, (int, float)):
                    all_metrics[metric_name].append(value)

        # Calculate averages
        avg_metrics = {}
        for metric_name, values in all_metrics.items():
            avg_metrics[f"avg_{metric_name}"] = sum(values) / len(values) if values else 0.0

        return {
            'search_method': search_method,
            'num_queries': len(queries),
            'top_k': top_k,
            'average_metrics': avg_metrics,
            'per_query_results': per_query_results
        }


def load_benchmark_queries(filepath: str) -> List[Dict[str, Any]]:
    """
    Load benchmark queries from JSON file

    Expected format:
    [
        {
            "query": "What are ELCA values?",
            "relevant_ids": ["doc1_chunk0", "doc1_chunk1", "doc2_chunk3"]
        },
        ...
    ]

    Args:
        filepath: Path to JSON file

    Returns:
        List of query dictionaries
    """
    with open(filepath, 'r') as f:
        return json.load(f)


def save_results(results: Dict[str, Any], output_path: str):
    """Save evaluation results to JSON file"""
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {output_path}")


def print_results(results: Dict[str, Any]):
    """Print formatted evaluation results"""
    print("\n" + "=" * 70)
    print(f"EVALUATION RESULTS - {results['search_method'].upper()}")
    print("=" * 70)
    print(f"Queries evaluated: {results['num_queries']}")
    print(f"Top K: {results['top_k']}")
    print("\nAverage Metrics:")
    print("-" * 70)

    metrics = results['average_metrics']

    # Precision metrics
    print(f"  Precision@1:  {metrics.get('avg_precision@1', 0):.4f}")
    print(f"  Precision@5:  {metrics.get('avg_precision@5', 0):.4f}")
    print(f"  Precision@10: {metrics.get('avg_precision@10', 0):.4f}")

    # Recall metrics
    print(f"\n  Recall@5:     {metrics.get('avg_recall@5', 0):.4f}")
    print(f"  Recall@10:    {metrics.get('avg_recall@10', 0):.4f}")

    # Ranking metrics
    print(f"\n  MRR:          {metrics.get('avg_mrr', 0):.4f}")
    print(f"  MAP:          {metrics.get('avg_map', 0):.4f}")

    # NDCG metrics
    print(f"\n  NDCG@5:       {metrics.get('avg_ndcg@5', 0):.4f}")
    print(f"  NDCG@10:      {metrics.get('avg_ndcg@10', 0):.4f}")

    print("=" * 70)


def compare_methods(
    namespace: str,
    queries: List[Dict[str, Any]],
    methods: List[str] = ['vector', 'bm25', 'hybrid'],
    top_k: int = 10
):
    """
    Compare multiple search methods side-by-side

    Args:
        namespace: Pinecone namespace
        queries: Benchmark queries
        methods: List of search methods to compare
        top_k: Number of results to retrieve
    """
    evaluator = RetrievalEvaluator(namespace)
    all_results = {}

    for method in methods:
        print(f"\n{'=' * 70}")
        print(f"Evaluating: {method.upper()}")
        print(f"{'=' * 70}")

        results = evaluator.evaluate_dataset(queries, search_method=method, top_k=top_k)
        all_results[method] = results

        print_results(results)

    # Print comparison table
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Metric':<20} " + " ".join([f"{m.upper():>12}" for m in methods]))
    print("-" * 70)

    # Compare key metrics
    key_metrics = [
        'avg_precision@5',
        'avg_recall@10',
        'avg_mrr',
        'avg_map',
        'avg_ndcg@10'
    ]

    for metric in key_metrics:
        metric_name = metric.replace('avg_', '').replace('@', '@')
        values = [all_results[m]['average_metrics'].get(metric, 0) for m in methods]
        print(f"{metric_name:<20} " + " ".join([f"{v:>12.4f}" for v in values]))

    print("=" * 70)

    # Identify best method per metric
    print("\nBest Performing Method per Metric:")
    print("-" * 70)
    for metric in key_metrics:
        values = {m: all_results[m]['average_metrics'].get(metric, 0) for m in methods}
        best_method = max(values, key=values.get)
        best_value = values[best_method]
        metric_name = metric.replace('avg_', '')
        print(f"  {metric_name:<18}: {best_method.upper():>10} ({best_value:.4f})")

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate retrieval quality with precision, recall, MRR, and NDCG'
    )
    parser.add_argument('benchmark_file', help='Path to benchmark queries JSON file')
    parser.add_argument('--namespace', required=True, help='Pinecone namespace to evaluate')
    parser.add_argument('--method', choices=['vector', 'bm25', 'hybrid', 'compare'],
                        default='compare', help='Search method to evaluate')
    parser.add_argument('--top-k', type=int, default=10, help='Number of results to retrieve')
    parser.add_argument('--output', help='Path to save results JSON (optional)')

    args = parser.parse_args()

    # Load benchmark queries
    print(f"Loading benchmark queries from {args.benchmark_file}...")
    queries = load_benchmark_queries(args.benchmark_file)
    print(f"Loaded {len(queries)} queries")

    if args.method == 'compare':
        # Compare all methods
        results = compare_methods(args.namespace, queries, top_k=args.top_k)

        if args.output:
            save_results(results, args.output)

    else:
        # Evaluate single method
        evaluator = RetrievalEvaluator(args.namespace)
        results = evaluator.evaluate_dataset(queries, search_method=args.method, top_k=args.top_k)

        print_results(results)

        if args.output:
            save_results(results, args.output)


if __name__ == '__main__':
    main()
