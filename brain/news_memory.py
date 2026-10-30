import json
import os


NEWS_MEMORY_FILE = (
    "data/news_memory.json"
)


# =========================================
# INIT
# =========================================

def initialize_news_memory():

    os.makedirs(
        "data",
        exist_ok=True
    )

    if not os.path.exists(
        NEWS_MEMORY_FILE
    ):

        with open(
            NEWS_MEMORY_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                [],
                file,
                indent=4
            )


# =========================================
# LOAD
# =========================================

def load_news_memory():

    initialize_news_memory()

    with open(
        NEWS_MEMORY_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )


# =========================================
# SAVE
# =========================================

def save_news_memory(data):

    with open(
        NEWS_MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4
        )


# =========================================
# RECORD EVENT
# =========================================

def record_news_event(

    event_name,
    market_direction,
    volatility,
    result

):

    data = load_news_memory()

    data.append({

        "event":
        event_name,

        "direction":
        market_direction,

        "volatility":
        volatility,

        "result":
        result

    })

    save_news_memory(
        data
    )


# =========================================
# GET NEWS SCORE
# =========================================

def get_news_score(

    event_name=None

):

    data = load_news_memory()

    if event_name is None:

        if len(data) < 5:

            return 50

        wins = 0

        for item in data:

            if item["result"] == "WIN":

                wins += 1

        return round(

            wins /

            len(data)

            * 100,

            2

        )

    wins = 0

    total = 0

    for item in data:

        if item["event"] == event_name:

            total += 1

            if item["result"] == "WIN":

                wins += 1

    if total < 5:

        return 50

    return round(

        wins /

        total

        * 100,

        2

    )