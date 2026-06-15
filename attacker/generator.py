import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

URL = "http://localhost:8000/cpu"

def send_one(i: int):
    start = time.time()
    try:
        response = requests.get(URL)
        elapsed = time.time() - start
        return f"{i}: status={response.status_code}, time={elapsed:.3f}s, body={response.text}"
    except requests.RequestException as e:
        return f"{i}: error {e}"

def send_parallel(count: int = 30, workers: int = 10):
    total_start = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(send_one, i + 1) for i in range(count)]
        for future in as_completed(futures):
            print(future.result())

    total_elapsed = time.time() - total_start
    print(f"\nTOTAL TIME: {total_elapsed:.3f}s")

if __name__ == "__main__":
    send_parallel()