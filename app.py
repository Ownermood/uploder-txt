import json
import os
from flask import Flask

app = Flask(__name__)


@app.route('/')
def hello_world():
    status_html = "<p style='color:orange'>⏳ Bot starting... refresh in 20s</p>"
    try:
        with open("/app/bot_status.json") as f:
            data = json.load(f)
        if data.get("connected"):
            status_html = (
                f"<div style='color:#0f0;font-size:20px'>"
                f"✅ <b>Bot is LIVE & connected!</b><br><br>"
                f"🤖 Username: <b>@{data.get('username')}</b><br>"
                f"🆔 Bot ID: <b>{data.get('id')}</b><br>"
                f"📛 Name: <b>{data.get('name')}</b><br>"
                f"🕒 Since: {data.get('time')}<br><br>"
                f"👉 Open <b>@{data.get('username')}</b> in Telegram and send /start"
                f"</div>"
            )
        else:
            status_html = (
                f"<div style='color:#f33;font-size:18px'>"
                f"❌ <b>Pyrogram NOT connected</b><br><br>"
                f"Error: <code>{data.get('error')}</code><br>"
                f"Time: {data.get('time')}"
                f"</div>"
            )
    except FileNotFoundError:
        status_html = "<p style='color:orange'>⏳ Bot still connecting (no status yet). Refresh in 20s.</p>"
    except Exception as e:
        status_html = f"<p style='color:#f33'>Status read error: {e}</p>"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Bot Status</title>
<meta http-equiv="refresh" content="15">
<style>body{{background:#111;color:#eee;font-family:sans-serif;text-align:center;padding:40px}}</style>
</head>
<body>
    <h2>🦅 Golden Eagle Bot — Health</h2>
    {status_html}
    <hr style="margin-top:40px;border-color:#333">
    <p style="color:#888">Powered By SAINI BOTS · auto-refresh 15s</p>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
