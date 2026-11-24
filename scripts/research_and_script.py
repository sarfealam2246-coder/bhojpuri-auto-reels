import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WORK_DIR = ROOT / "work"
WORK_DIR.mkdir(parents=True, exist_ok=True)

MOODS = ["rangdari", "bewafai", "judai", "vafadari"]


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def parse_json_safe(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    return json.loads(cleaned)


def analyze_fb_page_reach(history: list) -> dict:
    page_id = os.getenv("FB_PAGE_ID", "").strip()
    token = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
    summary = {"best_mood": None, "notes": "Balanced high-intensity mood rotation."}
    if not page_id or not token:
        return summary
    try:
        r = requests.get(
            f"https://graph.facebook.com/v21.0/{page_id}/posts",
            params={"fields": "id,shares,likes.summary(true),comments.summary(true)", "limit": 20, "access_token": token},
            timeout=15,
        )
        if not r.ok:
            return summary
        mood_scores = {m: 0 for m in MOODS}
        for p in r.json().get("data", []):
            pid = p.get("id", "")
            likes = p.get("likes", {}).get("summary", {}).get("total_count", 0)
            comments = p.get("comments", {}).get("summary", {}).get("total_count", 0)
            shares = p.get("shares", {}).get("count", 0)
            score = likes + (comments * 2) + (shares * 3)
            for h in history:
                if pid and pid in str(h.get("fbPostUrl", "")):
                    m = h.get("mood")
                    if m in mood_scores:
                        mood_scores[m] += score
                    h["reachMetrics"] = {"views": max(likes * 12, score * 15), "likes": likes, "comments": comments, "shares": shares}
        best = max(mood_scores, key=lambda k: mood_scores[k])
        if mood_scores[best] > 0:
            summary["best_mood"] = best
            summary["notes"] = f"Top mood on your Page: {best} (score {mood_scores[best]})."
    except Exception:
        pass
    return summary


def pick_next_mood(history: list, reach_summary: dict) -> str:
    last_moods = [h.get("mood") for h in history[-3:] if h.get("mood")]
    candidates = [m for m in MOODS if m not in last_moods[-2:]] or MOODS
    best_mood = reach_summary.get("best_mood")
    if best_mood in candidates and random.random() < 0.45:
        return best_mood
    return random.choice(candidates)


def research_top_bhojpuri_video(channels: list, mood: str, used_urls: set) -> dict:
    queries = {
        "rangdari": "bhojpuri rangdari attitude dialogue status shorts",
        "bewafai": "bhojpuri bewafai sad shayari dialogue shorts",
        "judai": "bhojpuri judai dard bhara dialogue status shorts",
        "vafadari": "bhojpuri dosti yaari vafadari dialogue shorts",
    }
    matching = [c for c in channels if c.get("enabled", True) and c.get("category") == mood]
    chosen = random.choice(matching) if matching else {"name": "Bhojpuri Viral", "youtubeHandleOrUrl": queries[mood]}
    query = chosen.get("youtubeHandleOrUrl", queries[mood])
    search_target = query if query.startswith("http") else f"ytsearch6:{query}"

    best_entry = None
    try:
        res = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--dump-single-json", "--flat-playlist", "--no-warnings", search_target],
            capture_output=True, text=True, timeout=35,
        )
        if res.returncode == 0 and res.stdout.strip():
            entries = [e for e in (json.loads(res.stdout).get("entries") or []) if e and e.get("url") not in used_urls]
            entries.sort(key=lambda e: e.get("view_count") or 0, reverse=True)
            if entries:
                best_entry = entries[0]
    except Exception:
        best_entry = None

    if best_entry:
        vid_url = best_entry.get("url") or f"https://www.youtube.com/watch?v={best_entry.get('id', '')}"
        if not str(vid_url).startswith("http"):
            vid_url = f"https://www.youtube.com/watch?v={best_entry.get('id', '')}"
        views = best_entry.get("view_count") or 0
        return {
            "channelName": best_entry.get("uploader") or chosen.get("name", "Bhojpuri Creator"),
            "videoTitle": best_entry.get("title") or f"Viral {mood.title()} Dialogue",
            "videoUrl": vid_url,
            "viewsLabel": f"{views:,} views" if views else "Trending Bhojpuri Short",
        }
    return {
        "channelName": chosen.get("name", "Bhojpuri Trending"),
        "videoTitle": f"Viral Bhojpuri {mood.title()} Trend",
        "videoUrl": "https://www.youtube.com/results?search_query=" + query.replace(" ", "+"),
        "viewsLabel": "Live Topic Trend",
    }


def get_active_groq_models(groq_key: str) -> list:
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {groq_key}", "User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.ok:
            ids = [m["id"] for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")]
            chat_ids = [m for m in ids if not any(b in m.lower() for b in ["whisper", "guard", "tts", "orpheus", "playai", "safeguard"])]
            chat_ids.sort(key=lambda x: (0 if "llama" in x.lower() else 1, x))
            if chat_ids:
                return chat_ids[:6]
    except Exception:
        pass
    return ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


def get_active_gemini_models(gemini_key: str) -> list:
    try:
        r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.ok:
            models = [
                m["name"].replace("models/", "")
                for m in r.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", []) and "tts" not in m["name"].lower() and "image" not in m["name"].lower()
            ]
            models.sort(key=lambda x: (0 if "flash" in x.lower() else 1, x))
            if models:
                return models[:6]
    except Exception:
        pass
    return ["gemini-3.0-flash"]


def call_llm_auto_rotate(prompt: str) -> dict:
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    errors = []

    if groq_key:
        for model in get_active_groq_models(groq_key):
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "You are a viral Bhojpuri mass-dialogue Reel writer. Return ONLY valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.92,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=35,
                )
                if r.ok:
                    return parse_json_safe(r.json()["choices"][0]["message"]["content"])
                errors.append(f"Groq {model}: {r.status_code}")
            except Exception as exc:
                errors.append(f"Groq {model}: {exc}")

    if gemini_key:
        for model in get_active_gemini_models(gemini_key):
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}",
                    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                    json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.92}},
                    timeout=35,
                )
                if r.ok:
                    return parse_json_safe(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                errors.append(f"Gemini {model}: {r.status_code}")
            except Exception as exc:
                errors.append(f"Gemini {model}: {exc}")

    raise RuntimeError("LLM error: " + " | ".join(errors))


def main():
    slot = os.getenv("REEL_SLOT", "manual").strip() or "manual"
    config = load_json(DATA_DIR / "config.json", {})
    history = load_json(DATA_DIR / "history.json", [])

    reach_summary = analyze_fb_page_reach(history)
    mood = pick_next_mood(history, reach_summary)
    used_urls = {h.get("researchSource", {}).get("videoUrl", "") for h in history}
    research_source = research_top_bhojpuri_video(config.get("channels", []), mood, used_urls)

    recent_hooks = [f"- ({h.get('mood')}) {h.get('title')}: {h.get('scriptDialogue', '')[:80]}" for h in history[-20:]]
    recent_block = "\n".join(recent_hooks) if recent_hooks else "None yet."

    prompt = f"""
Write an ultra-viral, goosebumps-giving 30-to-40 second BHOJPURI Reel in mood: "{mood}" (NO comedy!).
Base trend: "{research_source['videoTitle']}" ({research_source['viewsLabel']}) from "{research_source['channelName']}".

STRICT RULES:
1. Language MUST be 100% pure, raw, hard-hitting BHOJPURI / Purvanchali (words like: हमरा, तोहरा, रउआ, बाटे, होई, औकात, जिगर, दगाबाज, बदला, यारी, ईमान). NO English words, NO stage directions like "hero laughs", NO character names before dialogue!
2. Break into 5 short, explosive punch-lines (5-7 seconds each). Scene 1 MUST hit hard in the very first second!
3. `subtitleText` MUST be the EXACT same Bhojpuri line in Devanagari as `dialogue` (NOT English!).
4. Each `imagePrompt` MUST describe a hyper-realistic, cinematic, dramatic Indian/Bihar/UP vertical 9:16 photo (e.g., lone man in rain under streetlight, intense angry eyes in dark jeep, broken heart sitting on railway track at dusk, royal village dabang entry in dusty sunset — realistic photography, 8k, no text, no blur).
5. Anti-repeat: Do NOT repeat anything from:
{recent_block}

Return strictly JSON:
{{
  "title": "Catchy Bhojpuri Title",
  "mood": "{mood}",
  "voiceStyle": "{'Aoede' if mood in ('bewafai','judai') else 'Charon'}",
  "gapAnalysis": ["flaw 1 & fix", "flaw 2 & fix", "flaw 3 & fix"],
  "scenes": [
    {{
      "sceneNumber": 1,
      "dialogue": "ठेठ भोजपुरी डायलॉग लाइन",
      "subtitleText": "ठेठ भोजपुरी डायलॉग लाइन",
      "imagePrompt": "Hyper-realistic dramatic cinematic vertical 9:16 photo..."
    }}
  ],
  "caption": "दमदार भोजपुरी/हिंदी कैप्शन + कमेंट सवाल",
  "hashtags": ["#BhojpuriDialogue", "#Rangdari", "#Bewafai", "#DesiJazbaat", "#BhojpuriReels", "#ViralReels"]
}}
"""
    plan = call_llm_auto_rotate(prompt)
    plan["id"] = f"reel_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    plan["createdAt"] = datetime.now(timezone.utc).isoformat()
    plan["slot"] = slot
    plan["mood"] = mood
    plan["researchSource"] = research_source
    plan["scriptDialogue"] = " ".join(s.get("dialogue", "") for s in plan.get("scenes", []))

    (WORK_DIR / "script_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Script ready: {plan['id']} ({mood})")


if __name__ == "__main__":
    main()
