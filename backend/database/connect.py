from database.database import engine
from sqlalchemy.exc import OperationalError
import time

def wait_for_db():
    for i in range(10):
        try:
            conn = engine.connect()
            conn.close()
            print("DB is ready")
            break
        except OperationalError:
            print("Waiting for DB...")
            time.sleep(3)
    else:
        raise Exception("Could not connect to DB")
