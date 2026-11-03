
from mongo_db import test_connection

if __name__ == "__main__":
    try:
        print(test_connection())
    except Exception as error:
        print("MongoDB connection failed:")
        print(type(error).__name__, error)
