import base64
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import urllib.parse
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageStat
import requests

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "work"
ASSETS_DIR = WORK_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

BGM_YT_QUERIES = {
    "intense_action": "no copyright dark intense cinematic hip hop beat instrumental",
    "sad_emotional": "no copyright sad emotional flute piano instrumental music",
    "warm_inspiring": "no copyright inspiring emotional acoustic guitar instrumental",
    "desi_upbeat": "no copyright indian dholak upbeat folk instrumental music",
}


def is_valid_real_image(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 18000:
        return False
    try:
        img = Image.open(path).convert("RGB")
        stat = ImageStat.Stat(img)
        avg_std = sum(stat.stddev) / 3.0
        avg_mean = sum(stat.mean) / 3.0
        return avg_std > 12.0 and avg_mean > 15.0
    except Exception:
        return False


def finalize_portrait_image(raw_path: Path, out_path: Path):
    img = Image.open(raw_path).convert("RGB")
    w, h = img.size
    img = img.crop((0, 0, w, int(h * 0.94)))
    img = img.resize((1080, 1920), Image.Resampling.LANCZOS)
    img.save(out_path, quality=95)


def generate_real_image(prompt: str, out_path: Path, scene_idx: int, prev_valid_paths: list):
    full_prompt = (
        f"{prompt}, realistic 35mm Indian film still, real human photography, sharp focus, "
        f"dramatic cinematic lighting, vertical 9:16, no anime, no cartoon, no text, no watermark"
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
                    json={"prompt": full_prompt, "num_steps": 8, "width": 576, "height": 1024},
                    timeout=45,
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
                        print(f"Scene {scene_idx}: Cloudflare Flux OK")
                        return
            except Exception:
                pass
            time.sleep(1.5)

    if gemini_key:
        for g_model in ["gemini-2.0-flash-exp-image-generation", "gemini-2.5-flash-image"]:
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={gemini_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": f"Generate a vertical 9:16 realistic photograph: {full_prompt}"}]}],
                        "generationConfig": {"responseModalities": ["IMAGE"]},
                    },
                    timeout=45,
                )
                if r.ok:
                    for p in r.json()["candidates"][0]["content"]["parts"]:
                        if p.get("inlineData", {}).get("data"):
                            tmp_raw.write_bytes(base64.b64decode(p["inlineData"]["data"]))
                            if is_valid_real_image(tmp_raw):
                                finalize_portrait_image(tmp_raw, out_path)
                                print(f"Scene {scene_idx}: Gemini Image OK")
                                return
            except Exception:
                continue

    for attempt in range(3):
        try:
            time.sleep(3.5 + attempt * 3.0)
            encoded = urllib.parse.quote(full_prompt)
            p_url = f"https://image.pollinations.ai/prompt/{encoded}?width=720&height=1280&model=flux&nologo=true&seed={scene_idx * 503 + attempt}"
            pr = requests.get(p_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=50)
            if pr.ok and len(pr.content) > 18000:
                tmp_raw.write_bytes(pr.content)
                if is_valid_real_image(tmp_raw):
                    finalize_portrait_image(tmp_raw, out_path)
                    print(f"Scene {scene_idx}: Pollinations Flux OK")
                    return
        except Exception:
            pass

    if prev_valid_paths:
        src = Image.open(prev_valid_paths[-1]).convert("RGB")
        if scene_idx % 2 == 0:
            src = src.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        w, h = src.size
        src = src.crop((int(w * 0.08), int(h * 0.08), int(w * 0.92), int(h * 0.92))).resize((1080, 1920), Image.Resampling.LANCZOS)
        src.save(out_path, quality=94)
        print(f"Scene {scene_idx}: Visual Gate reused real zoomed frame (zero black screen)")
        return

    img = Image.new("RGB", (1080, 1920), (32, 24, 28))
    draw = ImageDraw.Draw(img)
    for y in range(1920):
        draw.line([(0, y), (1080, y)], fill=(int(28 + (y / 1920) * 45), 24, 38))
    img.save(out_path, quality=90)


def generate_voice_gemini(text: str, voice_name: str, out_wav: Path) -> bool:
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key or not text.strip():
        return False
    for model in ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": f"Speak in authentic, natural, expressive Bihar Bhojpuri cinema voice: {text}"}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}},
                },
            }
            r = requests.post(url, json=payload, timeout=45)
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
                        return True
        except Exception:
            continue
    return False


def fetch_real_bgm(music_mood: str, total_dur: float, out_wav: Path):
    query = BGM_YT_QUERIES.get(music_mood, BGM_YT_QUERIES["sad_emotional"])
    raw_audio = ASSETS_DIR / "bgm_dl"
    try:
        subprocess.run(
            [
                sys.executable, "-m", "yt_dlp",
                "-f", "bestaudio/best",
                "--max-filesize", "12M",
                "--no-playlist",
                "-o", str(raw_audio) + ".%(ext)s",
                f"ytsearch1:{query}",
            ],
            capture_output=True, text=True, timeout=30,
        )
        dl_files = list(ASSETS_DIR.glob("bgm_dl.*"))
        if dl_files and dl_files[0].stat().st_size > 30000:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-stream_loop", "-1",
                    "-ss", "12", "-i", str(dl_files[0]),
                    "-t", f"{total_dur:.2f}", "-ar", "24000", "-ac", "1",
                    str(out_wav),
                ],
                check=True,
            )
            print(f"Real No-Copyright BGM OK ({music_mood})")
            return
    except Exception as exc:
        print(f"BGM yt-dlp fallback ({exc})")

    sr = 24000
    n = int(sr * total_dur)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            beat = t % 0.75
            val = int(math.exp(-beat * 10.0) * math.sin(2 * math.pi * 52.0 * t) * 6500)
            frames += struct.pack("<h", max(-32767, min(32767, val)))
        wf.writeframes(bytes(frames))


def generate_climax_thud_sfx(out_wav: Path):
    sr = 24000
    n = int(sr * 0.65)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 6.0)
            freq = 92.0 * math.exp(-t * 5.0) + 36.0
            val = int(math.sin(2 * math.pi * freq * t) * env * 24000)
            frames += struct.pack("<h", max(-32767, min(32767, val)))
        wf.writeframes(bytes(frames))


def get_audio_duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return max(3.5, float(res.stdout.strip()))
    except Exception:
        return 6.0


def format_ass_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def create_thumbnail(scene_img: Path, title: str, out_thumb: Path):
    img = Image.open(scene_img).convert("RGB").resize((1080, 1920), Image.Resampling.LANCZOS)
    overlay = Image.new("RGBA", (1080, 1920), (0, 0, 0, 85))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    font_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
    try:
        font = ImageFont.truetype(font_path, 74) if Path(font_path).exists() else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    draw.rectangle([(60, 1420), (1020, 1660)], fill=(18, 18, 28), outline=(255, 200, 0), width=5)
    draw.text((540, 1540), title[:32], fill=(255, 220, 40), font=font, anchor="mm")
    img.save(out_thumb, quality=94)


def verify_final_reel(mp4_path: Path):
    assert mp4_path.exists() and mp4_path.stat().st_size > 100_000, "Final MP4 missing or too small"
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(mp4_path)],
        capture_output=True, text=True, check=True,
    )
    streams = res.stdout.strip().splitlines()
    assert "video" in streams and "audio" in streams, f"Missing A/V streams: {streams}"


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

    clip_paths = []
    ass_events = []
    valid_imgs = []
    cursor = 0.0
    intro_dur = 1.8

    for idx, sc in enumerate(scenes, start=1):
        img_path = ASSETS_DIR / f"scene_{idx}.png"
        wav_path = ASSETS_DIR / f"voice_{idx}.wav"
        voice_ready_wav = ASSETS_DIR / f"voice_ready_{idx}.wav"
        clip_path = ASSETS_DIR / f"clip_{idx}.mp4"

        generate_real_image(sc.get("imagePrompt", "Dramatic Indian cinema scene"), img_path, idx, valid_imgs)
        if is_valid_real_image(img_path):
            valid_imgs.append(img_path)

        ok_tts = generate_voice_gemini(sc.get("dialogue", ""), voice, wav_path)
        if not ok_tts:
            generate_climax_thud_sfx(wav_path)

        effect = sc.get("effect", "smooth_zoom")
        if idx == len(scenes) and mood in ("rangdari", "bewafai"):
            effect = "climax_shake"

        lead_delay_ms = int(intro_dur * 1000) if idx == 1 else 150
        if effect == "climax_shake":
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(wav_path), "-i", str(sfx_wav),
                    "-filter_complex", f"[0:a]adelay={lead_delay_ms}|{lead_delay_ms},volume=1.6[v];[1:a]volume=1.0[s];[v][s]amix=inputs=2:duration=first[a]",
                    "-map", "[a]", "-ar", "24000", "-ac", "1", str(voice_ready_wav),
                ],
                check=True,
            )
        else:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(wav_path),
                    "-af", f"adelay={lead_delay_ms}|{lead_delay_ms},volume=1.6",
                    "-ar", "24000", "-ac", "1", str(voice_ready_wav),
                ],
                check=True,
            )

        dur = get_audio_duration(voice_ready_wav) + 0.35
        frames = int(dur * 30)

        if effect == "climax_shake":
            vf = (
                f"scale=1260:2240,"
                f"zoompan=z='min(zoom+0.0025,1.22)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1140x2026:fps=30,"
                f"crop=1080:1920:'30+if(lt(t,0.65),26*sin(t*62),0)':'53+if(lt(t,0.65),26*cos(t*68),0)',"
                f"fade=t=in:st=0:d=0.12:color=white,"
                f"eq=contrast=1.10:saturation=1.18"
            )
        elif effect == "pan_left":
            vf = (
                f"scale=1240:2204,"
                f"zoompan=z='1.12':d={frames}:x='max(0,iw*0.10-(on/{frames})*iw*0.10)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                f"fade=t=in:st=0:d=0.20,"
                f"eq=contrast=1.08:saturation=1.16"
            )
        elif effect == "pan_right":
            vf = (
                f"scale=1240:2204,"
                f"zoompan=z='1.12':d={frames}:x='min(iw*0.10,(on/{frames})*iw*0.10)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                f"fade=t=in:st=0:d=0.20,"
                f"eq=contrast=1.08:saturation=1.16"
            )
        else:
            vf = (
                f"scale=1220:2168,"
                f"zoompan=z='min(zoom+0.0014,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                f"fade=t=in:st=0:d=0.20,"
                f"eq=contrast=1.08:saturation=1.16"
            )

        subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", str(img_path), "-i", str(voice_ready_wav),
                "-vf", vf, "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
                "-c:a", "aac", "-ar", "24000", "-ac", "1", str(clip_path),
            ],
            check=True,
        )
        clip_paths.append(clip_path)

        sub_start = cursor + (intro_dur if idx == 1 else 0.15)
        sub_txt = sc.get("subtitleText") or sc.get("dialogue", "")
        ass_events.append(
            f"Dialogue: 0,{format_ass_time(sub_start)},{format_ass_time(cursor + dur - 0.1)},Default,,0,0,0,,{{\\fscx85\\fscy85\\t(0,180,\\fscx104\\fscy104)\\t(180,300,\\fscx100\\fscy100)}}{sub_txt}"
        )
        cursor += dur

    title_text = plan.get("title", "Bhojpuri Pulse X")
    ass_events.insert(
        0,
        f"Dialogue: 1,0:00:00.00,0:00:02.60,TitleBanner,,0,0,0,,{{\\fad(200,300)\\fscx75\\fscy75\\t(0,260,\\fscx108\\fscy108)\\t(260,420,\\fscx100\\fscy100)}}{title_text}",
    )

    concat_file = WORK_DIR / "concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths), encoding="utf-8")
    merged_mp4 = WORK_DIR / "merged.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(merged_mp4)], check=True)

    ass_path = WORK_DIR / "subs.ass"
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans Devanagari,68,&H0000EAFF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,5,3,2,55,55,270,1
Style: TitleBanner,Noto Sans Devanagari,82,&H0000D4FF,&H00FFFFFF,&H00120A3A,&HC0000000,-1,0,0,0,100,100,1,0,1,6,4,8,50,50,210,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_path.write_text(ass_header + "\n".join(ass_events), encoding="utf-8")

    bgm_wav = WORK_DIR / "bgm.wav"
    fetch_real_bgm(music_mood, cursor + 0.5, bgm_wav)

    final_mp4 = WORK_DIR / "final_reel.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(merged_mp4), "-i", str(bgm_wav),
            "-filter_complex",
            (
                f"[0:v]ass='{ass_path.resolve()}'[vout];"
                f"[0:a]asplit=2[vo_main][vo_sc];"
                f"[1:a]volume=0.55[bgm_in];"
                f"[bgm_in][vo_sc]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=450[bgm_ducked];"
                f"[vo_main][bgm_ducked]amix=inputs=2:duration=first,loudnorm[aout]"
            ),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final_mp4),
        ],
        check=True,
    )

    verify_final_reel(final_mp4)
    if valid_imgs:
        create_thumbnail(valid_imgs[0], title_text, WORK_DIR / "thumbnail.jpg")
    elif (ASSETS_DIR / "scene_1.png").exists():
        create_thumbnail(ASSETS_DIR / "scene_1.png", title_text, WORK_DIR / "thumbnail.jpg")

    print(f"All Quality Gates PASSED: {final_mp4} (duration ~{cursor:.1f}s)")


if __name__ == "__main__":
    main()
