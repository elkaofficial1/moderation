from collections import deque


class ChatContext:
    def __init__(self, size=10):
        self.messages = deque(maxlen=size)

    def add(self, user, text):
        self.messages.append({
            "user": user,
            "text": text,
        })

    def format(self):
        if not self.messages:
            return "История отсутствует"

        return "\n".join(
            f'{item["user"]}: {item["text"]}'
            for item in self.messages
        )
