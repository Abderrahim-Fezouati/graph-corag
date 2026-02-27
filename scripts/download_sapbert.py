from transformers import AutoTokenizer, AutoModel

MODEL_ID = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
SAVE_PATH = "models/sapbert"

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModel.from_pretrained(MODEL_ID)

tokenizer.save_pretrained(SAVE_PATH)
model.save_pretrained(SAVE_PATH)

print(f"SapBERT downloaded to {SAVE_PATH}")
