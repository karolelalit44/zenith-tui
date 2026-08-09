import datetime


def get_greeting():
    hour = datetime.datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif 12 <= hour < 18:
        return "Good afternoon"
    else:
        return "Good evening"

if __name__ == "__main__":
    print(get_greeting())
