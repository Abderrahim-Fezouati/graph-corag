from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import re
import unicodedata

import yaml


class NameNormalizer:
    """
    Lightweight name normalizer used by the type-aware SapBERT linker.

    Design goals:
    - If cfg_path is "default" or empty: use built-in normalization only
      (no file access, no config required).
    - If cfg_path is a real path to a YAML file: load it and optionally
      use it to define extra rewrite / synonym rules.
    """

    def __init__(self, cfg_path: Optional[str] = None) -> None:
        self.cfg_path = cfg_path or "default"
        self.cfg = {}

        # "default" means: do not try to read any file, just use built-ins
        if self.cfg_path not in ("", "default"):
            path = Path(self.cfg_path)
            if not path.is_file():
                raise FileNotFoundError(f"NameNormalizer config not found: {path!s}")
            # YAML is optional; if file is empty/null, fall back to {}
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.cfg = loaded or {}

        # Precompile common regexes for speed / cleanliness
        self._whitespace_re = re.compile(r"\s+")
        self._punct_cleanup_re = re.compile(r"[^\w\s\-\+\./]")

    # ------------------------------------------------------------------
    # Core normalization logic
    # ------------------------------------------------------------------
    def normalize(self, text: str) -> str:
        """Return a single normalized string for a mention."""
        if text is None:
            return ""

        x = str(text)

        # Unicode normalize
        x = unicodedata.normalize("NFKC", x)

        # Trim
        x = x.strip()

        # Canonicalize quotes / dashes
        x = (
            x.replace("–", "-")
            .replace("—", "-")
            .replace("‐", "-")
            .replace("’", "'")
            .replace("‘", "'")
            .replace("´", "'")
        )

        # Collapse whitespace
        x = self._whitespace_re.sub(" ", x)

        # Optional punctuation cleanup (keep word chars, space, -, +, ., /)
        x = self._punct_cleanup_re.sub("", x)

        # Lowercase for SapBERT compatibility
        x = x.lower()

        return x

    def normalize_list(self, text: str) -> List[str]:
        """
        Return a list of candidate normalized surface forms.

        For now:
        - Always return a single normalized string.
        - In the future, we can expand synonyms based on self.cfg.
        """
        norm = self.normalize(text)
        if not norm:
            return []
        return [norm]
