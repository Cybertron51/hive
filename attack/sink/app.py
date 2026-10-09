import os
from datetime import datetime

from flask import Flask, jsonify, request

app = Flask(__name__)

LOG_PATH = "/data/received.log"
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
if not os.path.exists(LOG_PATH):
    open(LOG_PATH, "w", encoding="utf-8").close()


def append_log(message: str) -> None:
    timestamp = datetime.utcnow().isoformat()
    line = f"{timestamp} [SINK] {message}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


@app.route("/receive", methods=["POST"])
def receive():
    body = request.get_data(as_text=True)
    append_log(f"SINK RECEIVED: {body}")
    return jsonify({"status": "stored"}), 201


@app.route("/logs", methods=["GET"])
def logs():
    with open(LOG_PATH, "r", encoding="utf-8") as handle:
        entries = [line.rstrip("\n") for line in handle]
    return jsonify({"entries": entries})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
