from collections import defaultdict, deque
from datetime import datetime


class ChatMemory:


    def __init__(self, limit=10):

        self.limit = limit

        self.chats = defaultdict(
            lambda: deque(maxlen=self.limit)
        )



    def add(
        self,
        chat_id,
        user,
        text
    ):

        self.chats[chat_id].append(
            {
                "time": datetime.now().strftime("%H:%M"),
                "user": user,
                "text": text
            }
        )



    def get(
        self,
        chat_id
    ):

        messages = self.chats.get(
            chat_id,
            []
        )


        result = []


        for msg in messages:

            result.append(
                f"{msg['user']}: {msg['text']}"
            )


        return "\n".join(result)



# глобальная память чата

memory = ChatMemory()
