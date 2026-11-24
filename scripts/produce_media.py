import base64
import json
import math
import os
import struct
import subprocess
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import requests

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "work"
ASSETS_DIR = WORK_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def generate_image_cloudflare(prompt: str, out_path: Path, scene_idx: int):
    acc_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if acc_id and token:
        try:
            url = f"https://api.cloudflare.com/client/v4/accounts/{acc_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"prompt": f"{prompt}, ultra detailed cinematic lighting, vertical 9:16, no text, no watermark", "num_steps": 6},
                timeout=45,
            )
            if r.ok:
                data = r.json()
                b64_img = data.get("result", {}).get("image")
                if b64_img:
                    out_path.write_bytes(base64.b64decode(b64_img))
                    img = Image.open(out_path).convert("RGB").resize((1080, 1920), Image.Resampling.LANCZOS)
                    img.save(out_path, quality=92)
                    return
        except Exception:
            pass

    # Fallback clean dramatic gradient card (never fails)
    img = Image.new("RGB", (1080, 1920), (20, 28, 48))
    draw = ImageDraw.Draw(img)
    for y in range(1920):
        c1 = int(24 + (y / 1920) * 40)
        c2 = int(50 + ((scene_idx * 25 + y / 30) % 100))
        draw.line([(0, y), (1080, y)], fill=(c1, 32, min(220, c2)))
    img.save(out_path, quality=90)


def generate_voice_gemini(text: str, voice_name: str, out_wav: Path) -> bool:
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key or not text.strip():
        return False
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={gemini_key}"
        payload = {
            "contents": [{"parts": [{"text": f"Speak in expressive dramatic Bhojpuri Indian tone: {text}"}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}
                },
            },
        }
        r = requests.post(url, json=payload, timeout=45)
        if r.ok:
            parts = r.json()["candidates"][0]["content"]["parts"]
            for p in parts:
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
        return False
    return False


def generate_fallback_tone(duration_s: float, out_wav: Path):
    sr = 24000
    n_samples = int(sr * duration_s)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sr
            beat = 1.0 if (t % 0.5) < 0.08 else 0.25
            val = int(1200 * beat * math.sin(2 * math.pi * 110 * t))
            frames += struct.pack("<h", max(-32767, min(32767, val)))
        wf.writeframes(bytes(frames))


def generate_bgm(total_duration: float, out_wav: Path):
    sr = 24000
    n_samples = int(sr * total_duration)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sr
            pulse = math.exp(-((t % 0.6) * 8.0))
            bass = math.sin(2 * math.pi * 65.4 * t) * pulse * 2600
            pad = math.sin(2 * math.pi * 196.0 * t) * 700
            val = int(bass + pad)
            frames += struct.pack("<h", max(-32767, min(32767, val)))
        wf.writeframes(bytes(frames))


def get_audio_duration(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return max(3.5, float(res.stdout.strip()))
    except Exception:
        return 6.5


def format_ass_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def main():
    plan = json.loads((WORK_DIR / "script_plan.json").read_text(encoding="utf-8"))
    scenes = plan.get("scenes", [])
    voice = plan.get("voiceStyle", "Charon")
    if voice not in ("Charon", "Puck", "Aoede"):
        voice = "Charon"

    clip_paths = []
    ass_events = []
    cursor = 0.0

    for idx, sc in enumerate(scenes, start=1):
        img_path = ASSETS_DIR / f"scene_{idx}.png"
        wav_path = ASSETS_DIR / f"voice_{idx}.wav"
        clip_path = ASSETS_DIR / f"clip_{idx}.mp4"

        generate_image_cloudflare(sc.get("imagePrompt", "Dramatic Indian street scene"), img_path, idx)
        ok_tts = generate_voice_gemini(sc.get("dialogue", ""), voice, wav_path)
        if not ok_tts:
            generate_fallback_tone(6.5, wav_path)

        dur = get_audio_duration(wav_path) + 0.35
        frames = int(dur * 30)

        # Damdar editing: slow zoom-in + subtle punch shake at scene start + contrast grading
        vf = (
            f"scale=1200:2133,zoompan=z='min(zoom+0.0012,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
            f"eq=contrast=1.08:saturation=1.18:brightness=0.02"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img_path),
            "-i", str(wav_path),
            "-vf", vf,
            "-t", f"{dur:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
            "-c:a", "aac", "-ar", "24000", "-ac", "1",
            str(clip_path),
        ]
        subprocess.run(cmd, check=True)
        clip_paths.append(clip_path)

        sub_txt = sc.get("subtitleText") or sc.get("dialogue", "")
        ass_events.append(
            f"Dialogue: 0,{format_ass_time(cursor)},{format_ass_time(cursor + dur - 0.1)},Default,,0,0,0,,{sub_txt}"
        )
        cursor += dur

    # Concat clips
    concat_file = WORK_DIR / "concat.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths), encoding="utf-8")
    merged_mp4 = WORK_DIR / "merged.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(merged_mp4)], check=True)

    # Create ASS glowing subtitle file
    ass_path = WORK_DIR / "subs.ass"
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans Devanagari,64,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_path.write_text(ass_header + "\n".join(ass_events), encoding="utf-8")

    # Mix BGM + normalize audio + burn subtitles
    bgm_wav = WORK_DIR / "bgm.wav"
    generate_bgm(cursor + 0.5, bgm_wav)
    final_mp4 = WORK_DIR / "final_reel.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(merged_mp4),
            "-i", str(bgm_wav),
            "-filter_complex",
            f"[0:v]ass='{ass_path.resolve()}'[vout];[0:a]volume=1.6[va];[1:a]volume=0.22[ba];[va][ba]amix=inputs=2:duration=first,loudnorm[aout]",
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(final_mp4),
        ],
        check=True,
    )
    print(f"Final reel rendered: {final_mp4}")


if __name__ == "__main__":
    main()
