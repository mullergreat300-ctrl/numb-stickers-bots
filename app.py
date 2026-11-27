"""
A-sticker WhatsApp bot - single self-contained service.

Flow:
  1. Meta calls GET  /webhook  -> we answer the verification challenge.
  2. User sends a VIDEO to the bot -> we download it and remember it for that user.
  3. User sends "A-sticker" (or the video caption is "A-sticker") ->
     we convert it to a silent animated WebP sticker + an OGG voice note
     and send both back via the WhatsApp Cloud API.

Env vars (set these on the host):
  WA_TOKEN            Permanent access token (System User)
  WA_PHONE_ID         Phone Number ID
  WA_VERIFY_TOKEN     Any secret string; must match what you paste in Meta
  WA_API_VERSION      optional, default v21.0
  PORT                optional, default 8080
"""
import os
import tempfile
import time
import httpx
from fastapi import FastAPI, Request, Response

import engine

WA_TOKEN = os.environ.get("WA_TOKEN", "")
WA_PHONE_ID = os.environ.get("WA_PHONE_ID", "")
WA_VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "change-me")
API_VERSION = os.environ.get("WA_API_VERSION", "v21.0")
GRAPH = f"https://graph.facebook.com/{API_VERSION}"

app = FastAPI()

# Last video media id per sender (in-memory; fine for a small bot).
_last_video: dict[str, dict] = {}
VIDEO_TTL = 15 * 60  # 15 min to run the command after sending the video

TRIGGER = "a-sticker"


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/webhook")
def verify(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == WA_VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    return Response(content="forbidden", status_code=403)


@app.post("/webhook")
async def receive(request: Request):
    body = await request.json()
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        messages = entry.get("messages") or []
        if messages:
            msg = messages[0]
            await handle_message(msg)
    except (KeyError, IndexError):
        pass
    # Always ack fast so Meta doesn't retry.
    return {"status": "ok"}


async def handle_message(msg: dict):
    sender = msg.get("from")
    mtype = msg.get("type")
    if not sender:
        return

    # 1) Video arrives -> remember it.
    if mtype == "video":
        media_id = msg["video"]["id"]
        caption = (msg["video"].get("caption") or "").strip().lower()
        _last_video[sender] = {"id": media_id, "ts": time.time()}
        if caption == TRIGGER:
            await run_conversion(sender, media_id)
        else:
            await send_text(sender, "Video received. Send *A-sticker* to turn it into a sticker.")
        return

    # 2) Command arrives -> convert the remembered video.
    if mtype == "text":
        text = (msg["text"]["body"] or "").strip().lower()
        if text == TRIGGER:
            rec = _last_video.get(sender)
            if rec and time.time() - rec["ts"] <= VIDEO_TTL:
                await run_conversion(sender, rec["id"])
            else:
                await send_text(sender, "Send me a video first, then type *A-sticker*.")


async def run_conversion(sender: str, media_id: str):
    try:
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "in.mp4")
            await download_media(media_id, video_path)
            res = engine.convert(video_path, d)
            if not res["sticker_ok"]:
                await send_text(sender, "Sorry, I couldn't build a sticker under 500KB from that clip.")
                return
            sticker_id = await upload_media(res["sticker"], "sticker", "image/webp")
            await send_sticker(sender, sticker_id)
            if res["audio"]:
                audio_id = await upload_media(res["audio"], "audio", "audio/ogg")
                await send_audio(sender, audio_id)
    except Exception as e:
        await send_text(sender, f"Conversion failed: {e}")


async def download_media(media_id: str, dest: str):
    headers = {"Authorization": f"Bearer {WA_TOKEN}"}
    async with httpx.AsyncClient(timeout=60) as c:
        meta = (await c.get(f"{GRAPH}/{media_id}", headers=headers)).json()
        url = meta["url"]
        r = await c.get(url, headers=headers)
        with open(dest, "wb") as f:
            f.write(r.content)


async def upload_media(path: str, kind: str, mime: str) -> str:
    headers = {"Authorization": f"Bearer {WA_TOKEN}"}
    async with httpx.AsyncClient(timeout=120) as c:
        with open(path, "rb") as f:
            files = {"file": (os.path.basename(path), f, mime)}
            data = {"messaging_product": "whatsapp", "type": kind}
            r = await c.post(f"{GRAPH}/{WA_PHONE_ID}/media", headers=headers, data=data, files=files)
            return r.json()["id"]


async def _send(payload: dict):
    headers = {"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as c:
        await c.post(f"{GRAPH}/{WA_PHONE_ID}/messages", headers=headers, json=payload)


async def send_text(to: str, body: str):
    await _send({"messaging_product": "whatsapp", "to": to, "type": "text",
                 "text": {"body": body}})


async def send_sticker(to: str, media_id: str):
    await _send({"messaging_product": "whatsapp", "to": to, "type": "sticker",
                 "sticker": {"id": media_id}})


async def send_audio(to: str, media_id: str):
    await _send({"messaging_product": "whatsapp", "to": to, "type": "audio",
                 "audio": {"id": media_id}})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
