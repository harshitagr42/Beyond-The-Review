"""Local-first NLP engine for the Feedback & Review Analyzer.

Importing this package is cheap: heavy libraries (torch, transformers, bertopic)
are only imported when the corresponding component is constructed.
"""
import os

# Must be set before torch is imported anywhere. Lets PyTorch silently run any
# op that isn't implemented on MPS yet on the CPU instead of raising.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


from pathlib import Path

_MODEL_DIR = Path(__file__).resolve().parents[2] / "model"
_MODEL_DIR.mkdir(exist_ok=True)
os.environ.setdefault("HF_HOME", str(_MODEL_DIR))                       # transformers + huggingface_hub
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(_MODEL_DIR))    # older sentence-transformers versions