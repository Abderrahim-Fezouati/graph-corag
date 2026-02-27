import sys

sys.path.insert(0, r"F:\graph-corag-clean")  # fallback if PYTHONPATH is not set

from src.analyzer.sapbert_linker import SapBERTLinker

lk = SapBERTLinker(
    model_dir_or_name="cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
    index_dir=r"F:\graph-corag-clean\artifacts\sapbert",
)

for m in [
    "warfarin",
    "ibuprofen",
    "clopidogrel",
    "lactic acidosis",
    "hidradenitis suppurativa",
]:
    print(m, "->", lk.link(m, topk=5))
