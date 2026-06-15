import asyncio
import json
from time import sleep, time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import defense, metrics, alerts, attacker, scenario

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

connected_clients: list[WebSocket] = []
_pending_report = None


class DefenseControl(BaseModel):
    enabled: bool


class AttackerConfig(BaseModel):
    workers: int = 5
    interval: float = 0.5
    scenario: str = "flood"


class ManualBlockRequest(BaseModel):
    ip: str


EXEMPT_PATHS = {
    "/attacker/status",
    "/attacker/stop",
    "/attacker/start",
    "/attacker/normal/start",
    "/attacker/normal/stop",
    "/scenario/start",
    "/scenario/stop",
    "/scenario/status",
    "/defense",
    "/defense/rate-limiting",
    "/defense/ip-blocking",
    "/defense/emergency",
    "/defense/unblock-all",
    "/defense/manual-block",
    "/metrics",
    "/alerts",
    "/ws",
    "/static",
}


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def on_scenario_complete(report: dict):
    global _pending_report
    _pending_report = report


@app.middleware("http")
async def monitor_and_protect(request: Request, call_next):
    client_ip = get_client_ip(request)
    path = request.url.path

    metrics.record_request(path)

    if path not in EXEMPT_PATHS:
        allowed, reason, retry_after = defense.check_request(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too Many Requests",
                    "message": "Rate limit exceeded",
                    "reason": reason,
                },
                headers={"Retry-After": str(retry_after)},
            )

    start = time()
    response = await call_next(request)
    elapsed = time() - start

    metrics.record_latency(elapsed)
    response.headers["X-Response-Time"] = f"{elapsed:.4f}s"
    return response


@app.get("/")
def home():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/heavy")
def heavy():
    sleep(2)
    return {"message": "heavy endpoint"}


@app.get("/cpu")
def cpu():
    total = 0
    for i in range(50_000_000):
        total += i
    return {"message": "cpu endpoint", "total": total}


@app.get("/metrics")
def get_metrics():
    return metrics.snapshot()


@app.get("/defense")
def get_defense_state():
    return defense.snapshot()


@app.get("/alerts")
def get_alerts():
    return alerts.snapshot()


@app.get("/attacker/status")
def get_attacker_status():
    return attacker.snapshot()


@app.get("/scenario/status")
def get_scenario_status():
    return scenario.snapshot()


@app.post("/defense/rate-limiting")
def control_rate_limiting(body: DefenseControl):
    defense.set_rate_limiting(body.enabled)
    scenario.record_action(
        "defense_on" if body.enabled else "defense_off",
        f"rate-limiting: {'ON' if body.enabled else 'OFF'}",
    )
    return {"rate_limiting_enabled": body.enabled}


@app.post("/defense/ip-blocking")
def control_ip_blocking(body: DefenseControl):
    defense.set_ip_blocking(body.enabled)
    scenario.record_action(
        "defense_on" if body.enabled else "defense_off",
        f"ip-blocking: {'ON' if body.enabled else 'OFF'}",
    )
    return {"ip_blocking_enabled": body.enabled}


@app.post("/defense/emergency")
def control_emergency(body: DefenseControl):
    defense.set_emergency_mode(body.enabled)
    scenario.record_action(
        "defense_on" if body.enabled else "defense_off",
        f"emergency: {'ON' if body.enabled else 'OFF'}",
    )
    return {"emergency_mode": body.enabled}


@app.post("/defense/unblock-all")
def unblock_all():
    count = defense.unblock_all()
    return {"unblocked_count": count}


@app.post("/defense/manual-block")
def manual_block(body: ManualBlockRequest):
    result = defense.manual_block_ip(body.ip)
    scenario.record_action("manual_block", f"manual block: {body.ip}", ip=body.ip)
    return {"blocked": result, "ip": body.ip}


@app.post("/attacker/start")
def start_attacker(body: AttackerConfig):
    started = attacker.start(
        workers=body.workers,
        interval=body.interval,
        scenario=body.scenario,
    )
    return {"started": started, **attacker.snapshot()}


@app.post("/attacker/stop")
def stop_attacker():
    stopped = attacker.stop()
    return {"stopped": stopped, **attacker.snapshot()}


@app.post("/attacker/normal/start")
def start_normal():
    started = attacker.start_normal()
    return {"started": started, **attacker.snapshot()}


@app.post("/attacker/normal/stop")
def stop_normal():
    stopped = attacker.stop_normal()
    return {"stopped": stopped, **attacker.snapshot()}


@app.post("/scenario/start")
def start_scenario():
    result = scenario.start(on_complete=on_scenario_complete)
    return result


@app.post("/scenario/stop")
def stop_scenario():
    result = scenario.stop()
    return result


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _pending_report
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            metrics_data  = metrics.snapshot()
            defense_data  = defense.snapshot()
            attacker_data = attacker.snapshot()
            scenario_data = scenario.snapshot()

            new_alerts = alerts.check(
                rps=metrics_data["rps_10s"],
                latency_ms=metrics_data["avg_latency_ms"],
                blocked_count=len(defense_data["blocked_ips"]),
            )

            data = {
                **metrics_data,
                **defense_data,
                **attacker_data,
                "scenario_running":          scenario_data["running"],
                "scenario_name":             scenario_data["scenario"],
                "scenario_false_positives":  scenario_data["false_positives"],
                "scenario_phase":            scenario_data["phase"],
                "new_alerts":                new_alerts,
                "alert_history":             alerts.snapshot(),
                "pending_report":            None,
            }

            if _pending_report is not None:
                data["pending_report"] = _pending_report
                _pending_report = None

            await websocket.send_text(json.dumps(data))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        connected_clients.remove(websocket)