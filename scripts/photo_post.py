import base64
import json
import os
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WORK_DIR = ROOT / "work"
WORK_DIR.mkdir(parents=True, exist_ok=True)


def generate_quote_via_llm() -> dict:
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    prompt = (
        "Write 1 short powerful Bhojpuri Shayari or Desi Life Thought (2 lines max) for a Facebook Page Photo Post, "
        "plus an engaging Hindi/Bhojpuri caption asking audience a question, and 5 hashtags. "
        'Return JSON: {"quoteText": "...", "imagePrompt": "...", "caption": "...", "hashtags": ["#Bhojpuri", ...]}'
    )
    if groq_key:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )
            if r.ok:
                return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception:
            pass
    if gemini_key:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=30,
            )
            if r.ok:
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except Exception:
            pass
    return {
        "quoteText": "Apna dum par jeena sikho, duniya khud jhuk jaayi.",
        "imagePrompt": "Warm golden sunset over rural Bihar village road, cinematic",
        "caption": "Sach baat ba ki na? Comment me batai!",
        "hashtags": ["#BhojpuriShayari", "#DesiThought", "#Bihar", "#UP", "#ViralPost"],
    }


def render_photo(quote_text: str, image_prompt: str, out_path: Path):
    acc_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    img = None
    if acc_id and token:
        try:
            r = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"prompt": f"{image_prompt}, no text, warm dramatic lighting", "num_steps": 6},
                timeout=45,
            )
            if r.ok and r.json().get("result", {}).get("image"):
                raw = WORK_DIR / "raw_photo.png"
                raw.write_bytes(base64.b64decode(r.json()["result"]["image"]))
                img = Image.open(raw).convert("RGB").resize((1080, 1080), Image.Resampling.LANCZOS)
        except Exception:
            img = None

    if img is None:
        img = Image.new("RGB", (1080, 1080), (24, 119, 242))

    overlay = Image.new("RGBA", (1080, 1080), (0, 0, 0, 110))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    wrapped = textwrap.fill(quote_text, width=28)
    draw.rectangle([(60, 360), (1020, 720)], outline=(255, 255, 255), width=4)
    draw.multiline_text((540, 540), wrapped, fill=(255, 255, 255), font=font, anchor="mm", align="center")
    img.save(out_path, quality=92)


def main():
    data = generate_quote_via_llm()
    photo_path = WORK_DIR / "photo_post.jpg"
    render_photo(data["quoteText"], data.get("imagePrompt", ""), photo_path)

    page_id = os.getenv("FB_PAGE_ID", "").strip()
    token = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
    fb_ok = False
    fb_url = ""
    fb_err = ""

    if page_id and token:
        try:
            caption = f"{data['caption']}\n\n{' '.join(data.get('hashtags', []))}"
            with open(photo_path, "rb") as f:
                r = requests.post(
                    f"https://graph.facebook.com/v21.0/{page_id}/photos",
                    data={"caption": caption, "access_token": token},
                    files={"source": f},
                    timeout=45,
                )
            if r.ok:
                fb_ok = True
                fb_url = f"https://www.facebook.com/{r.json().get('post_id', '')}"
            else:
                fb_err = r.text
        except Exception as exc:
            fb_err = str(exc)
    else:
        fb_err = "FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN not set."

    hist_file = DATA_DIR / "photo_history.json"
    history = json.loads(hist_file.read_text(encoding="utf-8")) if hist_file.exists() else []
    history.append({
        "id": f"photo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "quoteText": data["quoteText"],
        "caption": data["caption"],
        "hashtags": data.get("hashtags", []),
        "fbPublished": fb_ok,
        "fbPostUrl": fb_url or None,
        **({"error": fb_err} if fb_err else {}),
    })
    hist_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Photo post complete (fb_ok={fb_ok})")


if __name__ == "__main__":
    main()
