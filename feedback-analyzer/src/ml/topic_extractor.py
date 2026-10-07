"""Two-tier issue & feature taxonomy extractor.

Tier 1 (general class)  - zero-shot NLI classifier (cross-encoder/nli-deberta-v3-small by default),
                          with a keyword-scoring fallback when no model is available.
Tier 2 (granular issue) - inside each Tier-1 class, cluster review embeddings (BERTopic when there
                          is enough data, otherwise k-means) and name each cluster with c-TF-IDF
                          key phrases. An optional LLM can rewrite the names.

Reviews are grouped by cluster, so ``len(cluster.indices)`` is the review volume of that sub-issue.
"""
from __future__ import annotations

import importlib.util
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

from .config import CATEGORY_DESCRIPTIONS, Settings
from .embedder import Embedder
from .llm_assist import LLMAssist

log = logging.getLogger("feedback_analyzer")

OTHER = "Other"
HYPOTHESIS = "This customer review is about {}."

DOMAIN_STOP = {
    "app", "apps", "application", "please", "pls", "just", "really", "very", "get", "got", "use", "using",
    "used", "would", "could", "also", "one", "even", "thing", "things", "doesn", "didn", "isn", "wasn",
    "don", "won", "couldn", "wouldn", "shouldn", "cant", "dont", "doesnt", "didnt", "ive", "im", "hasn",
    "haven", "aren", "like", "make", "makes", "need", "want", "time", "times", "ever", "lot", "much",
}
STOPWORDS = sorted(set(ENGLISH_STOP_WORDS) | DOMAIN_STOP)

# Keyword fallback for Tier 1 (only used when the zero-shot model can't be loaded).
KEYWORDS: Dict[str, List[str]] = {
    "Streaming/Playback": [
        r"\bstream", r"\bplayback", r"\bplay(?:ing|s)?\b", r"\bpaus", r"\bvideo", r"\bbuffer",
        r"\bresolution", r"\b(?:1080p|720p|4k|360p)\b", r"\bsubtitle", r"\bcaption", r"\blive\b",
        r"\bepisode", r"\bwatch", r"\bseek", r"\brewind", r"\baudio", r"\bcast(?:ing)?\b",
    ],
    "Comments & Social": [
        r"\bcomment", r"\brepl(?:y|ies)", r"\bshar(?:e|ing)\b", r"\bfollow", r"\bfriend", r"\bchat\b",
        r"\bmessag", r"\bprofile", r"\bcommunity", r"\breact(?:ion)?", r"\bmention", r"\bspam",
        r"\bcreator", r"\bpost(?:s|ing|ed)?\b",
    ],
    "Billing & Subscriptions": [
        r"\bbill", r"\bcharg", r"\bsubscri", r"\brefund", r"\bpay(?:s|ment|ing|ed)?\b", r"\bpric",
        r"\bexpensive", r"\bcancel", r"\bcredit card", r"\binvoice", r"\brenew", r"\btrial",
        r"\bpremium", r"\bplan\b", r"\bdiscount", r"\bcost",
    ],
    "Performance & Crashes": [
        r"\bcrash", r"\bfreez", r"\bfroze", r"\blag", r"\bslow", r"\bbug", r"\bbattery", r"\bdrain",
        r"\bloads?\b", r"\bloading", r"\bhang", r"\bforce.?clos", r"\bunresponsive", r"\bmemory",
        r"\bhot\b", r"\boverheat", r"\bstartup", r"\bstable", r"\bperformance", r"\bsnappier",
    ],
    "UI/UX & Navigation": [
        r"\bui\b", r"\bux\b", r"\binterface", r"\bmenu", r"\bnavigat", r"\bbutton", r"\bsearch",
        r"\bdesign", r"\blayout", r"\bdark mode", r"\btheme", r"\bconfus", r"\bsettings",
        r"\bhome screen", r"\btabs?\b", r"\bfont", r"\bintuitive", r"\bredesign", r"\bfilters?\b",
    ],
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@dataclass
class ThemeCluster:
    general_class: str
    name: str
    indices: List[int]  # row indices into the input list
    representatives: List[int] = field(default_factory=list)  # row indices, most central first


class TopicExtractor:
    def __init__(
        self,
        settings: Settings,
        device: str,
        embedder: Embedder,
        llm: Optional[LLMAssist] = None,
        force_fallback: bool = False,
    ):
        self.s = settings
        self.device = device
        self.embedder = embedder
        self.llm = llm
        self.categories = list(settings.categories)
        self.notes: List[str] = []
        self.tier1_backend = "keyword"
        self.tier2_backends: set = set()
        self._zs = None
        self._keyword_re = self._build_keyword_patterns()
        self._bertopic_ok = all(importlib.util.find_spec(m) for m in ("bertopic", "umap", "hdbscan"))

        want = "keyword" if force_fallback else settings.tier1_backend
        if want in ("auto", "zeroshot"):
            try:
                self._load_zero_shot()
                self.tier1_backend = "zero-shot"
            except Exception as exc:
                if want == "zeroshot":
                    raise
                self.notes.append(
                    f"Zero-shot model unavailable ({type(exc).__name__}); using keyword classifier for Tier 1."
                )
                log.warning(self.notes[-1])
        self._force_fallback = force_fallback

    # ------------------------------------------------------------------ tier 1
    def _load_zero_shot(self) -> None:
        from transformers import pipeline

        self._zs = pipeline("zero-shot-classification", model=self.s.zero_shot_model, device=self.device)

    def _build_keyword_patterns(self) -> Dict[str, List["re.Pattern[str]"]]:
        out = {}
        for cat in self.categories:
            pats = KEYWORDS.get(cat) or [rf"\b{re.escape(w)}" for w in re.findall(r"[a-z]{4,}", cat.lower())]
            out[cat] = [re.compile(p, re.I) for p in pats]
        return out

    def _zero_shot_predict(self, texts: List[str]) -> List[Tuple[str, float]]:
        descs = [CATEGORY_DESCRIPTIONS.get(c, c) for c in self.categories]
        back = dict(zip(descs, self.categories))

        def run():
            return self._zs(
                texts,
                candidate_labels=descs,
                hypothesis_template=HYPOTHESIS,
                multi_label=False,
                batch_size=self.s.batch_size,
            )

        try:
            out = run()
        except RuntimeError as exc:
            if self.device == "cpu":
                raise
            self.notes.append(f"Zero-shot inference failed on {self.device} ({exc}); retrying on CPU.")
            log.warning(self.notes[-1])
            self.device = "cpu"
            self._load_zero_shot()
            out = run()
        if isinstance(out, dict):
            out = [out]
        return [(back[o["labels"][0]], float(o["scores"][0])) for o in out]

    def _keyword_predict(self, texts: List[str]) -> List[Tuple[str, float]]:
        preds = []
        for t in texts:
            hits = {c: sum(1 for p in pats if p.search(t)) for c, pats in self._keyword_re.items()}
            total = sum(hits.values())
            if total == 0:
                preds.append((OTHER, 0.0))
                continue
            best = max(self.categories, key=lambda c: hits[c])  # ties -> earliest category
            preds.append((best, hits[best] / total))
        return preds

    def classify_general(self, texts: Sequence[str], use_llm: bool = True) -> List[Tuple[str, float]]:
        """Tier 1. Returns (category, confidence) per input text."""
        texts = list(texts)
        if not texts:
            return []
        unique = list(dict.fromkeys(texts))
        if self.tier1_backend == "zero-shot":
            preds = self._zero_shot_predict(unique)
            resolved = []
            for text, (label, score) in zip(unique, preds):
                if score < self.s.zero_shot_min_score:
                    llm_label = (
                        self.llm.classify(text, self.categories) if (use_llm and self.llm and self.llm.enabled) else None
                    )
                    resolved.append((llm_label, score) if llm_label else (OTHER, score))
                else:
                    resolved.append((label, score))
            preds = resolved
        else:
            preds = self._keyword_predict(unique)
        lut = dict(zip(unique, preds))
        return [lut[t] for t in texts]

    # ------------------------------------------------------------------ tier 2
    def _bertopic_labels(self, docs: List[str], emb: np.ndarray, max_k: int) -> np.ndarray:
        from bertopic import BERTopic
        from hdbscan import HDBSCAN
        from sklearn.feature_extraction.text import CountVectorizer as CV
        from umap import UMAP

        model = BERTopic(
            umap_model=UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=self.s.seed),
            hdbscan_model=HDBSCAN(min_cluster_size=max(self.s.min_theme_size, 10), prediction_data=True),
            vectorizer_model=CV(stop_words=STOPWORDS, ngram_range=(1, 2)),
            nr_topics=max_k,
            calculate_probabilities=False,
            verbose=False,
        )
        topics, _ = model.fit_transform(docs, embeddings=emb)
        return np.asarray(topics)

    def _cluster(self, docs: List[str], emb: np.ndarray) -> np.ndarray:
        n = len(docs)
        max_k = min(self.s.max_subtopics_per_class, n // max(self.s.min_theme_size, 1), len(set(docs)))
        if max_k < 2:
            return np.zeros(n, dtype=int)

        if self.s.tier2_backend in ("auto", "bertopic") and self._bertopic_ok and not self._force_fallback:
            if n >= self.s.bertopic_min_docs or self.s.tier2_backend == "bertopic":
                try:
                    labels = self._bertopic_labels(docs, emb, max_k)
                    self.tier2_backends.add("bertopic")
                    return labels
                except Exception as exc:
                    self.notes.append(f"BERTopic failed ({type(exc).__name__}: {exc}); using k-means.")
                    log.warning(self.notes[-1])

        k = int(np.clip(round(np.sqrt(n / 4)), 2, max_k))
        self.tier2_backends.add("kmeans")
        return KMeans(n_clusters=k, n_init=5, random_state=self.s.seed).fit_predict(emb)

    def _merge_small(self, labels: np.ndarray, emb: np.ndarray) -> np.ndarray:
        """Reassign outliers (-1) and clusters smaller than MIN_THEME_SIZE to the nearest large cluster."""
        labels = np.asarray(labels).copy()
        ids, counts = np.unique(labels[labels >= 0], return_counts=True)
        keep = [int(i) for i, c in zip(ids, counts) if c >= self.s.min_theme_size]
        if not keep:
            return np.zeros(len(labels), dtype=int)
        small = ~np.isin(labels, keep)
        if small.any():
            cents = np.stack([emb[labels == i].mean(axis=0) for i in keep])
            cents /= np.maximum(np.linalg.norm(cents, axis=1, keepdims=True), 1e-9)
            labels[small] = np.asarray(keep)[(emb[small] @ cents.T).argmax(axis=1)]
        remap = {old: new for new, old in enumerate(sorted(set(labels.tolist())))}
        return np.asarray([remap[x] for x in labels.tolist()])

    @staticmethod
    def _build_name(terms: List[str]) -> str:
        chosen: List[str] = []
        for term in terms:
            words = term.split()
            if all(w in chosen for w in words):
                continue
            fresh = [w for w in words if w not in chosen]
            if len(chosen) + len(fresh) > 4:
                continue
            chosen.extend(fresh)
            if len(chosen) >= 3:
                break
        return " ".join(w.capitalize() for w in chosen)

    def _name_clusters(self, docs: List[str], labels: np.ndarray, general_class: str) -> Dict[int, str]:
        ids = sorted(set(labels.tolist()))
        fallback = {i: f"{general_class} Feedback" for i in ids}
        joined = [" ".join(d for d, l in zip(docs, labels) if l == i) for i in ids]
        cv = CountVectorizer(
            stop_words=STOPWORDS, ngram_range=(1, 2), token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9]+\b"
        )
        try:
            X = cv.fit_transform(joined).toarray().astype(float)
        except ValueError:
            return fallback
        # class-based TF-IDF (as in BERTopic): tf within cluster * log(1 + avg_words / term_freq)
        tf = X / np.maximum(X.sum(axis=1, keepdims=True), 1.0)
        idf = np.log(1 + (X.sum() / len(ids)) / np.maximum(X.sum(axis=0), 1.0))
        scores = tf * idf
        terms = cv.get_feature_names_out()
        names = {}
        for row, cid in enumerate(ids):
            top = [terms[j] for j in np.argsort(-scores[row])[:15] if X[row, j] > 0]
            names[cid] = self._build_name(top) or fallback[cid]
        return names

    def _representatives(self, emb: np.ndarray, members: np.ndarray, docs: List[str]) -> List[int]:
        centroid = emb[members].mean(axis=0)
        centroid = centroid / max(float(np.linalg.norm(centroid)), 1e-9)
        order = members[np.argsort(-(emb[members] @ centroid))]
        picked: List[int] = []
        seen = set()
        for pass_filter in (True, False):
            for m in order:
                key = _norm(docs[m])
                if key in seen:
                    continue
                if pass_filter and not 15 <= len(docs[m]) <= 280:
                    continue
                seen.add(key)
                picked.append(int(m))
                if len(picked) >= self.s.samples_per_theme:
                    return picked
        return picked

    def _tier2(self, general_class: str, idx: List[int], texts: List[str], emb: np.ndarray) -> List[ThemeCluster]:
        docs = [texts[i] for i in idx]
        sub_emb = emb[idx]
        labels = self._merge_small(self._cluster(docs, sub_emb), sub_emb)
        names = self._name_clusters(docs, labels, general_class)
        clusters = []
        for cid in sorted(set(labels.tolist())):
            members = np.where(labels == cid)[0]
            reps_local = self._representatives(sub_emb, members, docs)
            name = names[cid]
            if self.llm and self.llm.enabled:
                better = self.llm.name_cluster(general_class, [docs[r] for r in reps_local])
                name = better or name
            clusters.append(
                ThemeCluster(
                    general_class=general_class,
                    name=name,
                    indices=[idx[m] for m in members],
                    representatives=[idx[r] for r in reps_local],
                )
            )
        return clusters

    # --------------------------------------------------------------------- API
    def extract(self, texts: Sequence[str], embeddings: Optional[np.ndarray] = None) -> List[ThemeCluster]:
        texts = list(texts)
        if not texts:
            return []
        emb = embeddings if embeddings is not None else self.embedder.encode(texts)
        preds = self.classify_general(texts)
        groups: Dict[str, List[int]] = defaultdict(list)
        for i, (label, _) in enumerate(preds):
            groups[label].append(i)

        clusters: List[ThemeCluster] = []
        for cls in self.categories + [OTHER]:
            if groups.get(cls):
                clusters.extend(self._tier2(cls, groups[cls], texts, emb))

        # make names unique
        seen: Dict[str, int] = {}
        for c in clusters:
            key = f"{c.general_class}|{c.name}"
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                c.name = f"{c.name} ({seen[key]})"
        clusters.sort(key=lambda c: len(c.indices), reverse=True)
        return clusters
