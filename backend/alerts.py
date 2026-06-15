from collections import deque
from threading import Lock
from time import time
from dataclasses import dataclass, field

lock = Lock()

SPIKE_THRESHOLD_RPS = 20
LATENCY_THRESHOLD_MS = 500
ALERT_COOLDOWN = 10

@dataclass
class Alert:
    level: str
    kind: str
    message: str
    timestamp: float = field(default_factory=time)

alert_history: deque = deque(maxlen=100)

last_alerted_at: dict = {}


def _can_alert(kind: str, now: float) -> bool:
    last = last_alerted_at.get(kind)
    if last is None:
        return True
    return now - last >= ALERT_COOLDOWN


def _record(level: str, kind: str, message: str, now: float) -> Alert:
    alert = Alert(level=level, kind=kind, message=message, timestamp=now)
    alert_history.append(alert)
    last_alerted_at[kind] = now
    return alert


def check(rps: float, latency_ms: float, blocked_count: int) -> list[dict]:
    now = time()
    new_alerts = []

    with lock:
        if rps > SPIKE_THRESHOLD_RPS and _can_alert("spike", now):
            alert = _record(
                level="danger",
                kind="spike",
                message=f"Traffic spike detected — rps: {rps}",
                now=now,
            )
            new_alerts.append(_to_dict(alert))

        if latency_ms > LATENCY_THRESHOLD_MS and _can_alert("latency", now):
            alert = _record(
                level="warning",
                kind="latency",
                message=f"High latency detected — {latency_ms}ms",
                now=now,
            )
            new_alerts.append(_to_dict(alert))

        if blocked_count > 0 and _can_alert("attack", now):
            alert = _record(
                level="danger",
                kind="attack",
                message=f"Attack detected — {blocked_count} IPs blocked",
                now=now,
            )
            new_alerts.append(_to_dict(alert))

    return new_alerts


def snapshot() -> list[dict]:
    with lock:
        return [_to_dict(a) for a in list(alert_history)[-20:]]


def _to_dict(alert: Alert) -> dict:
    return {
        "level": alert.level,
        "kind": alert.kind,
        "message": alert.message,
        "timestamp": alert.timestamp,
    }