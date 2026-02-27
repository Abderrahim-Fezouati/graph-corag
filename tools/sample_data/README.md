This folder contains minimal sample data to run the pipeline in a trimmed/local mode.

Files:
- sample_queries.raw.jsonl        : raw user queries (one JSON object per line)
- sample_queries.analyzed.jsonl   : analyzer output used by later stages
- sample_corpus.jsonl             : small corpus of documents used for retrieval
- sample_kg.csv                   : small KG with head,relation,tail
- sample_umls_dict.txt            : small UMLS-like dict snippet
- sample_umls_overlay.json        : example overlay mapping
- sample_relation_schema.json     : relation schema fragment used by the analyzer

How to use:
- Activate your environment and run the scripts, pointing them to these small files instead of the full datasets.
- The pipeline supports overriding input paths via CLI args; see tools/run_pipeline.ps1 for examples.
