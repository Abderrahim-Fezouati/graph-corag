class NeuralReranker:
    """
    Minimal no-op reranker that just returns hits unchanged.
    Each hit is expected to be a tuple: (score, doc_id)
    Replace with your real reranker later.
    """

    def __init__(self, **kwargs):
        pass

    def rerank(self, hits):
        # ensure it's a list of (score, doc_id)
        return list(hits or [])
