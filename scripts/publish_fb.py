import json
import os
import subprocess
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WORK_DIR = ROOT / "work"


def upload_to_github_release(reel_id: str, mp4_path: Path, report_path: Path) -> str:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    token = os.getenv("GH_AUTO_PAT", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
    if not repo or not token:
        return ""
    tag = f"reel-{reel_id}"
    env = {**os.environ, "GH_TOKEN": token}
    try:
        subprocess.run(
            ["gh", "release", "create", tag, str(mp4_path), str(report_path), "--title", f"Bhojpuri Reel {reel_id}", "--notes", "Auto-archived by Bhojpuri ReelStudio"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return f"https://github.com/{repo}/releases/download/{tag}/{mp4_path.name}"
    except Exception:
        return ""


def publish_reel_to_facebook(mp4_path: Path, description: str) -> tuple[bool, str, str]:
    page_id = os.getenv("FB_PAGE_ID", "").strip()
    token = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
    if not page_id or not token:
        return False, "", "FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN not set in APK Vault yet."

    try:
        # Step 1: Start upload
        start_res = requests.post(
            f"https://graph.facebook.com/v21.0/{page_id}/video_reels",
            data={"upload_phase": "start", "access_token": token},
            timeout=30,
        )
        if not start_res.ok:
            return False, "", f"FB Start failed: {start_res.text}"
        start_json = start_res.json()
        video_id = start_json.get("video_id")
        upload_url = start_json.get("upload_url")

        # Step 2: Upload binary
        file_bytes = mp4_path.read_bytes()
        up_res = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(len(file_bytes)),
            },
            data=file_bytes,
            timeout=120,
        )
        if not up_res.ok:
            return False, "", f"FB Binary upload failed: {up_res.text}"

        # Step 3: Finish & Publish
        fin_res = requests.post(
            f"https://graph.facebook.com/v21.0/{page_id}/video_reels",
            data={
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description,
                "access_token": token,
            },
            timeout=45,
        )
        if not fin_res.ok:
            return False, "", f"FB Finish failed: {fin_res.text}"
        return True, f"https://www.facebook.com/reel/{video_id}", ""
    except Exception as exc:
        return False, "", str(exc)


def main():
    plan = json.loads((WORK_DIR / "script_plan.json").read_text(encoding="utf-8"))
    mp4_path = WORK_DIR / "final_reel.mp4"
    report_path = WORK_DIR / "reel-report.json"

    caption_full = f"{plan.get('caption', '')}\n\n{' '.join(plan.get('hashtags', []))}".strip()
    fb_ok, fb_url, fb_err = publish_reel_to_facebook(mp4_path, caption_full)

    entry = {
        "id": plan["id"],
        "createdAt": plan["createdAt"],
        "slot": plan.get("slot", "manual"),
        "mood": plan.get("mood", "rangdari"),
        "title": plan.get("title", "Bhojpuri Reel"),
        "scriptDialogue": plan.get("scriptDialogue", ""),
        "caption": plan.get("caption", ""),
        "hashtags": plan.get("hashtags", []),
        "researchSource": plan.get("researchSource", {}),
        "gapAnalysis": plan.get("gapAnalysis", []),
        "status": {
            "script": True,
            "media": True,
            "render": mp4_path.exists(),
            "fbUpload": fb_ok,
            **({"error": fb_err} if fb_err else {}),
        },
        "fbPostUrl": fb_url or None,
    }
    report_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

    dl_url = upload_to_github_release(plan["id"], mp4_path, report_path)
    if dl_url:
        entry["videoDownloadUrl"] = dl_url

    hist_file = DATA_DIR / "history.json"
    history = json.loads(hist_file.read_text(encoding="utf-8")) if hist_file.exists() else []
    history.append(entry)
    hist_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Published & archived: {entry['id']} (fb_ok={fb_ok})")


if __name__ == "__main__":
    main()
