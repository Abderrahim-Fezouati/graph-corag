from src.analyzer.sapbert_linker_v2 import SapBERTLinkerV2
from src.analyzer.entity_linking_adapter import ELAdapter


def test_sapbert():
    linker = SapBERTLinkerV2(index_root="indices/sapbert")

    print(linker.link("blinatumomab", ["drug"]))
    print(linker.link("acute myocardial infarction", ["disease"]))
    print(linker.link("random nonsense", ["drug"]))


def test_adapter():
    linker = SapBERTLinkerV2(index_root="indices/sapbert")
    adapter = ELAdapter(linker)

    out = adapter.link_mentions(
        question="Does blinatumomab interact with CD19?",
        mentions=["blinatumomab"],
        relation="INTERACTS_WITH",
        slot="head",
    )
    print(out)


if __name__ == "__main__":
    print("Running Graph-CoRAG component tests...")
    test_sapbert()
    test_adapter()
    print("All tests PASSED.")
