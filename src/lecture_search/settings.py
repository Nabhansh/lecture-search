from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW_DIR = DATA / "raw"
AUDIO_DIR = DATA / "audio"
TRANSCRIPT_DIR = DATA / "transcripts"
PROCESSED_DIR = DATA / "processed"
INDEX_DIR = DATA / "index"
EVALUATION_DIR = DATA / "evaluation"
RESULTS_DIR = EVALUATION_DIR / "results"

CHUNK_SECONDS = 30.0
CHUNK_STRIDE_SECONDS = 20.0
RRF_K = 60
DEFAULT_TOP_K = 10
# Retained from the project context: multilingual, 384-dimensional model.
# FastEmbed availability may vary by installed version. Change only after
# recording the model change and rebuilding dense indexes.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384
