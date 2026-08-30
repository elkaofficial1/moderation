import json
import time

from ai import moderate_message


INPUT = "real_chat.txt"
OUTPUT = "real_chat_results.json"


context = []

results = []

with open(INPUT, "r", encoding="utf-8") as f:
    messages = [
        x.strip()
        for x in f
        if x.strip()
    ]


for i, text in enumerate(messages, 1):

    history = "\n".join(context[-5:])

    start = time.time()

    result = moderate_message(
        text,
        history
    )

    elapsed = round(
        time.time() - start,
        3
    )

    print(
        i,
        result.category,
        result.action,
        elapsed,
        text[:60]
    )


    results.append(
        {
            "message": text,
            "category": result.category,
            "severity": result.severity,
            "action": result.action,
            "reason": result.reason,
            "time": elapsed
        }
    )


    context.append(text)



with open(
    OUTPUT,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        results,
        f,
        ensure_ascii=False,
        indent=2
    )


print("\nГОТОВО")
print("Сообщений:", len(results))
print("Файл:", OUTPUT)
