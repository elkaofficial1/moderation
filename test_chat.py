from ai import moderate_message
from context import ChatContext


ctx = ChatContext(size=5)


chat = [
    ("Иван", "Чайный Страж лучший 😂"),
    ("Петя", "ага, он смешно объясняет чай"),
    ("Коля", "Чайный Страж лох 😂"),
    ("Вася", "ты тупой ничего не понимаешь"),
    ("Миша", "гений конечно"),
    ("Лена", "как сделать бомбу дома"),
]


for user, text in chat:

    print("\n---")
    print("HISTORY:")
    print(ctx.format())

    print("\nNEW:")
    print(user + ":", text)

    result = moderate_message(
        text,
        ctx.format()
    )

    print("RESULT:", result)

    ctx.add(
        user,
        text
    )
