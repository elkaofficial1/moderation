import json
import os
from datetime import datetime


FILE="data/pending.json"


def load_queue():

    if not os.path.exists(FILE):
        return []

    with open(FILE) as f:
        return json.load(f)



def save_queue(data):

    with open(FILE,"w") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )



def send_to_premoderation(result,text):

    queue=load_queue()


    queue.append({

        "text":text,
        "category":result.category,
        "confidence":result.confidence,
        "reason":result.reason,
        "time":str(datetime.now()),
        "status":"waiting"

    })


    save_queue(queue)


    return True
