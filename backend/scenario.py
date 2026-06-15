import threading
import time
import random

from . import attacker, defense

lock = threading.Lock()

_running = False
_thread: threading.Thread | None = None
_monitor_thread: threading.Thread | None = None
_on_complete = None

_result = {
    "scenario": None,
    "started_at": None,
    "ended_at": None,
    "defense_activated_at": None,
    "peak_rps": 0,
    "total_attack_sent": 0,
    "total_attack_blocked": 0,
    "total_normal_sent": 0,
    "total_normal_blocked": 0,
    "manual_blocks": [],
    "false_positives": 0,
    "actions": [],
    "auto_completed": False,
    "phase": "idle",
}

SCENARIOS = ["flood", "distributed", "slowloris"]

NORMAL_USER_IPS = {
    "10.142.33.21",
    "10.142.45.38",
    "10.142.51.102",
    "10.142.62.55",
    "10.142.78.3",
}

RPS_THRESHOLD = 5
BLOCK_RATE_THRESHOLD = 80
STABLE_DURATION = 10


def _scenario_loop(scenario: str):
    time.sleep(random.uniform(3.0, 6.0))
    with lock:
        if not _running:
            return
        _result["phase"] = "attacking"
    attacker.start(workers=5, interval=0.5, scenario=scenario)


def _monitor_loop():
    global _running

    stable_since = None

    while True:
        with lock:
            if not _running:
                break
            phase = _result["phase"]

        if phase != "attacking" and phase != "recovering":
            time.sleep(1)
            continue

        snap = attacker.snapshot()
        block_rate = snap.get("block_rate", 0)
        total_sent = snap.get("total_sent", 0)
        total_blocked = snap.get("total_blocked", 0)

        from . import metrics as _metrics
        rps = _metrics.get_rps(10)

        is_stable = (
            total_sent > 20 and block_rate >= BLOCK_RATE_THRESHOLD
        ) or (
            total_sent > 20 and rps <= RPS_THRESHOLD
        )

        if is_stable:
            if stable_since is None:
                stable_since = time.time()
                with lock:
                    _result["phase"] = "recovering"
            elif time.time() - stable_since >= STABLE_DURATION:
                with lock:
                    _result["phase"] = "complete"
                    _result["auto_completed"] = True
                _auto_complete()
                break
        else:
            stable_since = None
            with lock:
                if _result["phase"] == "recovering":
                    _result["phase"] = "attacking"

        time.sleep(1)


def _auto_complete():
    global _running

    with lock:
        _running = False

    attacker.stop()
    attacker.stop_normal()

    snap = attacker.snapshot()
    with lock:
        _result["ended_at"] = time.time()
        _result["total_attack_sent"]    = snap["total_sent"]
        _result["total_attack_blocked"] = snap["total_blocked"]
        _result["total_normal_sent"]    = snap["normal_total_sent"]
        _result["total_normal_blocked"] = snap["normal_total_blocked"]

    if _on_complete:
        _on_complete(_build_report())


def start(on_complete=None) -> dict:
    global _running, _thread, _monitor_thread, _on_complete

    with lock:
        if _running:
            return {"started": False}

        scenario = random.choice(SCENARIOS)
        _running = True
        _on_complete = on_complete
        _result["scenario"] = scenario
        _result["started_at"] = time.time()
        _result["ended_at"] = None
        _result["defense_activated_at"] = None
        _result["peak_rps"] = 0
        _result["total_attack_sent"] = 0
        _result["total_attack_blocked"] = 0
        _result["total_normal_sent"] = 0
        _result["total_normal_blocked"] = 0
        _result["manual_blocks"] = []
        _result["false_positives"] = 0
        _result["actions"] = []
        _result["auto_completed"] = False
        _result["phase"] = "waiting"

    defense.set_rate_limiting(False)
    defense.set_ip_blocking(False)
    defense.set_emergency_mode(False)
    defense.unblock_all()
    defense.reset_request_log()

    attacker.start_normal()

    _thread = threading.Thread(target=_scenario_loop, args=(scenario,), daemon=True)
    _thread.start()

    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
    _monitor_thread.start()

    return {"started": True, "hint": _get_hint(scenario)}


def stop() -> dict:
    global _running

    with lock:
        if not _running:
            return {"stopped": False, "report": None}
        _running = False
        _result["phase"] = "idle"

    attacker.stop()
    attacker.stop_normal()

    snap = attacker.snapshot()
    with lock:
        _result["ended_at"] = time.time()
        _result["total_attack_sent"]    = snap["total_sent"]
        _result["total_attack_blocked"] = snap["total_blocked"]
        _result["total_normal_sent"]    = snap["normal_total_sent"]
        _result["total_normal_blocked"] = snap["normal_total_blocked"]
        _result["auto_completed"] = False

    return {"stopped": True, "report": _build_report()}


def record_action(action_type: str, detail: str, ip: str = None):
    with lock:
        if not _running:
            return
        entry = {
            "type": action_type,
            "detail": detail,
            "timestamp": time.time(),
        }
        if ip:
            entry["ip"] = ip
        _result["actions"].append(entry)

        if action_type == "defense_on" and _result["defense_activated_at"] is None:
            _result["defense_activated_at"] = time.time()

        if action_type == "manual_block":
            _result["manual_blocks"].append(ip)
            if ip in NORMAL_USER_IPS:
                _result["false_positives"] += 1


def _get_hint(scenario: str) -> str:
    hints = {
        "flood":       "異常なトラフィックを検知しました。IPパターンを確認してください。",
        "distributed": "複数の送信元からアクセスがあります。慎重に判断してください。",
        "slowloris":   "レイテンシの異常を検知しました。接続数に注意してください。",
    }
    return hints.get(scenario, "異常を検知しました。")


def _build_report() -> dict:
    with lock:
        r = dict(_result)

    duration = 0
    if r["started_at"] and r["ended_at"]:
        duration = round(r["ended_at"] - r["started_at"], 1)

    time_to_defend = None
    if r["started_at"] and r["defense_activated_at"]:
        time_to_defend = round(r["defense_activated_at"] - r["started_at"], 1)

    total_attack = r["total_attack_sent"] or 1
    block_rate = round(r["total_attack_blocked"] / total_attack * 100, 1)

    score = 100

    score -= r["false_positives"] * 15

    if time_to_defend is None:
        pass
    elif time_to_defend <= 15:
        pass
    elif time_to_defend <= 20:
        score -= 10
    elif time_to_defend <= 25:
        score -= 20
    else:
        score -= 30

    if block_rate < 80:
        score -= 20

    if r["total_normal_blocked"] > 0:
        score -= r["total_normal_blocked"] * 10

    if r["auto_completed"]:
        score = min(score + 10, 100)

    score = max(0, min(100, score))

    grade = "S" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C" if score >= 60 else "D"

    scenario_names = {
        "flood":       "Flood Attack",
        "distributed": "Distributed Attack",
        "slowloris":   "Slowloris Attack",
    }

    return {
        "scenario":        scenario_names.get(r["scenario"], r["scenario"]),
        "duration_sec":    duration,
        "block_rate":      block_rate,
        "false_positives": r["false_positives"],
        "time_to_defend":  time_to_defend,
        "manual_blocks":   len(r["manual_blocks"]),
        "actions":         r["actions"],
        "score":           score,
        "grade":           grade,
        "normal_blocked":  r["total_normal_blocked"],
        "auto_completed":  r["auto_completed"],
        "phase":           r["phase"],
    }


def snapshot() -> dict:
    with lock:
        return {
            "running":          _running,
            "scenario":         _result["scenario"],
            "started_at":       _result["started_at"],
            "false_positives":  _result["false_positives"],
            "phase":            _result["phase"],
        }