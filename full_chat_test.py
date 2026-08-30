import json
import time

from ai import moderate_message
from context import ChatContext


ctx = ChatContext(size=5)

results = []

start = time.time()


with open("chat_test.txt", encoding="utf-8") as f:
    lines = [
        x.strip()
        for x in f
        if x.strip()
    ]


for i, text in enumerate(lines, 1):

    t0 = time.time()

    result = moderate_message(
        text,
        ctx.format()
    )

    elapsed = round(
        time.time() - t0,
        3
    )

    item = {
        "id": i,
        "message": text,
        "result": result.to_dict(),
        "time": elapsed
    }

    results.append(item)

    ctx.add(
        "user",
        text
    )

    print(
        i,
        result.category,
        result.action,
        elapsed,
        "sec"
    )


with open(
    "moderation_results.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        results,
        f,
        ensure_ascii=False,
        indent=2
    )


total = time.time() - start


stats = {}

for r in results:
    c = r["result"]["category"]
    stats[c] = stats.get(c, 0) + 1


print("\nСТАТИСТИКА:")
for k,v in stats.items():
    print(k, v)

print("\nВсего сообщений:", len(results))
print("Время:", round(total,2), "сек")
