import threading
import time
import random
from concurrent.futures import ThreadPoolExecutor

import requests

lock = threading.Lock()
stop_event = threading.Event()
normal_stop_event = threading.Event()

BASE_URL = "http://localhost:8000"

ATTACK_ENDPOINTS = ["/health", "/"]
NORMAL_ENDPOINTS = ["/", "/health"]

NORMAL_USER_IPS = [
    "10.142.33.21",
    "10.142.45.38",
    "10.142.51.102",
    "10.142.62.55",
    "10.142.78.3",
]

FLOOD_IP       = "10.142.19.77"
SLOWLORIS_IP   = "10.142.28.193"
DISTRIBUTED_IPS = [
    "10.142.11.204",
    "10.142.23.117",
    "10.142.37.89",
    "10.142.44.156",
    "10.142.59.231",
]

_thread: threading.Thread | None = None
_normal_thread: threading.Thread | None = None
_running = False
_normal_running = False

_stats = {
    "total_sent": 0,
    "total_success": 0,
    "total_blocked": 0,
    "total_error": 0,
    "workers": 5,
    "interval": 0.5,
    "scenario": "flood",
}

_normal_stats = {
    "total_sent": 0,
    "total_blocked": 0,
}


def _send_attack(ip: str, endpoint: str):
    if stop_event.is_set():
        return
    try:
        res = requests.get(
            BASE_URL + endpoint,
            timeout=2,
            headers={"X-Forwarded-For": ip},
        )
        with lock:
            _stats["total_sent"] += 1
            if res.status_code == 429:
                _stats["total_blocked"] += 1
            else:
                _stats["total_success"] += 1
    except requests.RequestException:
        with lock:
            _stats["total_sent"] += 1
            _stats["total_error"] += 1


def _send_normal(ip: str):
    if normal_stop_event.is_set():
        return
    endpoint = random.choice(NORMAL_ENDPOINTS)
    try:
        res = requests.get(
            BASE_URL + endpoint,
            timeout=3,
            headers={"X-Forwarded-For": ip},
        )
        with lock:
            _normal_stats["total_sent"] += 1
            if res.status_code == 429:
                _normal_stats["total_blocked"] += 1
    except requests.RequestException:
        pass


def _flood_loop():
    executor = ThreadPoolExecutor(max_workers=_stats["workers"])
    try:
        while not stop_event.is_set():
            for _ in range(_stats["workers"]):
                if stop_event.is_set():
                    break
                executor.submit(_send_attack, FLOOD_IP, random.choice(ATTACK_ENDPOINTS))
            stop_event.wait(timeout=_stats["interval"])
    finally:
        executor.shutdown(wait=False)


def _distributed_loop():
    executor = ThreadPoolExecutor(max_workers=_stats["workers"])
    try:
        while not stop_event.is_set():
            for ip in DISTRIBUTED_IPS:
                if stop_event.is_set():
                    break
                executor.submit(_send_attack, ip, random.choice(ATTACK_ENDPOINTS))
            stop_event.wait(timeout=_stats["interval"])
    finally:
        executor.shutdown(wait=False)


def _slowloris_loop():
    while not stop_event.is_set():
        try:
            res = requests.get(
                BASE_URL + "/heavy",
                timeout=30,
                headers={"X-Forwarded-For": SLOWLORIS_IP},
            )
            with lock:
                _stats["total_sent"] += 1
                if res.status_code == 429:
                    _stats["total_blocked"] += 1
                else:
                    _stats["total_success"] += 1
        except requests.RequestException:
            with lock:
                _stats["total_sent"] += 1
                _stats["total_error"] += 1
        if stop_event.wait(timeout=0.1):
            break


def _normal_user_loop():
    while not normal_stop_event.is_set():
        ip = random.choice(NORMAL_USER_IPS)
        _send_normal(ip)
        normal_stop_event.wait(timeout=random.uniform(1.0, 3.0))


def start(workers: int = 5, interval: float = 0.5, scenario: str = "flood"):
    global _thread, _running
    if _running:
        return False

    _running = True
    _stats["workers"] = workers
    _stats["interval"] = interval
    _stats["scenario"] = scenario
    _stats["total_sent"] = 0
    _stats["total_success"] = 0
    _stats["total_blocked"] = 0
    _stats["total_error"] = 0

    stop_event.clear()

    if scenario == "flood":
        _thread = threading.Thread(target=_flood_loop, daemon=True)
    elif scenario == "distributed":
        _thread = threading.Thread(target=_distributed_loop, daemon=True)
    elif scenario == "slowloris":
        _thread = threading.Thread(target=_slowloris_loop, daemon=True)
    else:
        _thread = threading.Thread(target=_flood_loop, daemon=True)

    _thread.start()
    return True


def stop():
    global _running
    if not _running:
        return False
    _running = False
    stop_event.set()
    return True


def start_normal():
    global _normal_thread, _normal_running
    if _normal_running:
        return False
    _normal_running = True
    _normal_stats["total_sent"] = 0
    _normal_stats["total_blocked"] = 0
    normal_stop_event.clear()
    _normal_thread = threading.Thread(target=_normal_user_loop, daemon=True)
    _normal_thread.start()
    return True


def stop_normal():
    global _normal_running
    if not _normal_running:
        return False
    _normal_running = False
    normal_stop_event.set()
    return True


def snapshot() -> dict:
    with lock:
        total = _stats["total_sent"] or 1
        return {
            "running": _running,
            "normal_running": _normal_running,
            "scenario": _stats["scenario"],
            "total_sent": _stats["total_sent"],
            "total_success": _stats["total_success"],
            "total_blocked": _stats["total_blocked"],
            "total_error": _stats["total_error"],
            "block_rate": round(_stats["total_blocked"] / total * 100, 1),
            "workers": _stats["workers"],
            "interval": _stats["interval"],
            "normal_total_sent": _normal_stats["total_sent"],
            "normal_total_blocked": _normal_stats["total_blocked"],
        }