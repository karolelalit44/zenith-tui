import datetime


def greet():
    now = datetime.datetime.now()
    hour = now.hour
    if hour < 12:
        print("Good morning!")
    elif hour < 18:
        print("Good afternoon!")
    else:
        print("Good evening!")

if __name__ == "__main__":
    greet()
