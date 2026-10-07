import src.ml  # sets HF_HOME before anything else
from src.ml.config import Settings
from huggingface_hub import snapshot_download

s = Settings.from_env()
for repo in (s.sentiment_model, s.zero_shot_model, s.embedding_model):
    print("Downloading", repo)
    snapshot_download(repo_id=repo)