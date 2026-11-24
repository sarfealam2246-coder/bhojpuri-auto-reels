import base64
import json
import math
import os
import struct
import subprocess
import urllib.parse
import wave
from pathlib import Path
from PIL import Image, ImageDraw
import requests

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "work"
ASSETS_DIR = WORK_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def generate_real_image(prompt: str, out_path: Path, scene_idx: int):
    full_prompt = f"{prompt}, hyper realistic 8k cinematic photography, dramatic lighting, sharp focus, vertical 9:16, no text, no watermark"
    acc_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()

    # 1. Try Cloudflare Workers AI (handles both JSON base64 and raw PNG bytes)
    if acc_id and token:
        try:
            url = f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"prompt": full_prompt, "num_steps": 6},
                timeout=50,
            )
            if r.ok:
                ctype = r.headers.get("Content-Type", "")
                if "image/" in ctype:
                    out_path.write_bytes(r.content)
                else:
                    b64_img = r.json().get("result", {}).get("image")
                    if b64_img:
                        out_path.write_bytes(base64.b64decode(b64_img))
                if out_path.exists() and out_path.stat().st_size > 5000:
                    img = Image.open(out_path).convert("RGB").resize((1080, 1920), Image.Resampling.LANCZOS)
                    img.save(out_path, quality=94)
                    print(f"Scene {scene_idx}: Cloudflare Flux OK")
                    return
            else:
                print(f"Cloudflare failed ({r.status_code}): {r.text[:120]}")
        except Exception as exc:
            print(f"Cloudflare error: {exc}")

    # 2. Free High-Res Flux Fallback (Pollinations AI - Real cinematic photo!)
    try:
        encoded = urllib.parse.quote(full_prompt)
        p_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed={scene_idx * 137}"
        pr = requests.get(p_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
        if pr.ok and len(pr.content) > 10000:
            out_path.write_bytes(pr.content)
            img = Image.open(out_path).convert("RGB").resize((1080, 1920), Image.Resampling.LANCZOS)
            img.save(out_path, quality=94)
            print(f"Scene {scene_idx}: Pollinations Flux HD OK")
            return
    except Exception as exc:
        print(f"Pollinations fallback error: {exc}")

    # 3. Last-resort dark cinematic vignette (only if offline)
    img = Image.new("RGB", (1080, 1920), (18, 16, 26))
    draw = ImageDraw.Draw(img)
    for y in range(1920):
        c = int(16 + (y / 1920) * 35)
        draw.line([(0, y), (1080, y)], fill=(c, 18, 32))
    img.save(out_path, quality=90)


def generate_voice_gemini(text: str, voice_name: str, out_wav: Path) -> bool:
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key or not text.strip():
        return False
    for model in ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": f"Speak in intense, powerful, emotional Bhojpuri dialogue delivery with dramatic pauses: {text}"}]}],
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


def generate_impact_sfx(out_wav: Path):
    """Heavy bass thud + cinematic whoosh at scene start."""
    sr = 24000
    dur = 0.75
    n = int(sr * dur)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            env = math.exp(-t * 5.5)
            freq = 120.0 * math.exp(-t * 4.0) + 42.0
            thud = math.sin(2 * math.pi * freq * t) * env * 18000
            frames += struct.pack("<h", max(-32767, min(32767, int(thud))))
        wf.writeframes(bytes(frames))


def generate_heavy_bgm(total_duration: float, mood: str, out_wav: Path):
    """Deep rhythmic bass + dramatic cinematic pad."""
    sr = 24000
    n = int(sr * total_duration)
    tempo = 0.48 if mood == "rangdari" else 0.72
    base_hz = 55.0 if mood == "rangdari" else 65.4
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            beat_phase = t % tempo
            kick = math.exp(-beat_phase * 11.0) * math.sin(2 * math.pi * (base_hz + 50 * math.exp(-beat_phase * 18)) * t) * 7500
            sub = math.sin(2 * math.pi * base_hz * t) * 2600
            pad = (math.sin(2 * math.pi * (base_hz * 3.0) * t) + math.sin(2 * math.pi * (base_hz * 4.5) * t)) * 900
            val = int(kick + sub + pad)
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


def main():
    plan = json.loads((WORK_DIR / "script_plan.json").read_text(encoding="utf-8"))
    scenes = plan.get("scenes", [])
    mood = plan.get("mood", "rangdari")
    voice = plan.get("voiceStyle", "Charon")
    if voice not in ("Charon", "Puck", "Aoede"):
        voice = "Charon"

    sfx_wav = ASSETS_DIR / "impact_sfx.wav"
    generate_impact_sfx(sfx_wav)

    clip_paths = []
    ass_events = []
    cursor = 0.0

    for idx, sc in enumerate(scenes, start=1):
        img_path = ASSETS_DIR / f"scene_{idx}.png"
        wav_path = ASSETS_DIR / f"voice_{idx}.wav"
        mixed_wav = ASSETS_DIR / f"mixed_{idx}.wav"
        clip_path = ASSETS_DIR / f"clip_{idx}.mp4"

        generate_real_image(sc.get("imagePrompt", "Dramatic Indian cinematic scene"), img_path, idx)
        ok_tts = generate_voice_gemini(sc.get("dialogue", ""), voice, wav_path)
        if not ok_tts:
            generate_impact_sfx(wav_path)

        dur = get_audio_duration(wav_path) + 0.35
        frames = int(dur * 30)

        # Mix voice + heavy impact SFX at start of every scene
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(wav_path), "-i", str(sfx_wav),
                "-filter_complex", "[0:a]volume=1.5[v];[1:a]volume=0.85[s];[v][s]amix=inputs=2:duration=first[a]",
                "-map", "[a]", "-ar", "24000", "-ac", "1", str(mixed_wav),
            ],
            check=True,
        )

        # Damdar editing: punch zoom + impact shake in first 0.5s + contrast/warm cinematic grade
        vf = (
            f"scale=1240:2204,"
            f"zoompan=z='min(zoom+0.0022,1.22)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1120x1990:fps=30,"
            f"crop=1080:1920:'20+if(lt(t,0.45),18*sin(t*55),0)':'35+if(lt(t,0.45),18*cos(t*60),0)',"
            f"eq=contrast=1.12:saturation=1.22:brightness=-0.02"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", str(img_path), "-i", str(mixed_wav),
                "-vf", vf, "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
                "-c:a", "aac", "-ar", "24000", "-ac", "1", str(clip_path),
            ],
            check=True,
        )
        clip_paths.append(clip_path)

        sub_txt = sc.get("subtitleText") or sc.get("dialogue", "")
        ass_events.append(f"Dialogue: 0,{format_ass_time(cursor)},{format_ass_time(cursor + dur - 0.1)},Default,,0,0,0,,{sub_txt}")
        cursor += dur

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
Style: Default,Noto Sans Devanagari,68,&H0000E5FF,&H00FFFFFF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,5,3,2,55,55,270,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_path.write_text(ass_header + "\n".join(ass_events), encoding="utf-8")

    bgm_wav = WORK_DIR / "bgm.wav"
    generate_heavy_bgm(cursor + 0.5, mood, bgm_wav)
    final_mp4 = WORK_DIR / "final_reel.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(merged_mp4), "-i", str(bgm_wav),
            "-filter_complex",
            f"[0:v]ass='{ass_path.resolve()}'[vout];[0:a]volume=1.5[va];[1:a]volume=0.45[ba];[va][ba]amix=inputs=2:duration=first,loudnorm[aout]",
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final_mp4),
        ],
        check=True,
    )
    print(f"Final reel rendered: {final_mp4}")


if __name__ == "__main__":
    main()
