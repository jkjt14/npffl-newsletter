import os, json, requests

def post_slack(text: str):
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url: return
    requests.post(url, data=json.dumps({"text": text}),
                  headers={"Content-Type":"application/json"}, timeout=15)

def mailchimp_send(subject: str, html: str):
    api_key = os.getenv("MAILCHIMP_API_KEY")
    dc = os.getenv("MAILCHIMP_SERVER_PREFIX")
    list_id = os.getenv("MAILCHIMP_LIST_ID")
    if not all([api_key, dc, list_id]): return
    base = f"https://{dc}.api.mailchimp.com/3.0"
    auth = ("anystring", api_key)
    camp = requests.post(f"{base}/campaigns", auth=auth, json={
        "type": "regular",
        "recipients": {"list_id": list_id},
        "settings": {
            "subject_line": subject,
            "title": subject,
            "from_name": "NPFFL Bot",
            "reply_to": "no-reply@example.com"
        }
    }, timeout=30).json()
    cid = camp.get("id")
    requests.put(f"{base}/campaigns/{cid}/content", auth=auth, json={"html": html}, timeout=30)
    requests.post(f"{base}/campaigns/{cid}/actions/send", auth=auth, timeout=30)
