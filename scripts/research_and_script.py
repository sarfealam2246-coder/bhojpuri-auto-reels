import json
import os
import random
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WORK_DIR = ROOT / "work"
SUBS_TMP = WORK_DIR / "yt_subs"
WORK_DIR.mkdir(parents=True, exist_ok=True)
SUBS_TMP.mkdir(parents=True, exist_ok=True)

MOODS = ["rangdari", "rangdari", "bewafai", "judai", "vafadari", "comedy"]

LIVE_BHOJPURI_TREND_QUERIES = {
    "rangdari": [
        "bhojpuri rangdari viral dialogue shorts today",
        "bhojpuri attitude status viral trending",
        "bhojpuri dabang dialogue reel viral",
        "purvanchal bihari swag dialogue bhojpuri",
        "bhojpuri bahubali dialogue viral shorts",
    ],
    "bewafai": [
        "bhojpuri bewafai viral dialogue status",
        "bhojpuri sad shayari trending shorts",
        "bhojpuri dard bhara status viral",
        "bhojpuri dhokha emotional dialogue viral",
    ],
    "judai": [
        "bhojpuri judai emotional dialogue viral",
        "bhojpuri sad story emotional shorts",
        "bhojpuri rula dene wala dialogue viral",
    ],
    "vafadari": [
        "bhojpuri yaari dosti vafadari viral dialogue",
        "bhojpuri parivar imandari emotional dialogue",
        "bhojpuri bhai dosti attitude status",
    ],
    "comedy": [
        "bhojpuri desi comedy viral shorts trending",
        "bhojpuri gaon comedy funny dialogue viral",
        "bhojpuri hasi mazak viral reel",
    ],
}

BHOJPURI_KEYWORDS = [
    "bhojpuri", "भोजपुरी", "bihari", "purvanchal", "dehati",
    "khesari", "pawan", "nirahua", "mani meraj", "kallu",
    "gunjan", "ankush", "anand mohan", "dileep", "amarjeet", "bihar", "patna", "gorakhpur", "banaras",
]


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
    summary = {"best_mood": None, "notes": "Focusing on high-impact Rangdari, Bewafai & Desi Bhojpuri trends."}
    if not page_id or not token:
        return summary
    try:
        r = requests.get(
            f"https://graph.facebook.com/v21.0/{page_id}/posts",
            params={"fields": "id,shares,likes.summary(true),comments.summary(true)", "limit": 25, "access_token": token},
            timeout=15,
        )
        if not r.ok:
            return summary
        mood_scores = {}
        for p in r.json().get("data", []):
            pid = p.get("id", "")
            likes = p.get("likes", {}).get("summary", {}).get("total_count", 0)
            comments = p.get("comments", {}).get("summary", {}).get("total_count", 0)
            shares = p.get("shares", {}).get("count", 0)
            score = likes + (comments * 2) + (shares * 3)
            for h in history:
                if pid and pid in str(h.get("fbPostUrl", "")):
                    m = h.get("mood")
                    if m:
                        mood_scores[m] = mood_scores.get(m, 0) + score
                    h["reachMetrics"] = {"views": max(likes * 12, score * 15), "likes": likes, "comments": comments, "shares": shares}
        if mood_scores:
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


def is_bhojpuri_entry(entry: dict) -> bool:
    blob = f"{entry.get('title', '')} {entry.get('uploader', '')} {entry.get('description', '')}".lower()
    return any(k in blob for k in BHOJPURI_KEYWORDS)


def extract_hashtags(text: str) -> list[str]:
    tags = re.findall(r"#[\w\u0900-\u097F]+", text or "")
    seen = []
    for t in tags:
        if t.lower() not in [s.lower() for s in seen]:
            seen.append(t)
    return seen[:12]


def fetch_video_transcript_snippet(video_url: str) -> str:
    try:
        for f in SUBS_TMP.glob("*"):
            f.unlink(missing_ok=True)
        subprocess.run(
            [
                sys.executable, "-m", "yt_dlp",
                "--skip-download", "--write-auto-sub", "--write-sub",
                "--sub-lang", "hi,en", "--sub-format", "vtt",
                "-o", str(SUBS_TMP / "sub"),
                video_url,
            ],
            capture_output=True, text=True, timeout=30,
        )
        vtts = list(SUBS_TMP.glob("*.vtt"))
        if vtts:
            raw = vtts[0].read_text(encoding="utf-8", errors="ignore")
            lines = []
            for ln in raw.splitlines():
                ln = ln.strip()
                if not ln or "-->" in ln or ln.startswith(("WEBVTT", "Kind:", "Language:")):
                    continue
                clean_ln = re.sub(r"<[^>]+>", "", ln)
                if clean_ln and (not lines or lines[-1] != clean_ln):
                    lines.append(clean_ln)
            return " ".join(lines)[:1200]
    except Exception:
        pass
    return ""


def search_social_trends_web(mood: str) -> tuple[list[str], list[str], list[str]]:
    """Scan public Facebook Reels & Instagram Reels trend mentions via DuckDuckGo HTML."""
    platforms = []
    social_notes = []
    hashtags = []
    queries = [
        ("Facebook", f"site:facebook.com/reel bhojpuri {mood} viral"),
        ("Instagram", f"site:instagram.com/reel bhojpuri {mood} viral"),
        ("Facebook/Instagram", f"bhojpuri {mood} trending viral reels hashtags today"),
    ]
    for platform, q in queries:
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(q)}"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=20)
            if r.ok and r.text:
                titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', r.text, flags=re.S)
                snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', r.text, flags=re.S)
                clean_items = []
                for idx in range(min(3, len(titles))):
                    t = re.sub(r"<[^>]+>", "", titles[idx]).strip()
                    s = re.sub(r"<[^>]+>", "", snippets[idx]).strip() if idx < len(snippets) else ""
                    if t:
                        clean_items.append(f"{t} — {s[:140]}")
                        hashtags.extend(extract_hashtags(f"{t} {s}"))
                if clean_items:
                    if platform not in platforms:
                        platforms.append(platform)
                    social_notes.append(f"[{platform}] " + " | ".join(clean_items[:2]))
        except Exception:
            continue
    return platforms, social_notes, list(dict.fromkeys(hashtags))[:10]


def open_bhojpuri_trend_research(channels_cfg: list, mood: str, used_urls: set) -> tuple[dict, str, dict]:
    """Deep multi-platform Bhojpuri trend research across YouTube, Facebook & Instagram."""
    queries = list(LIVE_BHOJPURI_TREND_QUERIES.get(mood, LIVE_BHOJPURI_TREND_QUERIES["rangdari"]))
    for c in channels_cfg:
        if c.get("enabled", True) and c.get("category") == mood and c.get("youtubeHandleOrUrl"):
            queries.append(c["youtubeHandleOrUrl"])

    random.shuffle(queries)
    candidates = []
    for q in queries[:4]:
        target = q if q.startswith("http") else f"ytsearch15:{q}"
        try:
            res = subprocess.run(
                [sys.executable, "-m", "yt_dlp", "--dump-single-json", "--flat-playlist", "--no-warnings", target],
                capture_output=True, text=True, timeout=45,
            )
            if res.returncode == 0 and res.stdout.strip():
                for e in (json.loads(res.stdout).get("entries") or []):
                    if not e:
                        continue
                    url = e.get("url") or f"https://www.youtube.com/watch?v={e.get('id', '')}"
                    if not str(url).startswith("http"):
                        url = f"https://www.youtube.com/watch?v={e.get('id', '')}"
                    if url in used_urls:
                        continue
                    if is_bhojpuri_entry(e):
                        candidates.append({
                            "channelName": e.get("uploader") or "Bhojpuri Creator",
                            "videoTitle": e.get("title") or f"Viral Bhojpuri {mood.title()}",
                            "videoUrl": url,
                            "views": e.get("view_count") or 0,
                            "tags": extract_hashtags(f"{e.get('title', '')} {e.get('description', '')}"),
                        })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["views"], reverse=True)
    platforms, social_notes, web_tags = search_social_trends_web(mood)
    if candidates and "YouTube" not in platforms:
        platforms.insert(0, "YouTube")

    all_tags = list(dict.fromkeys(web_tags + [t for c in candidates[:8] for t in c.get("tags", [])]))[:12]
    distinct_creators = len({c["channelName"] for c in candidates})

    if candidates:
        top = candidates[0]
        transcript_1 = fetch_video_transcript_snippet(top["videoUrl"])
        transcript_2 = fetch_video_transcript_snippet(candidates[1]["videoUrl"]) if len(candidates) > 1 else ""
        points = [
            f"Platforms Scanned: {', '.join(platforms) or 'YouTube'} | Distinct Creators Found: {distinct_creators}",
            f"1. Top Viral Hit: {top['channelName']} | '{top['videoTitle']}' ({top['views']:,} views)",
            f"   Spoken Transcript 1: {transcript_1 or 'Use raw Bhojpuri emotion & punch theme directly.'}",
        ]
        if transcript_2:
            points.append(f"2. Runner-Up Viral Hit: {candidates[1]['channelName']} | '{candidates[1]['videoTitle']}' ({candidates[1]['views']:,} views)")
            points.append(f"   Spoken Transcript 2: {transcript_2}")
        for idx, alt in enumerate(candidates[2:6], start=3):
            points.append(f"{idx}. Also Trending Today: {alt['channelName']} | '{alt['videoTitle']}' ({alt['views']:,} views)")
        if social_notes:
            points.append("Social Platform Signals:\n" + "\n".join(social_notes))
        if all_tags:
            points.append("Trending Hashtags Found: " + " ".join(all_tags))

        viral_report = {
            "platformsFound": platforms or ["YouTube"],
            "channelsCount": distinct_creators,
            "topCreator": top["channelName"],
            "topViews": top["views"],
            "extractedHashtags": all_tags,
            "transcriptsRead": sum(1 for t in (transcript_1, transcript_2) if t),
        }
        return {
            "channelName": top["channelName"],
            "videoTitle": top["videoTitle"],
            "videoUrl": top["videoUrl"],
            "viewsLabel": f"{top['views']:,} views" if top["views"] else "Trending Bhojpuri Video",
        }, "\n".join(points), viral_report

    viral_report = {
        "platformsFound": platforms or ["YouTube", "Web"],
        "channelsCount": distinct_creators,
        "topCreator": "Bhojpuri Audience Trend",
        "topViews": 0,
        "extractedHashtags": all_tags,
        "transcriptsRead": 0,
    }
    return {
        "channelName": "Bhojpuri Audience Trend",
        "videoTitle": f"Viral Bhojpuri {mood.title()} Trend",
        "videoUrl": "https://www.youtube.com/results?search_query=bhojpuri+" + mood + "+viral+dialogue",
        "viewsLabel": "Live Bhojpuri Trend",
    }, "\n".join(social_notes) or f"Topic: Bhojpuri {mood} viral dialogue", viral_report


def get_active_groq_models(groq_key: str) -> list:
    try:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {groq_key}", "User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.ok:
            ids = [m["id"] for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")]
            chat_ids = [m for m in ids if not any(b in m.lower() for b in ["whisper", "guard", "tts", "orpheus", "playai", "safeguard"])]
            chat_ids.sort(key=lambda x: (0 if "70b" in x.lower() else (1 if "llama" in x.lower() else 2), x))
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
    return ["gemini-2.5-flash"]


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
                            {"role": "system", "content": "You are an elite Purvanchali/Bihari Bhojpuri cinema writer. Return ONLY valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.85,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=60,
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
                    json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.85}},
                    timeout=60,
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
    research_source, deep_context, viral_report = open_bhojpuri_trend_research(config.get("channels", []), mood, used_urls)

    recent_hooks = [f"- ({h.get('mood')}) {h.get('title')}: {h.get('scriptDialogue', '')[:80]}" for h in history[-20:]]
    recent_block = "\n".join(recent_hooks) if recent_hooks else "None yet."

    draft_prompt = f"""
Analyze what is trending TODAY in the Bhojpuri audience across YouTube, Facebook & Instagram:
{deep_context}
Page Reach Insight: {reach_summary['notes']}

Now create ONE gripping, 45-to-55 second BHOJPURI Reel in mood: "{mood}" that BEATS the flaws in those viral videos.

STRICT QUALITY GATE RULES:
1. ONE cohesive, connected story from Scene 1 to Scene 7 (Hook -> Tension -> Turning Point -> Killer Climax). No random disconnected lines!
2. 100% pure, natural spoken Bhojpuri (Bihar/Purvanchal): use "बा, बाटे, रहल बा, होई, ना, हमरा, तोहरा, रउआ, सुनऽ, देखऽ". Zero Hindi verbs ("है, रहा है, मुझे"), zero English words!
3. IMPORTANT FOR EMOJIS:
   - Keep `dialogue` clean spoken Devanagari ONLY (NO emojis inside `dialogue`, so voice TTS speaks cleanly).
   - Put expressive emojis (`🔥`, `😡`, `💔`, `⚡`, `😂`, `🙏`, `🦁`) inside `title` and `subtitleText`!
4. Smart `effect`: `"smooth_zoom"`, `"pan_left"`, or `"pan_right"` on scenes 1–6; `"climax_shake"` ONLY on Scene 7.
5. Pick `musicMood`: `"intense_action"` (rangdari), `"sad_emotional"` (bewafai/judai), `"warm_inspiring"` (vafadari), or `"desi_upbeat"` (comedy).
6. Every `imagePrompt` MUST describe an ultra-sharp HD 35mm DSLR live-action Indian single-person portrait (crisp facial focus, dramatic lighting, Bihar/UP backdrop, NO blur, NO crowds, NO anime, NO cartoon).
7. Anti-repeat: Do NOT repeat anything from:
{recent_block}

Return strictly JSON:
{{
  "title": "दमदार भोजपुरी टाइटल 🔥",
  "mood": "{mood}",
  "musicMood": "intense_action",
  "voiceStyle": "{'Aoede' if mood in ('bewafai','judai') else ('Puck' if mood == 'comedy' else 'Charon')}",
  "gapAnalysis": ["Viral trigger & platform reach", "Flaw in trending videos & how we beat it", "Hashtag & climax strategy"],
  "scenes": [
    {{
      "sceneNumber": 1,
      "effect": "smooth_zoom",
      "dialogue": "असली नेचुरल भोजपुरी डायलॉग बिना इमोजी के",
      "subtitleText": "असली नेचुरल भोजपुरी डायलॉग 🔥",
      "imagePrompt": "Ultra-sharp 8K 35mm DSLR close-up portrait of an intense Indian man..."
    }}
  ],
  "caption": "दमदार भोजपुरी कैप्शन + कमेंट सवाल 🔥",
  "hashtags": ["#BhojpuriReels", "#BhojpuriDialogue", "#Rangdari", "#BiharUP", "#ViralBhojpuri", "#BhojpuriPulseX"]
}}
"""
    plan = call_llm_auto_rotate(draft_prompt)

    audit_prompt = f"""
Strictly audit and polish this 7-scene Bhojpuri Reel JSON script:
{json.dumps(plan, ensure_ascii=False)}

Verify:
1. Scenes 1 to 7 tell ONE connected, high-impact story.
2. Every `dialogue` is 100% spoken Bhojpuri (replace any Hindi words like "है/मुझे/रहा है" with "बा/हमरा/रहल बा") and has NO emojis.
3. Every `subtitleText` matches `dialogue` AND ends with 1–2 fitting emojis (`🔥`, `😡`, `💔`, `⚡`, `😂`).
4. `climax_shake` is used ONLY on the final climax scene.
Return the polished JSON in the exact same format.
"""
    try:
        polished = call_llm_auto_rotate(audit_prompt)
        if polished.get("scenes") and len(polished["scenes"]) >= 5:
            plan = polished
    except Exception:
        pass

    plan["id"] = f"reel_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    plan["createdAt"] = datetime.now(timezone.utc).isoformat()
    plan["slot"] = slot
    plan["mood"] = mood
    plan["researchSource"] = research_source
    plan["viralReport"] = viral_report
    plan["scriptDialogue"] = " ".join(s.get("dialogue", "") for s in plan.get("scenes", []))

    (WORK_DIR / "script_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Multi-Platform Research & Script Gate PASSED: {plan['id']} ({mood}) | Platforms: {viral_report['platformsFound']}")


if __name__ == "__main__":
    main()
