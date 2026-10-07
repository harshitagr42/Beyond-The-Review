"""Embedded 100-row validation set (hand-written, synthetic).

20 reviews per Tier-1 category; 40 Negative / 30 Positive / 30 Neutral overall.
Labels are 3-class (Positive / Neutral / Negative). This is a smoke-test set for catching
regressions and broken installs - it is NOT a substitute for evaluating on your own
labelled reviews.
"""
from __future__ import annotations

from typing import Dict, List


def _rows(category: str, neg: List[str], pos: List[str], neu: List[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for sentiment, items in (("Negative", neg), ("Positive", pos), ("Neutral", neu)):
        rows += [{"text": t, "sentiment": sentiment, "category": category} for t in items]
    return rows


VALIDATION_SET: List[Dict[str, str]] = (
    _rows(
        "Streaming/Playback",
        neg=[
            "Whenever I tap pause on a 1080p stream, the app freezes completely.",
            "Video buffers every few seconds even on fast wifi.",
            "Playback keeps stopping halfway through every episode.",
            "The audio is out of sync with the video on all live streams.",
            "Subtitles disappear after I pause and resume the video.",
            "Stream quality is stuck at 360p no matter what I choose.",
            "Can't seek forward, the progress bar jumps back to the start.",
            "Live streams cut out right when the match gets exciting.",
        ],
        pos=[
            "Crystal clear 4K streaming, no buffering at all. Love it.",
            "Playback is smooth and the picture quality is fantastic.",
            "Love that videos resume exactly where I left off.",
            "The new autoplay for the next episode works great.",
            "Streaming on my TV via casting is seamless now.",
            "Excellent video quality and the audio is crisp.",
        ],
        neu=[
            "I watched three episodes of the series yesterday.",
            "The video player has a playback speed option in the settings.",
            "I mostly stream on my tablet in the evenings.",
            "Is there a way to download videos for offline playback?",
            "The stream starts with a short ad before the video.",
            "I use the app to watch live sports on weekends.",
        ],
    )
    + _rows(
        "Comments & Social",
        neg=[
            "Comment section fails to load for live streams.",
            "I cannot post a comment on videos from certain channels.",
            "My replies to other people's comments never show up.",
            "The comment box closes every time I try to type.",
            "Notifications for new replies are delayed by hours.",
            "Sharing a video to my friends always fails with an error.",
            "Can't follow other users anymore, the follow button does nothing.",
            "Spam bots flood the comments and there is no easy way to report them.",
        ],
        pos=[
            "Love the community here, the comments are so friendly and helpful.",
            "Great that I can now reply directly to a comment thread.",
            "Sharing clips with my friends is super easy and fun.",
            "The new reaction emojis on comments are a nice touch.",
            "Following my favorite creators and seeing their posts works really well.",
            "Happy with the way comments are sorted by top and newest.",
        ],
        neu=[
            "I read the comments after watching most videos.",
            "There is a comments tab below the video player.",
            "I sometimes share videos with my brother on chat.",
            "Users can follow channels from the profile page.",
            "I turned off comments on my own uploads last week.",
            "How do I mention another user in a comment?",
        ],
    )
    + _rows(
        "Billing & Subscriptions",
        neg=[
            "I was charged twice for the same monthly subscription.",
            "Cancelled my plan but the app still billed me this month.",
            "Refund request has been ignored for three weeks now.",
            "The price increase is ridiculous for what you get.",
            "Cannot update my credit card, the payment page keeps erroring.",
            "Free trial converted to a paid plan without any warning.",
            "No invoice emails are sent after payment, I need them for work.",
            "Premium features are still locked even after I paid.",
        ],
        pos=[
            "Subscription renewal was smooth and the pricing is fair.",
            "Got my refund within two days, great customer support.",
            "The annual plan is a really good deal compared to monthly.",
            "Easy to cancel and manage my subscription in settings.",
            "Billing is transparent and the invoices are detailed.",
            "Happy with the student discount on premium.",
        ],
        neu=[
            "I subscribed to the premium plan in March.",
            "The monthly plan renews on the first of each month.",
            "I pay for the family plan through the app store.",
            "Where can I find my billing history?",
            "The trial lasts seven days before the first charge.",
            "My subscription is billed in Indian rupees.",
        ],
    )
    + _rows(
        "Performance & Crashes",
        neg=[
            "The app crashes every time I open it after the latest update.",
            "Terribly slow, every screen takes ages to load.",
            "It drains my battery in less than two hours.",
            "My phone gets hot after ten minutes of using this app.",
            "App force closes whenever I switch to another app and come back.",
            "Constant lag and stuttering, even on a flagship phone.",
            "Login screen hangs forever and never gets past the spinner.",
            "Uses way too much memory and slows down my whole phone.",
        ],
        pos=[
            "Runs fast and stable, haven't had a single crash in months.",
            "The latest update fixed the lag, it feels so much snappier.",
            "Impressively lightweight and barely uses any battery.",
            "Loads instantly now, great performance improvements.",
            "Very stable app, zero bugs so far.",
            "Startup time is much faster since the last release.",
        ],
        neu=[
            "I updated the app to the newest version yesterday.",
            "The app is about 150 MB on my phone.",
            "I use it on an older Android device.",
            "Does the app support background refresh?",
            "The release notes mention bug fixes and performance changes.",
            "I reinstalled the app on my new phone last week.",
        ],
    )
    + _rows(
        "UI/UX & Navigation",
        neg=[
            "I can never find the settings menu, the navigation is so confusing.",
            "The new layout is cluttered and hard to use.",
            "Search is useless, it never finds the video I'm looking for.",
            "Buttons are way too small and I keep tapping the wrong one.",
            "Dark mode makes the text almost impossible to read.",
            "Too many tabs and menus, I get lost trying to go back to the home screen.",
            "Why did you move the library tab? The redesign is a mess.",
            "No way to change the font size, the text is tiny.",
        ],
        pos=[
            "Beautiful clean design and so easy to navigate.",
            "The redesigned home screen is intuitive and looks great.",
            "Love the dark mode, it is easy on the eyes.",
            "Search works well and the filters are really handy.",
            "Navigation is simple, found everything within seconds.",
            "The bottom tab bar makes one-handed use really comfortable.",
        ],
        neu=[
            "The menu is on the left side of the screen.",
            "There is a search bar at the top of the home page.",
            "I switched to the light theme in the settings.",
            "The app has five tabs along the bottom.",
            "Is there a tablet layout for the app?",
            "I mostly use the library and search sections.",
        ],
    )
)
