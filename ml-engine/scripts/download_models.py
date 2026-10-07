"""Download all Hugging Face models used by the pipeline.

Run once from ml-engine/ before starting offline:
    python scripts/download_models.py

Re-run with HF_HUB_OFFLINE=1 to verify the cached models load correctly.
"""
import src.ml  # sets HF_HOME before anything else
from src.ml.config import Settings
from huggingface_hub import snapshot_download

# Skip unused formats to keep the download small.
_IGNORE = [
    "onnx/*",
    "openvino/*",
    "*.onnx",
    "*.h5",
    "*.ot",
    "*.msgpack",
    "tf_model*",
    "flax_model*",
    "rust_model*",
]

s = Settings.from_env()
for repo in (s.sentiment_model, s.zero_shot_model, s.embedding_model):
    print("Downloading", repo)
    snapshot_download(repo_id=repo, ignore_patterns=_IGNORE)
    print("  done")