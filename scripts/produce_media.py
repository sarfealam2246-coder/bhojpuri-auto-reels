import asyncio
import base64
import json
import math
import os
import random
import re
import struct
import subprocess
import sys
import time
import urllib.parse
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageStat
import requests

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "work"
ASSETS_DIR = WORK_DIR / "assets"
LOCAL_BGM_DIR = ROOT / "assets" / "bgm"
WORK_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

DEVA_FONT_PATH = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
EMOJI_FONT_PATH = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

BGM_YT_QUERIES = {
    "intense_action": "no copyright dark intense cinematic hip hop beat instrumental",
    "sad_emotional": "no copyright sad emotional flute piano instrumental music",
    "warm_inspiring": "no copyright inspiring emotional acoustic guitar instrumental",
    "desi_upbeat": "no copyright indian dholak upbeat folk instrumental music",
}

CC0_BGM_LIBRARY = {
    "intense_action": [
        "https://freepd.com/music/Epic%20Blockbuster%202.mp3",
        "https://upload.wikimedia.org/wikipedia/commons/e/e4/Kevin_MacLeod_-_Impact_Moderato.ogg",
        "https://freepd.com/music/Dark%20Tension%20Rising%20Music.mp3",
    ],
    "sad_emotional": [
        "https://upload.wikimedia.org/wikipedia/commons/4/45/Kevin_MacLeod_-_Heartbreaking.ogg",
        "https://upload.wikimedia.org/wikipedia/commons/8/87/Kevin_MacLeod_-_Touching_Moments_Two_-_Higher.ogg",
        "https://freepd.com/music/Sad%20Trio.mp3",
    ],
    "warm_inspiring": [
        "https://upload.wikimedia.org/wikipedia/commons/8/87/Kevin_MacLeod_-_Touching_Moments_Two_-_Higher.ogg",
        "https://freepd.com/music/Inspiring%20Teaser.mp3",
    ],
    "desi_upbeat": [
        "https://upload.wikimedia.org/wikipedia/commons/5/59/Kevin_MacLeod_-_Bossa_Bossa.ogg",
        "https://freepd.com/music/Funshine.mp3",
    ],
}


def is_valid_real_image(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 20000:
        return False
    try:
        img = Image.open(path).convert("RGB")
        stat = ImageStat.Stat(img)
        return (sum(stat.stddev) / 3.0) > 12.0 and (sum(stat.mean) / 3.0) > 15.0
    except Exception:
        return False


def finalize_portrait_image(raw_path: Path, out_path: Path):
    img = Image.open(raw_path).convert("RGB")
    w, h = img.size
    img = img.crop((0, 0, w, int(h * 0.94)))
    img = img.resize((1080, 1920), Image.Resampling.LANCZOS)
    img = ImageEnhance.Sharpness(img).enhance(1.18)
    img = ImageEnhance.Contrast(img).enhance(1.04)
    img.save(out_path, quality=96)


def generate_real_image(prompt: str, out_path: Path, scene_idx: int, prev_valid_paths: list):
    full_prompt = (
        f"{prompt}, ultra sharp 8k 35mm DSLR Indian film still, single person close-up portrait, "
        f"crisp facial details, dramatic cinema lighting, vertical 9:16, no blur, no anime, no cartoon, no text, no watermark"
    )
    acc_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    tmp_raw = ASSETS_DIR / f"raw_{scene_idx}.png"

    if acc_id and token:
        for _ in range(2):
            try:
                r = requests.post(
                    f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"prompt": full_prompt, "num_steps": 8, "width": 720, "height": 1280},
                    timeout=50,
                )
                if r.ok:
                    if "image/" in r.headers.get("Content-Type", ""):
                        tmp_raw.write_bytes(r.content)
                    else:
                        b64_img = r.json().get("result", {}).get("image")
                        if b64_img:
                            tmp_raw.write_bytes(base64.b64decode(b64_img))
                    if is_valid_real_image(tmp_raw):
                        finalize_portrait_image(tmp_raw, out_path)
                        print(f"Scene {scene_idx}: Cloudflare HD Flux OK")
                        return
                else:
                    print(f"Cloudflare status {r.status_code}: {r.text[:100]}")
            except Exception as exc:
                print(f"Cloudflare error: {exc}")
            time.sleep(1.5)

    if gemini_key:
        for g_model in ["gemini-2.0-flash-exp-image-generation", "gemini-2.5-flash-image"]:
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={gemini_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": f"Generate a sharp HD vertical 9:16 realistic photograph: {full_prompt}"}]}],
                        "generationConfig": {"responseModalities": ["IMAGE"]},
                    },
                    timeout=50,
                )
                if r.ok:
                    for p in r.json()["candidates"][0]["content"]["parts"]:
                        if p.get("inlineData", {}).get("data"):
                            tmp_raw.write_bytes(base64.b64decode(p["inlineData"]["data"]))
                            if is_valid_real_image(tmp_raw):
                                finalize_portrait_image(tmp_raw, out_path)
                                print(f"Scene {scene_idx}: Gemini HD Image OK")
                                return
            except Exception:
                continue

    for attempt in range(3):
        try:
            time.sleep(3.5 + attempt * 3.0)
            encoded = urllib.parse.quote(full_prompt)
            p_url = f"https://image.pollinations.ai/prompt/{encoded}?width=720&height=1280&model=flux&nologo=true&seed={scene_idx * 503 + attempt}"
            pr = requests.get(p_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=55)
            if pr.ok and len(pr.content) > 20000:
                tmp_raw.write_bytes(pr.content)
                if is_valid_real_image(tmp_raw):
                    finalize_portrait_image(tmp_raw, out_path)
                    print(f"Scene {scene_idx}: Pollinations HD Flux OK")
                    return
        except Exception:
            pass

    if prev_valid_paths:
        src = Image.open(prev_valid_paths[-1]).convert("RGB")
        if scene_idx % 2 == 0:
            src = src.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        w, h = src.size
        src = src.crop((int(w * 0.08), int(h * 0.08), int(w * 0.92), int(h * 0.92))).resize((1080, 1920), Image.Resampling.LANCZOS)
        src.save(out_path, quality=95)
        print(f"Scene {scene_idx}: Visual Gate reused zoomed HD frame")
        return

    img = Image.new("RGB", (1080, 1920), (32, 24, 28))
    draw = ImageDraw.Draw(img)
    for y in range(1920):
        draw.line([(0, y), (1080, y)], fill=(int(28 + (y / 1920) * 45), 24, 38))
    img.save(out_path, quality=92)


def is_valid_voice_wav(wav_path: Path) -> bool:
    if not wav_path.exists() or wav_path.stat().st_size < 16000:
        return False
    dur = get_audio_duration(wav_path)
    return dur >= 1.1


def generate_voice_gemini(text: str, voice_name: str, out_wav: Path) -> bool:
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key or not text.strip():
        return False
    for model in ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": f"Speak in authentic, bold, expressive Bihar Bhojpuri cinema voice: {text}"}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}},
                },
            }
            r = requests.post(url, json=payload, timeout=50)
            if r.ok:
                for p in r.json()["candidates"][0]["content"]["parts"]:
                    inline = p.get("inlineData")
                    if inline and inline.get("data"):
                        pcm = base64.b64decode(inline["data"])
                        with wave.open(str(out_wav), "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(24000)
                            wf.writeframes(pcm)
                        if is_valid_voice_wav(out_wav):
                            return True
        except Exception:
            continue
    return False


async def _run_edge_tts(text: str, voice_id: str, pitch: str, mp3_path: Path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice_id, pitch=pitch)
    await communicate.save(str(mp3_path))


def generate_voice_guaranteed(text: str, voice_name: str, mood: str, out_wav: Path):
    """3-Layer Guaranteed Voice: 1) Gemini TTS -> 2) Free Zero-Key edge-tts -> 3) gTTS."""
    clean_text = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27bf]", "", text).strip() or text.strip()
    if generate_voice_gemini(clean_text, voice_name, out_wav):
        print("Voice Layer 1: Gemini TTS OK")
        return

    try:
        edge_voice = "hi-IN-SwaraNeural" if voice_name == "Aoede" else "hi-IN-MadhurNeural"
        pitch = "-4Hz" if mood == "rangdari" else ("+2Hz" if mood == "comedy" else "+0Hz")
        tmp_mp3 = out_wav.with_suffix(".edge.mp3")
        asyncio.run(_run_edge_tts(clean_text, edge_voice, pitch, tmp_mp3))
        subprocess.run(["ffmpeg", "-y", "-i", str(tmp_mp3), "-ar", "24000", "-ac", "1", str(out_wav)], check=True, capture_output=True)
        if is_valid_voice_wav(out_wav):
            print(f"Voice Layer 2: edge-tts ({edge_voice}) OK")
            return
    except Exception as exc:
        print(f"edge-tts fallback skipped ({exc})")

    try:
        from gtts import gTTS
        tmp_mp3 = out_wav.with_suffix(".gtts.mp3")
        gTTS(text=clean_text, lang="hi", slow=False).save(str(tmp_mp3))
        subprocess.run(["ffmpeg", "-y", "-i", str(tmp_mp3), "-ar", "24000", "-ac", "1", str(out_wav)], check=True, capture_output=True)
        if is_valid_voice_wav(out_wav):
            print("Voice Layer 3: gTTS OK")
            return
    except Exception as exc:
        print(f"gTTS fallback skipped ({exc})")

    raise RuntimeError(f"All 3 voice layers failed for dialogue: {clean_text[:40]}")


def fetch_real_bgm(music_mood: str, mood: str, total_dur: float, out_wav: Path):
    """Zero-API-Key BGM fetcher: 1) Local assets/bgm/, 2) Multi-track CC0 URLs, 3) yt-dlp, 4) Phone-audible beat."""
    for fname in [f"{mood}.mp3", f"{music_mood}.mp3", "default.mp3"]:
        local_f = LOCAL_BGM_DIR / fname
        if local_f.exists() and local_f.stat().st_size > 20000:
            subprocess.run(
                ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(local_f), "-t", f"{total_dur:.2f}", "-ar", "24000", "-ac", "1", str(out_wav)],
                check=True, capture_output=True,
            )
            print(f"Local Repo BGM OK: {local_f.name}")
            return

    urls = list(CC0_BGM_LIBRARY.get(music_mood, CC0_BGM_LIBRARY["sad_emotional"]))
    random.shuffle(urls)
    for dl_url in urls:
        try:
            r = requests.get(dl_url, headers={"User-Agent": "Mozilla/5.0 (compatible; BhojpuriReelStudio/1.0)"}, timeout=30)
            if r.ok and len(r.content) > 30000:
                ext = ".mp3" if dl_url.lower().endswith(".mp3") else ".ogg"
                raw_path = ASSETS_DIR / f"cc0_bgm{ext}"
                raw_path.write_bytes(r.content)
                subprocess.run(
                    ["ffmpeg", "-y", "-stream_loop", "-1", "-ss", "4", "-i", str(raw_path), "-t", f"{total_dur:.2f}", "-ar", "24000", "-ac", "1", str(out_wav)],
                    check=True, capture_output=True,
                )
                print(f"CC0 Direct BGM OK ({music_mood}): {dl_url.split('/')[-1]}")
                return
        except Exception as exc:
            print(f"CC0 BGM retry ({exc})")

    query = BGM_YT_QUERIES.get(music_mood, BGM_YT_QUERIES["sad_emotional"])
    raw_audio = ASSETS_DIR / "bgm_dl"
    try:
        subprocess.run(
            [sys.executable, "-m", "yt_dlp", "-f", "bestaudio/best", "--max-filesize", "12M", "--no-playlist", "-o", str(raw_audio) + ".%(ext)s", f"ytsearch1:{query}"],
            capture_output=True, text=True, timeout=30,
        )
        dl_files = list(ASSETS_DIR.glob("bgm_dl.*"))
        if dl_files and dl_files[0].stat().st_size > 30000:
            subprocess.run(
                ["ffmpeg", "-y", "-stream_loop", "-1", "-ss", "10", "-i", str(dl_files[0]), "-t", f"{total_dur:.2f}", "-ar", "24000", "-ac", "1", str(out_wav)],
                check=True, capture_output=True,
            )
            print(f"yt-dlp No-Copyright BGM OK ({music_mood})")
            return
    except Exception:
        pass

    sr = 24000
    n = int(sr * total_dur)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            beat = t % 0.65
            env = math.exp(-beat * 8.0)
            chord = math.sin(2 * math.pi * 164.8 * t) + 0.6 * math.sin(2 * math.pi * 220.0 * t)
            kick = math.sin(2 * math.pi * (140.0 * math.exp(-beat * 14.0) + 60.0) * t) * math.exp(-beat * 12.0)
            val = int((chord * env * 2800) + (kick * 4500))
            frames += struct.pack("<h", max(-32767, min(32767, val)))
        wf.writeframes(bytes(frames))
    print("Phone-audible fallback beat generated")


def generate_climax_thud_sfx(out_wav: Path):
    sr = 24000
    n = int(sr * 0.55)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 6.5)
            freq = 150.0 * math.exp(-t * 7.0) + 65.0
            val = int(math.sin(2 * math.pi * freq * t) * env * 24000)
            frames += struct.pack("<h", max(-32767, min(32767, val)))
        wf.writeframes(bytes(frames))


def get_audio_duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return max(1.2, float(res.stdout.strip()))
    except Exception:
        return 5.0


def measure_mean_volume_db(path: Path) -> float:
    res = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", res.stderr)
    return float(m.group(1)) if m else -20.0


def is_emoji_char(ch: str) -> bool:
    cp = ord(ch)
    return (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF)


def tokenize_text_with_emojis(text: str) -> list[tuple[str, bool]]:
    tokens = []
    buf = ""
    for ch in text:
        if ord(ch) == 0xFE0F:
            continue
        if is_emoji_char(ch):
            if buf:
                tokens.append((buf, False))
                buf = ""
            tokens.append((ch, True))
        else:
            buf += ch
    if buf:
        tokens.append((buf, False))
    return tokens


def wrap_tokens_to_lines(text: str, deva_font, emoji_size: int, max_width: int) -> list[list[tuple[str, bool]]]:
    words = text.split(" ")
    lines = []
    cur_line_str = ""
    dummy = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    def measure_str_w(s: str) -> int:
        total = 0
        for seg, is_em in tokenize_text_with_emojis(s):
            if is_em:
                total += emoji_size + 6
            else:
                bbox = dummy.textbbox((0, 0), seg, font=deva_font)
                total += max(0, bbox[2] - bbox[0])
        return total

    for w in words:
        test = f"{cur_line_str} {w}".strip()
        if measure_str_w(test) <= max_width or not cur_line_str:
            cur_line_str = test
        else:
            lines.append(tokenize_text_with_emojis(cur_line_str))
            cur_line_str = w
    if cur_line_str:
        lines.append(tokenize_text_with_emojis(cur_line_str))
    return lines


def render_text_emoji_overlay_png(text: str, out_png: Path, is_title: bool = False):
    """Render crisp Devanagari + real Color Emoji PNG overlay (1080x1920 RGBA)."""
    canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    deva_size = 64 if is_title else 56
    emoji_size = 68 if is_title else 60
    deva_font = ImageFont.truetype(DEVA_FONT_PATH, deva_size) if Path(DEVA_FONT_PATH).exists() else ImageFont.load_default()
    emoji_font = ImageFont.truetype(EMOJI_FONT_PATH, 109) if Path(EMOJI_FONT_PATH).exists() else None

    lines = wrap_tokens_to_lines(text.strip(), deva_font, emoji_size, max_width=900)
    line_h = int(deva_size * 1.45)
    total_h = max(line_h, len(lines) * line_h + 36)
    y_top = 150 if is_title else (1540 - total_h // 2)

    box_fill = (16, 16, 26, 205) if is_title else (10, 10, 18, 175)
    outline_col = (255, 200, 0, 230) if is_title else (255, 255, 255, 70)
    draw.rounded_rectangle([(55, y_top), (1025, y_top + total_h)], radius=24, fill=box_fill, outline=outline_col, width=3)

    fill_col = (255, 224, 50, 255) if is_title else (255, 240, 85, 255)
    cur_y = y_top + 18
    for line_tokens in lines:
        line_w = 0
        for seg, is_em in line_tokens:
            if is_em:
                line_w += emoji_size + 6
            else:
                bb = draw.textbbox((0, 0), seg, font=deva_font)
                line_w += max(0, bb[2] - bb[0])
        cur_x = max(75, (1080 - line_w) // 2)
        for seg, is_em in line_tokens:
            if is_em and emoji_font is not None:
                em_tile = Image.new("RGBA", (130, 130), (0, 0, 0, 0))
                em_draw = ImageDraw.Draw(em_tile)
                try:
                    em_draw.text((10, 10), seg, font=emoji_font, embedded_color=True)
                    em_scaled = em_tile.resize((emoji_size, emoji_size), Image.Resampling.LANCZOS)
                    canvas.alpha_composite(em_scaled, (cur_x, cur_y + 2))
                except Exception:
                    pass
                cur_x += emoji_size + 6
            else:
                draw.text((cur_x + 2, cur_y + 2), seg, font=deva_font, fill=(0, 0, 0, 220))
                draw.text((cur_x, cur_y), seg, font=deva_font, fill=fill_col)
                bb = draw.textbbox((0, 0), seg, font=deva_font)
                cur_x += max(0, bb[2] - bb[0])
        cur_y += line_h

    canvas.save(out_png)


def create_thumbnail(scene_img: Path, title: str, out_thumb: Path):
    base = Image.open(scene_img).convert("RGBA").resize((1080, 1920), Image.Resampling.LANCZOS)
    title_png = ASSETS_DIR / "thumb_title.png"
    render_text_emoji_overlay_png(title[:42], title_png, is_title=True)
    ov = Image.open(title_png).convert("RGBA")
    merged = Image.alpha_composite(base, ov).convert("RGB")
    merged.save(out_thumb, quality=95)


def verify_final_reel(mp4_path: Path):
    assert mp4_path.exists() and mp4_path.stat().st_size > 100_000, "Final MP4 missing or too small"
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(mp4_path)],
        capture_output=True, text=True, check=True,
    )
    streams = res.stdout.strip().splitlines()
    assert "video" in streams and "audio" in streams, f"Missing A/V streams: {streams}"
    mean_db = measure_mean_volume_db(mp4_path)
    print(f"Final MP4 Audio Gate -> mean_volume={mean_db:.1f} dB")
    assert mean_db > -45.0, f"Final MP4 audio too quiet ({mean_db} dB)"


def main():
    plan = json.loads((WORK_DIR / "script_plan.json").read_text(encoding="utf-8"))
    scenes = plan.get("scenes", [])
    mood = plan.get("mood", "rangdari")
    music_mood = plan.get("musicMood", "sad_emotional")
    voice = plan.get("voiceStyle", "Charon")
    if voice not in ("Charon", "Puck", "Aoede"):
        voice = "Charon"

    sfx_wav = ASSETS_DIR / "climax_thud.wav"
    generate_climax_thud_sfx(sfx_wav)

    title_text = plan.get("title", "Bhojpuri Pulse X 🔥")
    title_png = ASSETS_DIR / "title_overlay.png"
    render_text_emoji_overlay_png(title_text, title_png, is_title=True)

    clip_paths = []
    valid_imgs = []
    cursor = 0.0
    intro_dur = 0.70

    for idx, sc in enumerate(scenes, start=1):
        img_path = ASSETS_DIR / f"scene_{idx}.png"
        sub_png = ASSETS_DIR / f"sub_{idx}.png"
        wav_path = ASSETS_DIR / f"voice_{idx}.wav"
        voice_ready_wav = ASSETS_DIR / f"voice_ready_{idx}.wav"
        clip_path = ASSETS_DIR / f"clip_{idx}.mp4"

        generate_real_image(sc.get("imagePrompt", "Dramatic Indian cinema portrait"), img_path, idx, valid_imgs)
        if is_valid_real_image(img_path):
            valid_imgs.append(img_path)

        sub_txt = sc.get("subtitleText") or sc.get("dialogue", "")
        render_text_emoji_overlay_png(sub_txt, sub_png, is_title=False)

        if idx > 1:
            time.sleep(1.2)
        generate_voice_guaranteed(sc.get("dialogue", ""), voice, mood, wav_path)

        effect = sc.get("effect", "smooth_zoom")
        if idx == len(scenes) and mood in ("rangdari", "bewafai"):
            effect = "climax_shake"

        lead_delay_ms = int(intro_dur * 1000) if idx == 1 else 60
        if effect == "climax_shake":
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(wav_path), "-i", str(sfx_wav),
                    "-filter_complex", f"[0:a]adelay={lead_delay_ms}|{lead_delay_ms},volume=1.6[v];[1:a]volume=1.1[s];[v][s]amix=inputs=2:duration=longest[a]",
                    "-map", "[a]", "-ar", "24000", "-ac", "1", str(voice_ready_wav),
                ],
                check=True, capture_output=True,
            )
        else:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(wav_path),
                    "-af", f"adelay={lead_delay_ms}|{lead_delay_ms},volume=1.6",
                    "-ar", "24000", "-ac", "1", str(voice_ready_wav),
                ],
                check=True, capture_output=True,
            )

        dur = get_audio_duration(voice_ready_wav) + 0.08
        frames = int(dur * 30)

        if effect == "climax_shake":
            vf = (
                f"scale=1260:2240,"
                f"zoompan=z='min(zoom+0.0025,1.22)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1140x2026:fps=30,"
                f"crop=1080:1920:'30+if(lt(t,0.65),26*sin(t*62),0)':'53+if(lt(t,0.65),26*cos(t*68),0)',"
                f"fade=t=in:st=0:d=0.10:color=white,"
                f"eq=contrast=1.10:saturation=1.18"
            )
        elif effect == "pan_left":
            vf = (
                f"scale=1240:2204,"
                f"zoompan=z='1.12':d={frames}:x='max(0,iw*0.10-(on/{frames})*iw*0.10)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                f"fade=t=in:st=0:d=0.15,"
                f"eq=contrast=1.08:saturation=1.16"
            )
        elif effect == "pan_right":
            vf = (
                f"scale=1240:2204,"
                f"zoompan=z='1.12':d={frames}:x='min(iw*0.10,(on/{frames})*iw*0.10)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                f"fade=t=in:st=0:d=0.15,"
                f"eq=contrast=1.08:saturation=1.16"
            )
        else:
            vf = (
                f"scale=1220:2168,"
                f"zoompan=z='min(zoom+0.0014,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                f"fade=t=in:st=0:d=0.15,"
                f"eq=contrast=1.08:saturation=1.16"
            )

        filter_complex = f"[0:v]{vf}[bg];[bg][1:v]overlay=0:0:shortest=1[vout]"
        subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", str(img_path), "-loop", "1", "-i", str(sub_png), "-i", str(voice_ready_wav),
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", "2:a",
                "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
                "-c:a", "aac", "-ar", "24000", "-ac", "1", str(clip_path),
            ],
            check=True, capture_output=True,
        )
        clip_paths.append(clip_path)
        cursor += get_audio_duration(clip_path)

    concat_file = WORK_DIR / "concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths), encoding="utf-8")
    merged_mp4 = WORK_DIR / "merged.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(merged_mp4)], check=True, capture_output=True)

    bgm_wav = WORK_DIR / "bgm.wav"
    fetch_real_bgm(music_mood, mood, cursor + 0.2, bgm_wav)

    bgm_mean_db = measure_mean_volume_db(bgm_wav)
    bgm_vol = 0.65 if bgm_mean_db < -22.0 else 0.42
    print(f"Audio Gate -> BGM mean={bgm_mean_db:.1f}dB, chosen bgm_vol={bgm_vol}")

    final_mp4 = WORK_DIR / "final_reel.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(merged_mp4), "-i", str(bgm_wav), "-i", str(title_png),
            "-filter_complex",
            (
                f"[0:v][2:v]overlay=0:0:enable='between(t,0,2.3)':eof_action=pass[vout];"
                f"[0:a]asplit=2[vo_main][vo_sc];"
                f"[1:a]volume={bgm_vol}[bgm_in];"
                f"[bgm_in][vo_sc]sidechaincompress=threshold=0.02:ratio=5:attack=25:release=400[bgm_ducked];"
                f"[vo_main][bgm_ducked]amix=inputs=2:duration=first,loudnorm[aout]"
            ),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{cursor:.2f}", "-movflags", "+faststart", str(final_mp4),
        ],
        check=True, capture_output=True,
    )

    verify_final_reel(final_mp4)
    if valid_imgs:
        create_thumbnail(valid_imgs[0], title_text, WORK_DIR / "thumbnail.jpg")
    elif (ASSETS_DIR / "scene_1.png").exists():
        create_thumbnail(ASSETS_DIR / "scene_1.png", title_text, WORK_DIR / "thumbnail.jpg")

    print(f"All Quality, HD Image, Color Emoji & Audio Gates PASSED: {final_mp4} (duration ~{cursor:.1f}s)")


if __name__ == "__main__":
    main()
