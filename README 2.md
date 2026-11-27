# A-sticker — WhatsApp Video-to-Sticker Bot

Send the bot a video, type **A-sticker**, and it replies with:
- a real **animated sticker** (silent WebP, 512×512, ≤3s, ≤500KB), and
- the clip's **audio** as a separate voice note.

> Note: WhatsApp stickers cannot carry sound. That's a WhatsApp format limit, not a bug.
> So the sound is delivered as a separate voice note right after the sticker.

## What's in here
- `engine.py` — the conversion core (ffmpeg): video → sticker.webp + audio.ogg
- `app.py` — the webhook + WhatsApp Cloud API sender (FastAPI)
- `requirements.txt`, `Dockerfile` — deployable as-is

## Deploy (5 minutes, Railway shown — Render/Fly work the same)
1. Push this folder to a GitHub repo.
2. On **railway.app** → New Project → Deploy from repo. It detects the `Dockerfile` and builds (ffmpeg included).
3. Add environment variables in the Railway dashboard:
   - `WA_TOKEN` — your permanent System User access token
   - `WA_PHONE_ID` — the Phone Number ID
   - `WA_VERIFY_TOKEN` — any secret string you choose (e.g. `asticker-7f3a9`)
4. Copy the public URL Railway gives you, e.g. `https://asticker-production.up.railway.app`.

## Wire it to Meta (WhatsApp Manager)
1. **WhatsApp Manager → Configuration → Webhook → Edit**
2. Callback URL: `https://<your-host>/webhook`
3. Verify token: the exact `WA_VERIFY_TOKEN` you set above
4. Click **Verify and save**, then **subscribe** to the `messages` field.
5. Add your business number and use the `wa.me/<number>` link as the bot link.

## Local test (no WhatsApp needed)
```bash
pip install -r requirements.txt
uvicorn app:app --port 8080
# GET http://localhost:8080/webhook?hub.mode=subscribe&hub.verify_token=change-me&hub.challenge=hi
```

## How a user uses it
1. Opens `wa.me/<your-number>` → starts chat
2. Sends a video
3. Types **A-sticker** → gets the sticker + audio
   (or sends the video with the caption `A-sticker`)
