"""MiniPaaS - a tiny Platform-as-a-Service simulator (Flask). Run: python app.py"""
import threading, time, uuid
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder=".")
APPS, LOCK = {}, threading.Lock()
RUNTIMES = {"python": 5000, "node": 3000, "java": 8080, "go": 8000}

def log(a, msg):
    a["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")

def set_state(a, state, delay, msg):
    """Move an app to `state` after `delay` seconds (simulates build/boot time)."""
    def run():
        time.sleep(delay)
        with LOCK:
            if a["id"] in APPS:
                a["status"] = state; log(a, msg)
    threading.Thread(target=run, daemon=True).start()

def view(a):
    return {k: v for k, v in a.items() if k != "logs"}

@app.get("/")
def home():
    return send_from_directory(".", "index.html")

@app.get("/api/apps")
def list_apps():
    with LOCK:
        return jsonify([view(a) for a in APPS.values()])

@app.post("/api/apps")
def deploy():
    d = request.get_json(force=True)
    name, rt = (d.get("name") or "").strip().lower(), d.get("runtime", "python")
    if not name.replace("-", "").isalnum():
        return jsonify(error="Name must use letters, numbers and dashes only."), 400
    if rt not in RUNTIMES:
        return jsonify(error=f"Runtime must be one of {list(RUNTIMES)}."), 400
    with LOCK:
        if any(a["name"] == name for a in APPS.values()):
            return jsonify(error=f"'{name}' already exists."), 409
        a = dict(id=uuid.uuid4().hex[:8], name=name, runtime=rt, instances=max(1, min(int(d.get("instances", 1)), 10)),
                 status="building", port=RUNTIMES[rt], url=f"https://{name}.minipaas.app", logs=[])
        APPS[a["id"]] = a
        log(a, f"Received code for {name} ({rt}). Building image...")
        set_state(a, "running", 2, f"Build done. {a['instances']} instance(s) live on port {a['port']}.")
    return jsonify(view(a)), 201

@app.post("/api/apps/<aid>/<action>")
def act(aid, action):
    with LOCK:
        a = APPS.get(aid)
        if not a: return jsonify(error="App not found."), 404
        if action == "stop":
            a["status"] = "stopped"; log(a, "Stopped by user.")
        elif action in ("start", "restart"):
            a["status"] = "starting"; log(a, f"{action.title()}ing...")
            set_state(a, "running", 1, "App is running.")
        elif action == "scale":
            n = max(1, min(int(request.get_json(force=True).get("instances", 1)), 10))
            log(a, f"Scaled {a['instances']} -> {n} instance(s)."); a["instances"] = n
        else:
            return jsonify(error="Unknown action."), 400
        return jsonify(view(a))

@app.delete("/api/apps/<aid>")
def remove(aid):
    with LOCK:
        return ("", 204) if APPS.pop(aid, None) else (jsonify(error="App not found."), 404)

@app.get("/api/apps/<aid>/logs")
def logs(aid):
    with LOCK:
        a = APPS.get(aid)
        return jsonify(a["logs"]) if a else (jsonify(error="App not found."), 404)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
