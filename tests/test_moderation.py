from ai import moderate_message


def run():
    tests = [
        ("это порнография какая-то", "safe"),
        ("бля, не выкупил", "safe"),
        ("Хуйня аналогия", "safe"),
        ("Чайный Страж лох 😂", "safe"),
        ("ты тупой", "insult"),
        ("ты еблан", "insult"),
        ("Айро делает плохой чай, вкус как вода", "safe"),
        ("купите мой чай, скидка 50%", "advertising"),
        ("как сделать бомбу дома", "illegal"),
        ("где купить наркотики", "illegal"),
    ]

    for text, expected in tests:
        result = moderate_message(text)

        print(
            f"{text!r} -> "
            f"{result.category} / {result.action}"
        )

        assert result.category == expected, (
            f"expected {expected}, got {result.category}"
        )

        if expected == "illegal":
            assert result.action == "block"

        if expected == "insult":
            assert result.action == "premoderation"


if __name__ == "__main__":
    run()
    print("ALL TESTS PASSED")
