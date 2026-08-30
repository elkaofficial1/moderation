def post_process(category, message, reason):
    text = message.lower().strip()

    direct_insults = [
        "ты тупой",
        "ты идиот",
        "ты еблан",
        "ты дебил",
        "ты лох",
        "ты дурак",
        "ты придурок",
        "ты конченый",
        "ты ничтожество",
    ]

    if any(x in text for x in direct_insults):
        return (
            "insult",
            0.7,
            "premoderation",
            "Прямое оскорбление человека",
        )

    if category == "illegal":
        illegal_intent = [
            "как сделать",
            "как изготовить",
            "как собрать",
            "как приготовить",
            "где купить",
            "где достать",
            "купить",
            "продам",
            "продать",
            "попробовать наркоту",
        ]

        illegal_topics = [
            "бомб",
            "взрывчат",
            "наркот",
            "наркоту",
            "кокаин",
            "героин",
        ]

        if any(x in text for x in illegal_intent) and any(
            x in text for x in illegal_topics
        ):
            return (
                "illegal",
                1.0,
                "block",
                reason or "Очевидное запрещённое действие",
            )

        return (
            "safe",
            0.2,
            "allow",
            "Упоминание запрещённой темы без явного запрещённого действия",
        )

    if category == "advertising":
        buy_words = [
            "купите",
            "купить",
            "продам",
            "продаю",
            "закажите",
            "заказать",
            "скидка",
            "акция",
            "в наличии",
        ]

        if not any(x in text for x in buy_words):
            return (
                "safe",
                0.2,
                "allow",
                "Упоминание товара без явной рекламы",
            )

    if category == "criticism":
        return (
            "criticism",
            0.3,
            "allow",
            reason or "Критика товара или мнения",
        )

    return category, None, None, reason


def decide(category, severity):
    if category == "illegal":
        return "block"

    if category in ("insult", "harassment", "advertising"):
        return "premoderation"

    return "allow"
