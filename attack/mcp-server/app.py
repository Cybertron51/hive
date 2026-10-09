from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory stores keep the demo self-contained.
contexts = {
    "summarize_user_notes": "Default meeting notes: stay focused on user needs.",
    "classify_bug": "Bug queue triage instructions.",
}
tools = {}
files = {
    "sample_secret": {
        "content": "USER_API_KEY=PLACEHOLDER123",
        "metadata": {"owner": "demo-user", "created": "2024-01-01"},
    }
}


def log(event: str, detail: str = "") -> None:
    timestamp = datetime.utcnow().isoformat()
    print(f"{timestamp} [MCP] {event} {detail}".strip(), flush=True)


@app.before_request
def log_request() -> None:
    log("REQUEST", f"{request.method} {request.path}")


@app.route("/context", methods=["GET"])
def get_context():
    task = request.args.get("task", "")
    context = contexts.get(task, "No context stored for this task.")
    log("CONTEXT_SERVE", f"task={task}")
    return jsonify({"task": task, "context": context})


@app.route("/admin/contexts", methods=["POST"])
def upsert_context():
    data = request.get_json(force=True) or {}
    task = data.get("task")
    context = data.get("context", "")
    if not task:
        return jsonify({"error": "task is required"}), 400
    contexts[task] = context
    log("CONTEXT_UPDATE", f"task={task}")
    return jsonify({"status": "ok", "task": task})


@app.route("/tools", methods=["GET"])
def list_tools():
    return jsonify(list(tools.values()))


@app.route("/admin/registerTool", methods=["POST"])
def register_tool():
    data = request.get_json(force=True) or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400
    endpoint = data.get("endpoint") or f"/tool/{name}"
    description = data.get("description", "")
    tools[name] = {"name": name, "endpoint": endpoint, "description": description}
    log("TOOL_REGISTERED", f"{name} -> {endpoint}")
    return jsonify({"status": "registered", "tool": tools[name]})


@app.route("/files/<file_id>", methods=["GET"])
def fetch_file(file_id: str):
    record = files.get(file_id)
    if not record:
        return jsonify({"error": "file not found"}), 404
    log("FILE_READ", file_id)
    return jsonify({"file_id": file_id, "content": record["content"], "metadata": record.get("metadata", {})})


@app.route("/tool/<tool_name>", methods=["POST"])
def invoke_tool(tool_name: str):
    if tool_name not in tools:
        return jsonify({"error": "unknown tool"}), 404
    payload = request.get_json(force=True) or {}
    log("TOOL_INVOKE", f"{tool_name} payload={payload}")
    file_id = payload.get("file_id")
    file_blob = files.get(file_id) if file_id else None
    return jsonify({"tool": tool_name, "echo": payload, "file": file_blob})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
