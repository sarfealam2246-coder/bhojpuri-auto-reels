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
SUBS_TMP = WORK_DIR / "yt_subs"
WORK_DIR.mkdir(parents=True, exist_ok=True)
SUBS_TMP.mkdir(parents=True, exist_ok=True)

MOODS = ["rangdari", "bewafai", "judai", "vafadari", "comedy"]

BHOJPURI_CHANNELS = {
    "rangdari": [
        ("B4U Bhojpuri", "B4U Bhojpuri rangdari action dialogue shorts"),
        ("Khesari Music World", "Khesari Lal Yadav attitude dialogue bhojpuri shorts"),
        ("Amarjeet Akela", "Amarjeet Akela rangdari bhojpuri dialogue status"),
        ("Worldwide Records Bhojpuri", "Worldwide Records Bhojpuri dabang movie dialogue"),
    ],
    "bewafai": [
        ("Ankush Raja Official", "Ankush Raja bewafai sad bhojpuri dialogue status"),
        ("T-Series Hamaar Bhojpuri", "T-Series Hamaar Bhojpuri bewafai dard dialogue"),
        ("Gunjan Singh", "Gunjan Singh bhojpuri sad bewafai shayari status"),
        ("RJ Sadaf Bhojpuri", "RJ Sadaf bhojpuri bewafai shayari"),
    ],
    "judai": [
        ("Wave Music Bhojpuri", "Wave Music bhojpuri judai emotional dialogue status"),
        ("Saregama Hum Bhojpuri", "Saregama Hum Bhojpuri emotional sad dialogue"),
        ("Nirahua Music World", "Nirahua emotional judai bhojpuri movie scene"),
    ],
    "vafadari": [
        ("Nirahua Music World", "Nirahua bhojpuri dosti yaari vafadari dialogue"),
        ("B4U Bhojpuri", "B4U Bhojpuri imandari parivar emotional dialogue"),
        ("Pawan Singh Official", "Pawan Singh bhojpuri yaari vafadari dialogue"),
    ],
    "comedy": [
        ("Mani Meraj Vines", "Mani Meraj Vines bhojpuri comedy shorts"),
        ("Anand Mohan Comedy", "Anand Mohan bhojpuri desi comedy scene"),
        ("Dileep Vines", "Dileep Vines bhojpuri gaon comedy"),
    ],
}

BHOJPURI_KEYWORDS = [
    "bhojpuri", "भोजपुरी", "bihari", "purvanchal", "dehati",
    "khesari", "pawan", "nirahua", "mani meraj", "kallu",
    "gunjan", "ankush", "anand mohan", "dileep vines", "b4u", "amarjeet akela",
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
    summary = {"best_mood": None, "notes": "New page: balancing Rangdari, Bewafai, Judai, Vafadari & Desi Comedy."}
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
    if best_mood in candidates and random.random() < 0.40:
        return best_mood
    return random.choice(candidates)


def is_bhojpuri_entry(entry: dict) -> bool:
    blob = f"{entry.get('title', '')} {entry.get('uploader', '')} {entry.get('description', '')}".lower()
    return any(k in blob for k in BHOJPURI_KEYWORDS)


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
            capture_output=True, text=True, timeout=20,
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


def deep_research_bhojpuri(channels_cfg: list, mood: str, used_urls: set) -> tuple[dict, str]:
    pool = list(BHOJPURI_CHANNELS.get(mood, []))
    for c in channels_cfg:
        if c.get("enabled", True) and c.get("category") == mood:
            pool.append((c.get("name", "Bhojpuri Channel"), c.get("youtubeHandleOrUrl", "")))

    random.shuffle(pool)
    candidates = []
    for ch_name, query in pool[:3]:
        if not query:
            continue
        target = query if query.startswith("http") else f"ytsearch8:{query}"
        try:
            res = subprocess.run(
                [sys.executable, "-m", "yt_dlp", "--dump-single-json", "--flat-playlist", "--no-warnings", target],
                capture_output=True, text=True, timeout=25,
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
                            "channelName": e.get("uploader") or ch_name,
                            "videoTitle": e.get("title") or f"Viral Bhojpuri {mood.title()}",
                            "videoUrl": url,
                            "views": e.get("view_count") or 0,
                        })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["views"], reverse=True)
    if candidates:
        top = candidates[0]
        transcript = fetch_video_transcript_snippet(top["videoUrl"])
        context_lines = [
            f"- Top Video: {top['channelName']} | {top['videoTitle']} ({top['views']:,} views)",
            f"- Real Spoken Transcript/Lyrics: {transcript or 'Use title & Bhojpuri emotion theme directly.'}",
        ]
        for alt in candidates[1:3]:
            context_lines.append(f"- Runner-up: {alt['channelName']} | {alt['videoTitle']} ({alt['views']:,} views)")
        return {
            "channelName": top["channelName"],
            "videoTitle": top["videoTitle"],
            "videoUrl": top["videoUrl"],
            "viewsLabel": f"{top['views']:,} views" if top["views"] else "Trending Bhojpuri Video",
        }, "\n".join(context_lines)

    fallback_ch, fallback_q = pool[0]
    return {
        "channelName": fallback_ch,
        "videoTitle": f"Viral Bhojpuri {mood.title()} Trend",
        "videoUrl": "https://www.youtube.com/results?search_query=" + fallback_q.replace(" ", "+"),
        "viewsLabel": "Live Bhojpuri Trend",
    }, f"Topic: {fallback_q}"


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
                            {"role": "system", "content": "You are an elite Purvanchali/Bihari Bhojpuri cinema writer. Return ONLY valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.85,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=45,
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
                    timeout=45,
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
    research_source, deep_context = deep_research_bhojpuri(config.get("channels", []), mood, used_urls)

    recent_hooks = [f"- ({h.get('mood')}) {h.get('title')}: {h.get('scriptDialogue', '')[:80]}" for h in history[-20:]]
    recent_block = "\n".join(recent_hooks) if recent_hooks else "None yet."

    draft_prompt = f"""
You are creating a cohesive, goosebumps-giving 45-to-58 second BHOJPURI Reel in mood: "{mood}".
Deep Research Context:
{deep_context}
Page Reach Insight: {reach_summary['notes']}

STRICT STORY & NATURAL BHOJPURI RULES (QUALITY GATE 1):
1. Tell ONE connected, logical story from Scene 1 to Scene 7 (Beginning Hook -> Emotional/Conflict Build-up -> Turning Point -> Killer Climax Ending). NEVER write random disconnected lines!
2. Write 100% pure, natural spoken Bhojpuri from Bihar/Purvanchal:
   - Good example: "जवन हाथ देख के लोग कहत रहे कि इ लइका कुछ ना करी, आज उहे हाथ अपना किस्मत के रेखा खुद लिख रहल बा।"
   - FORBIDDEN: Hindi verbs ("है, रहा है, होगी, मुझे, तुझे"), heavy Sanskrit ("रौद्रता, प्रतिशोध"), or English words!
3. Smart Editor Effect per scene: use `"smooth_zoom"`, `"pan_left"`, or `"pan_right"` for scenes 1–6, and `"climax_shake"` ONLY on the final climax punch scene (Scene 7) or 1 key turning point!
4. Pick `musicMood`: `"intense_action"` (rangdari), `"sad_emotional"` (bewafai/judai), `"warm_inspiring"` (vafadari), or `"desi_upbeat"` (comedy).
5. `subtitleText` MUST match `dialogue` word-for-word in Devanagari.
6. Every `imagePrompt` MUST describe a realistic 35mm Indian live-action photo of adult Indian characters continuing the SAME visual story (clear faces, real emotion, Bihar/UP environment, NO anime, NO cartoon).
7. Anti-repeat: Do NOT repeat anything from:
{recent_block}

Return strictly JSON:
{{
  "title": "Short Catchy Bhojpuri Title",
  "mood": "{mood}",
  "musicMood": "sad_emotional",
  "voiceStyle": "{'Aoede' if mood in ('bewafai','judai') else ('Puck' if mood == 'comedy' else 'Charon')}",
  "gapAnalysis": ["Flaw 1 in reference & how we fixed it", "Flaw 2 & fix", "Flaw 3 & fix"],
  "scenes": [
    {{
      "sceneNumber": 1,
      "effect": "smooth_zoom",
      "dialogue": "असली नेचुरल भोजपुरी डायलॉग",
      "subtitleText": "असली नेचुरल भोजपुरी डायलॉग",
      "imagePrompt": "Realistic 35mm DSLR movie still of an Indian man in Bihar..."
    }}
  ],
  "caption": "दमदार भोजपुरी कैप्शन + दर्शकों से सवाल",
  "hashtags": ["#BhojpuriReels", "#BhojpuriDialogue", "#DesiJazbaat", "#BiharUP", "#ViralBhojpuri", "#BhojpuriPulseX"]
}}
"""
    plan = call_llm_auto_rotate(draft_prompt)

    audit_prompt = f"""
Review and polish this 7-scene Bhojpuri Reel JSON script strictly:
{json.dumps(plan, ensure_ascii=False)}

Check 3 things:
1. Are Scenes 1 to 7 ONE single connected, meaningful story (not random unrelated sentences)? If any line breaks the story, rewrite it so it flows smoothly.
2. Is every single word natural spoken Bhojpuri (replace any Hindi words like "है/मुझे/रहा है/करेंगे" with "बा/हमरा/रहल बा/करब")?
3. Ensure `subtitleText` == `dialogue` for every scene, and `climax_shake` appears ONLY on the climax scene(s).
Return the final polished JSON in the exact same schema.
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
    plan["scriptDialogue"] = " ".join(s.get("dialogue", "") for s in plan.get("scenes", []))

    (WORK_DIR / "script_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Script Gate PASSED: {plan['id']} ({mood}, {len(plan.get('scenes', []))} scenes)")


if __name__ == "__main__":
    main()
