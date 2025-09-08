# src/post_outputs.py
from __future__ import annotations
import os, sys, json, time
from typing import Optional
import requests

def post_to_slack(text: str) -> None:
    url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not url: 
        print("[post_outputs] Slack webhook not set; skipping.", file=sys.stderr)
        return
    payload = {"text": text}
    r = requests.post(url, data=json.dumps(payload), headers={"Content-Type":"application/json"}, timeout=20)
    try:
        r.raise_for_status()
        print("[post_outputs] Posted to Slack.")
    except Exception as e:
        print(f"[post_outputs] Slack error: {e} {r.text}", file=sys.stderr)

# Minimal Mailchimp sender (create campaign -> set content -> send)
def mailchimp_send(subject: str, html: str) -> None:
    api_key = os.getenv("MC_API_KEY", "")
    dc = os.getenv("MC_SERVER_PREFIX", "")  # e.g., us21
    list_id = os.getenv("MC_LIST_ID", "")
    if not (api_key and dc and list_id):
        print("[post_outputs] Mailchimp not configured; skipping.", file=sys.stderr)
        return
    auth = ("anystring", api_key)
    base = f"https://{dc}.api.mailchimp.com/3.0"

    # 1) create campaign
    camp = {
        "type": "regular",
        "recipients": {"list_id": list_id},
        "settings": {
            "subject_line": subject,
            "title": f"{subject} {int(time.time())}",
            "from_name": "NPFFL",
            "reply_to": "no-reply@example.com",
        },
    }
    r = requests.post(f"{base}/campaigns", auth=auth, json=camp, timeout=30)
    r.raise_for_status()
    cid = r.json()["id"]

    # 2) set content
    r = requests.put(f"{base}/campaigns/{cid}/content", auth=auth, json={"html": html}, timeout=30)
    r.raise_for_status()

    # 3) send
    r = requests.post(f"{base}/campaigns/{cid}/actions/send", auth=auth, timeout=30)
    r.raise_for_status()
    print("[post_outputs] Mailchimp campaign sent.")
