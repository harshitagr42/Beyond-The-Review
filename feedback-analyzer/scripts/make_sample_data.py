"""Generate a synthetic reviews CSV (with some PII mixed in) for demos and tests.

    python scripts/make_sample_data.py --rows 1000 --out data/sample_reviews.csv
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

NEG = {
    "Streaming/Playback": [
        "Whenever I tap pause on a stream the whole app freezes.",
        "Video keeps buffering at the worst moment, even on fibre internet.",
        "The picture is stuck at low resolution on live streams.",
        "Audio drifts out of sync after about ten minutes of playback.",
        "Subtitles vanish whenever I resume a paused video.",
    ],
    "Comments & Social": [
        "The comment section never loads on live streams.",
        "I can't post comments on some channels, the send button does nothing.",
        "Replies to my comments disappear after a refresh.",
        "Sharing videos with friends fails every single time.",
    ],
    "Billing & Subscriptions": [
        "I got charged twice for my monthly subscription.",
        "Cancelled the plan but still got billed, and support will not refund me.",
        "The free trial turned into a paid plan without any reminder.",
        "Payment page errors out whenever I try to add a new card.",
    ],
    "Performance & Crashes": [
        "The app crashes right after the splash screen since the last update.",
        "Everything is slow and laggy, even scrolling the home page.",
        "Battery drain is awful, my phone gets hot within minutes.",
        "It force closes every time I switch apps and come back.",
    ],
    "UI/UX & Navigation": [
        "I can't find the settings anywhere, the menu layout is confusing.",
        "Search never shows the video I'm looking for.",
        "Buttons are tiny and I keep hitting the wrong tab.",
        "The redesign moved the library tab and now nothing makes sense.",
    ],
}
POS = {
    "Streaming/Playback": ["Smooth playback and sharp picture quality.", "Streaming has been flawless on my TV."],
    "Comments & Social": ["Friendly community and replying to comments is easy.", "Sharing clips with friends is great."],
    "Billing & Subscriptions": ["Fair pricing and cancelling was painless.", "Refund came through within two days, thanks!"],
    "Performance & Crashes": ["Fast, stable and easy on the battery.", "No crashes at all since the last update."],
    "UI/UX & Navigation": ["Clean design and very easy to navigate.", "Love the dark mode and the new home screen."],
}
NEUTRAL = [
    "I mostly watch on my tablet in the evening.",
    "Using the premium plan since March.",
    "The app has five tabs along the bottom.",
    "I updated to the latest version yesterday.",
]
PREFIX = ["", "", "", "Honestly, ", "Update: ", "Since the last update, ", "Seriously, ", "FYI "]
PII = [
    "Email me at {name}.{n}@example.com if you need details.",
    "Call me on +1 415-555-01{n:02d}.",
    "My card 4111 1111 1111 1111 was charged.",
    "Seen from IP 192.168.1.{n}.",
    "My SSN 123-45-6789 is on the invoice, please fix.",
    "Reach me at 98765 432{n:02d}.",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--out", default="data/sample_reviews.csv")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pii-rate", type=float, default=0.08)
    args = ap.parse_args()

    rnd = random.Random(args.seed)
    cats = list(NEG)
    rows = []
    for _ in range(args.rows):
        roll = rnd.random()
        if roll < 0.60:
            cat = rnd.choice(cats)
            text, rating = rnd.choice(NEG[cat]), rnd.choice([1, 1, 2, 2, 3])
        elif roll < 0.85:
            cat = rnd.choice(cats)
            text, rating = rnd.choice(POS[cat]), rnd.choice([4, 5, 5])
        else:
            text, rating = rnd.choice(NEUTRAL), 3
        text = rnd.choice(PREFIX) + (text if not rnd.choice(PREFIX) else text[0].lower() + text[1:])
        if rnd.random() < args.pii_rate:
            text += " " + rnd.choice(PII).format(name=rnd.choice(["sam", "priya", "alex"]), n=rnd.randint(10, 99))
        rows.append(
            {
                "review_text": text,
                "date": (date(2026, 10, 1) - timedelta(days=rnd.randint(0, 89))).isoformat(),
                "rating": rating,
            }
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
