import csv
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional, Set

Triple = Tuple[str, str, str]        # (src, rel, tgt)
Edge = Tuple[str, str]               # (rel, tgt)


class KGMultiHop:
    """
    Lightweight multihop KG traversal over a CSV edge list.

    CSV format (header optional):
        src,rel,tgt
        C123,INTERACTS_WITH,C456
        ...

    Features:
    - Robust CSV loading (with or without header)
    - One-hop neighbor lookup
    - BFS path enumeration (1..max_hops) with:
        * optional relation filtering
        * global limit_paths enforcement
        * simple cycle avoidance (no node repeated within a path)
    """

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.adj: Dict[str, List[Edge]] = defaultdict(list)
        self._load_edges(csv_path)

    # -----------------------
    # Loading
    # -----------------------
    def _load_edges(self, csv_path: str) -> None:
        """
        Load edges from a CSV file. Accepts both:
        - with header row: "src,rel,tgt"
        - without header: 3 columns per row
        Ignores blank lines and lines starting with '#'.
        """
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                row = [cell.strip() for cell in row]
                if not row[0] or row[0].startswith("#"):
                    continue
                # Skip header if present
                if len(row) >= 3 and row[0].lower() == "src" and row[1].lower() == "rel" and row[2].lower() == "tgt":
                    continue
                if len(row) < 3:
                    # malformed line; skip
                    continue
                src, rel, tgt = row[0], row[1], row[2]
                self.adj[src].append((rel, tgt))

    # -----------------------
    # Public API
    # -----------------------
    def one_hop(self, src: str) -> List[Edge]:
        """
        Return list of (rel, tgt) for a given src node.
        """
        return list(self.adj.get(src, []))

    def bfs_paths(
        self,
        start: str,
        max_hops: int = 3,
        allowed_relations: Optional[Set[str]] = None,
        limit_paths: Optional[int] = None,
    ) -> List[List[Triple]]:
        """
        Enumerate paths of length 1..max_hops starting from `start`.
        Each path is represented as a list of triples: [(src, rel, tgt), ...]

        Parameters
        ----------
        start : str
            Starting CUI/node id.
        max_hops : int
            Maximum number of edges per path (1..max_hops).
        allowed_relations : Optional[Set[str]]
            If provided, only edges whose relation ∈ allowed_relations are explored.
        limit_paths : Optional[int]
            Global cap on the number of returned paths. If set, traversal stops
            immediately once the cap is reached.

        Returns
        -------
        List[List[Triple]]
            A list of paths; each path is list of (src, rel, tgt) triples.
        """
        if max_hops <= 0:
            return []

        results: List[List[Triple]] = []

        # Queue holds tuples of (current_node, current_path, visited_nodes_in_path)
        # current_path is a list of triples
        queue: deque = deque()
        queue.append((start, [], {start}))

        while queue:
            node, path, visited = queue.popleft()

            # Stop early if we already reached global cap
            if limit_paths is not None and len(results) >= limit_paths:
                return results

            for rel, nxt in self.adj.get(node, []):
                if allowed_relations and rel not in allowed_relations:
                    continue
                if nxt in visited:
                    # simple cycle avoidance
                    continue

                new_triple: Triple = (node, rel, nxt)
                new_path = path + [new_triple]

                # Record this path (every hop depth is a valid path)
                results.append(new_path)
                if limit_paths is not None and len(results) >= limit_paths:
                    return results

                # If we can go deeper, continue BFS
                if len(new_path) < max_hops:
                    queue.append((nxt, new_path, visited | {nxt}))

        return results
