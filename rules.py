import json
import os
import re

BLACKLIST_FILE = "data/blacklist.txt"


def load_words(path):
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        return [
            line.strip().lower()
            for line in f
            if line.strip() and not line.startswith("#")
        ]


def check_rules(text):
    t = text.lower().strip()

    explicit_illegal = [
        "как сделать бомбу",
        "как изготовить бомбу",
        "как сделать взрывчатку",
        "как изготовить взрывчатку",
        "как собрать взрывное устройство",
        "где купить наркотики",
        "где купить наркоту",
        "где достать наркотики",
        "где достать наркоту",
        "купить кокаин",
        "купить героин",
        "продам наркотики",
        "продам наркоту",
        "попробовать наркоту",
    ]

    for phrase in explicit_illegal:
        if phrase in t:
            return {
                "category": "illegal",
                "severity": 1.0,
                "action": "block",
                "reason": phrase,
            }

    fast_safe = [
        "привет",
        "спасибо",
        "понятно",
        "ясно",
        "ага",
        "ок",
        "окей",
        "класс",
        "супер",
        "топ",
        "понял",
        "интересно",
        "ахаха",
        "😂",
        "🤣",
        "👍",
        "🔥",
        "крутой чай",
        "отличный чай",
    ]

    if any(x in t for x in fast_safe):
        return {
            "category": "safe",
            "severity": 0.2,
            "action": "allow",
            "reason": "fast_safe",
        }

    return None
