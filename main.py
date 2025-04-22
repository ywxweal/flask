from flask import Flask, request, Response
import requests
import time
import threading
import uuid

app = Flask(__name__)
webhook_queue = {}
lock = threading.Lock()

def heartbeat():
    while True:
        now = time.time()
        to_remove = []

        with lock:
            for qid, item in list(webhook_queue.items()):
                if item['retry_after'] <= now:
                    try:
                        response = requests.post(item['webhook_url'], json=item['payload'])
                        if response.status_code != 429:
                            print(f"[{qid}] Sent successfully.")
                            to_remove.append(qid)
                        else:
                            retry_after = response.json().get("retry_after", 1)
                            item['retry_after'] = now + retry_after
                            print(f"[{qid}] Still rate limited. Retrying in {retry_after}s.")
                    except Exception as e:
                        print(f"[{qid}] Error sending webhook: {e}")
                        to_remove.append(qid)

            for qid in to_remove:
                webhook_queue.pop(qid)

        time.sleep(1)

@app.route('/api/<path:subpath>', methods=['POST'])
def queue_webhook(subpath):
    body = request.get_json(silent=True)
    webhook_url = f"https://discord.com/api/{subpath}"
    now = time.time()

    try:
        response = requests.post(webhook_url, json=body)
        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 1)
            qid = str(uuid.uuid4())
            with lock:
                webhook_queue[qid] = {
                    "webhook_url": webhook_url,
                    "payload": body,
                    "retry_after": now + retry_after
                }
            print(f"[{qid}] Rate limited. Queued for retry in {retry_after}s.")
            return ('', 204)

        elif response.status_code == 204:
            return ('', 204)

        else:
            return Response(response.content, status=response.status_code, headers=dict(response.headers))

    except Exception as e:
        print(f"[Error] {e}")
        return Response(f"Error: {e}", status=500)

if __name__ == '__main__':
    print("🚀 Starting heartbeat thread...")
    threading.Thread(target=heartbeat, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
