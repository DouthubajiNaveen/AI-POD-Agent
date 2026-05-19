"""
PodSight AI — Main Server
Starts collector + agents + Flask REST API.
Run: python3 server.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# ── Load .env file automatically ─────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env file loaded")
except ImportError:
    print("⚠️  python-dotenv not installed. Run: pip install python-dotenv")

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from backend.collector import collector
from agents.multi_agent import AgentOrchestrator
from agents.security_agent import SecurityAgent

app = Flask(__name__, static_folder="dashboard")
CORS(app)


# ── Dashboard route ─────────────────────────────────────────────────────────
@app.route("/")
def dashboard():
    return send_from_directory("dashboard", "index.html")


# ── Start background services ─────────────────────────────────────────────────
collector.start()

orchestrator = AgentOrchestrator(collector)
orchestrator.start()

security = SecurityAgent(collector)
security.start()


# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "podsight-ai"})


@app.route("/api/summary")
def summary():
    return jsonify(collector.get_summary())


@app.route("/api/pods")
def pods():
    ns = request.args.get("namespace")
    all_pods = collector.get_all_pods()
    if ns and ns != "all":
        all_pods = [p for p in all_pods if p["namespace"] == ns]
    return jsonify(all_pods)


@app.route("/api/pods/<pod_name>")
def pod_detail(pod_name):
    pod = collector.get_pod(pod_name)
    if not pod:
        return jsonify({"error": "Pod not found"}), 404
    return jsonify(pod)


@app.route("/api/pods/<pod_name>/history")
def pod_history(pod_name):
    return jsonify(collector.get_history(pod_name))


@app.route("/api/namespaces")
def namespaces():
    summary = collector.get_summary()
    return jsonify(summary.get("namespaces", []))


@app.route("/api/anomalies")
def anomalies():
    limit = int(request.args.get("limit", 50))
    return jsonify(collector.get_anomalies(limit))


@app.route("/api/dependencies")
def dependencies():
    return jsonify(collector.get_dependencies())


@app.route("/api/agents")
def agents():
    return jsonify(orchestrator.get_results())


# ── Security endpoints ────────────────────────────────────────────────────────

@app.route("/api/security/threats")
def threats():
    limit = int(request.args.get("limit", 50))
    return jsonify(security.get_threats(limit))


@app.route("/api/security/scores")
def scores():
    return jsonify({
        "pod_scores":    security.get_pod_scores(),
        "cluster_score": security.get_cluster_score(),
    })


@app.route("/api/security/summary")
def security_summary():
    return jsonify(security.get_summary())


import requests as req_lib

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return jsonify({"error": "No Groq API key configured."}), 400

    # Convert Anthropic format to Groq/OpenAI format
    messages = data.get("messages", [])
    system = data.get("system", "")

    # Trim system prompt to avoid token limit issues
    system_trimmed = system[:2000] if system else ""

    resp = req_lib.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.1-8b-instant",
            "max_tokens": data.get("max_tokens", 600),
            "messages": [{"role": "system", "content": system_trimmed}] + messages if system_trimmed else messages,
        },
        timeout=30,
    )

    groq_data = resp.json()

    # Convert Groq response back to Anthropic format so frontend works without changes
    if resp.status_code == 200:
        text = groq_data["choices"][0]["message"]["content"]
        return jsonify({"content": [{"type": "text", "text": text}]}), 200
    else:
        error_msg = groq_data.get("error", {}).get("message", "Groq API error")
        return jsonify({"content": [{"type": "text", "text": f"⚠️ {error_msg}"}]}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"PodSight AI Collector starting on :{port}")
    print(f"Demo mode: {os.environ.get('DEMO_MODE', 'true')}")
    print(f"AI mode: {'enabled ✅' if os.environ.get('ANTHROPIC_API_KEY') else 'rule-based ❌ key not loaded'}")
    app.run(host="0.0.0.0", port=port, debug=False)
