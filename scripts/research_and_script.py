import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WORK_DIR = ROOT / "work"
WORK_DIR.mkdir(parents=True, exist_ok=True)

MOODS = ["rangdari", "bewafai", "comedy", "vafadari", "judai"]


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def analyze_fb_page_reach(history: list) -> dict:
    page_id = os.getenv("FB_PAGE_ID", "").strip()
    token = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
    summary = {"best_mood": None, "notes": "New page or no reach data yet; using balanced rotation."}
    if not page_id or not token:
        return summary

    try:
        url = f"https://graph.facebook.com/v21.0/{page_id}/posts"
        params = {
            "fields": "id,message,created_time,shares,likes.summary(true),comments.summary(true)",
            "limit": 20,
            "access_token": token,
        }
        r = requests.get(url, params=params, timeout=15)
        if not r.ok:
            return summary
        posts = r.json().get("data", [])
        mood_scores = {m: 0 for m in MOODS}
        for p in posts:
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
                    h["reachMetrics"] = {
                        "views": max(likes * 12, score * 15),
                        "likes": likes,
                        "comments": comments,
                        "shares": shares,
                    }
        best = max(mood_scores, key=lambda k: mood_scores[k])
        if mood_scores[best] > 0:
            summary["best_mood"] = best
            summary["notes"] = f"Top performing mood on your FB Page: {best} (engagement score {mood_scores[best]})."
    except Exception as exc:
        summary["notes"] = f"Reach check skipped safely: {exc}"
    return summary


def pick_next_mood(history: list, reach_summary: dict) -> str:
    last_moods = [h.get("mood") for h in history[-3:] if h.get("mood")]
    candidates = [m for m in MOODS if m not in last_moods[-2:]] or MOODS
    best_mood = reach_summary.get("best_mood")
    if best_mood in candidates and random.random() < 0.45:
        return best_mood
    return random.choice(candidates)


def research_top_bhojpuri_video(channels: list, mood: str, used_urls: set) -> dict:
    matching = [c for c in channels if c.get("enabled", True) and c.get("category") == mood]
    pool = matching if matching else [c for c in channels if c.get("enabled", True)]
    if not pool:
        pool = [{"name": "Bhojpuri Viral", "youtubeHandleOrUrl": f"bhojpuri {mood} dialogue shorts"}]

    chosen = random.choice(pool)
    query = chosen.get("youtubeHandleOrUrl", f"bhojpuri {mood} dialogue shorts")
    search_target = query if query.startswith("http") else f"ytsearch6:{query}"

    best_entry = None
    try:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-single-json",
            "--flat-playlist",
            "--no-warnings",
            search_target,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            entries = data.get("entries", []) or []
            entries = [e for e in entries if e and e.get("url") not in used_urls]
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
        views_label = f"{views:,} views" if views else "Trending Bhojpuri Short"
        return {
            "channelName": best_entry.get("uploader") or chosen.get("name", "Bhojpuri Creator"),
            "videoTitle": best_entry.get("title") or f"Trending {mood.title()} Dialogue",
            "videoUrl": vid_url,
            "viewsLabel": views_label,
        }

    return {
        "channelName": chosen.get("name", "Bhojpuri Trending"),
        "videoTitle": f"Viral Bhojpuri {mood.title()} Trend",
        "videoUrl": "https://www.youtube.com/results?search_query=" + query.replace(" ", "+"),
        "viewsLabel": "Live Topic Trend",
    }


def call_llm_auto_rotate(prompt: str) -> dict:
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if groq_key:
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "You are a viral Bhojpuri Reels scriptwriter. Return ONLY valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.9,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=35,
                )
                if r.ok:
                    content = r.json()["choices"][0]["message"]["content"]
                    return json.loads(content)
            except Exception:
                continue

    if gemini_key:
        for model in ["gemini-2.5-flash", "gemini-2.0-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                r = requests.post(
                    url,
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
                    },
                    timeout=35,
                )
                if r.ok:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text)
            except Exception:
                continue

    raise RuntimeError("No active Groq or Gemini API key succeeded.")


def main():
    slot = os.getenv("REEL_SLOT", "manual").strip() or "manual"
    config = load_json(DATA_DIR / "config.json", {})
    history = load_json(DATA_DIR / "history.json", [])

    reach_summary = analyze_fb_page_reach(history)
    mood = pick_next_mood(history, reach_summary)

    used_urls = {h.get("researchSource", {}).get("videoUrl", "") for h in history}
    research_source = research_top_bhojpuri_video(config.get("channels", []), mood, used_urls)

    recent_hooks = [f"- ({h.get('mood')}) {h.get('title')}: {h.get('scriptDialogue', '')[:90]}" for h in history[-20:]]
    recent_block = "\n".join(recent_hooks) if recent_hooks else "None yet."

    prompt = f"""
Create a 100% ORIGINAL, viral 35-to-50 second Bhojpuri Reel script in mood: "{mood}".
Reference trending video to beat: "{research_source['videoTitle']}" ({research_source['viewsLabel']}) from "{research_source['channelName']}".
Facebook Page Reach Insight: {reach_summary['notes']}

STRICT ANTI-REPEAT RULE — DO NOT repeat or copy any story, character name, or dialogue from these recent reels:
{recent_block}

Requirements:
1. Perform a 10M->50M Viral Gap Analysis: list 3 specific flaws in typical viral videos of this topic and how this script improves the 0-2s hook, emotional/rangdari twist, and ending punch.
2. Write natural, hard-hitting Bhojpuri dialogue (Devanagari or Hinglish mix that reads super natural in Indian voice) broken into 5 scenes (each scene 6-9 seconds, total ~40 seconds).
3. Each scene must have a rich, watermark-free vertical 9:16 visual prompt in English for Flux image generation (cinematic Indian/Bihar/UP rural or urban atmosphere, expressive lighting, no text in image).
4. Provide a catchy Facebook Reel caption in Hindi/Bhojpuri + 6 viral hashtags.

Return strictly this JSON structure:
{{
  "title": "Short catchy title",
  "mood": "{mood}",
  "voiceStyle": "Charon" or "Puck" or "Aoede",
  "gapAnalysis": ["bullet 1", "bullet 2", "bullet 3"],
  "scenes": [
    {{
      "sceneNumber": 1,
      "dialogue": "Bhojpuri dialogue line for this scene",
      "subtitleText": "Short punchy subtitle text",
      "imagePrompt": "Cinematic 9:16 vertical scene prompt in English, no text, no watermark"
    }}
  ],
  "caption": "Engaging Facebook Reel caption with question hook",
  "hashtags": ["#BhojpuriReels", "#BhojpuriDialogue", "#DesiSwag", "#ViralReels", "#Bihar", "#UP"]
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
    # Save updated reach metrics back to history
    (DATA_DIR / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Script generated cleanly: {plan['id']} ({mood})")


if __name__ == "__main__":
    main()
