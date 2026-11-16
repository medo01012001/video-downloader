"""
تطبيق تحميل الفيديوهات — Flask + yt-dlp
كيدعم يوتيوب، فيسبوك، انستغرام، تيك توك، تويتر/X وبزاف ديال المنصات الأخرى.
"""
import os
import re
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder="static")

# job_id -> dict(status, percent, speed, eta, title, file, error, created)
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
FILE_TTL_SECONDS = 60 * 60  # كنمسحو الملفات من بعد ساعة


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name or "video").strip()
    return (name[:120] or "video").strip(". ")


def cleanup_old_files():
    while True:
        now = time.time()
        for f in DOWNLOAD_DIR.iterdir():
            try:
                if now - f.stat().st_mtime > FILE_TTL_SECONDS:
                    f.unlink()
            except OSError:
                pass
        with JOBS_LOCK:
            for jid in [j for j, d in JOBS.items() if now - d["created"] > FILE_TTL_SECONDS]:
                JOBS.pop(jid, None)
        time.sleep(600)


threading.Thread(target=cleanup_old_files, daemon=True).start()


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/info")
def info():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify(error="دخل الرابط عافاك"), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
            data = ydl.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        return jsonify(error=clean_error(e)), 400

    if data.get("_type") == "playlist" and data.get("entries"):
        data = next((e for e in data["entries"] if e), data)

    heights = sorted(
        {f["height"] for f in data.get("formats", []) if f.get("height") and f.get("vcodec") != "none"},
        reverse=True,
    )
    return jsonify(
        title=data.get("title"),
        thumbnail=data.get("thumbnail"),
        duration=data.get("duration"),
        uploader=data.get("uploader") or data.get("channel"),
        platform=data.get("extractor_key"),
        heights=heights,
    )


@app.post("/api/download")
def download():
    body = request.json or {}
    url = body.get("url", "").strip()
    kind = body.get("type", "video")
    quality = body.get("quality", "best")
    if not url:
        return jsonify(error="دخل الرابط عافاك"), 400

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = dict(status="starting", percent=0, speed="", eta="", title="",
                            file=None, error=None, created=time.time())
    threading.Thread(target=run_job, args=(job_id, url, kind, quality), daemon=True).start()
    return jsonify(job_id=job_id)


def run_job(job_id: str, url: str, kind: str, quality: str):
    job = JOBS[job_id]

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            job.update(status="downloading",
                       percent=round(done * 100 / total, 1) if total else job["percent"],
                       speed=(d.get("_speed_str") or "").strip(),
                       eta=(d.get("_eta_str") or "").strip())
        elif d["status"] == "finished":
            job.update(status="processing", percent=100)

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": str(DOWNLOAD_DIR / f"{job_id}.%(ext)s"),
        "progress_hooks": [hook],
    }

    if kind == "audio":
        audio_fmt = quality if quality in ("mp3", "m4a", "wav", "opus") else "mp3"
        opts.update(
            format="bestaudio/best",
            postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": audio_fmt,
                             "preferredquality": "192"}],
        )
    else:
        h = f"[height<={int(quality)}]" if str(quality).isdigit() else ""
        opts.update(
            format=f"bv*{h}[ext=mp4]+ba[ext=m4a]/bv*{h}+ba/b{h}/b",
            merge_output_format="mp4",
        )

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=True)
        files = sorted(DOWNLOAD_DIR.glob(f"{job_id}.*"), key=lambda p: p.stat().st_size, reverse=True)
        files = [f for f in files if not f.name.endswith((".part", ".ytdl"))]
        if not files:
            raise RuntimeError("ما لقيناش الملف من بعد التحميل")
        job.update(status="done", percent=100, file=files[0].name,
                   title=safe_name(data.get("title")))
    except Exception as e:  # noqa: BLE001
        job.update(status="error", error=clean_error(e))


def clean_error(e: Exception) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
    low = msg.lower()
    if "unsupported url" in low:
        return "هاد الرابط ما مدعومش"
    if "audio codec" in low:
        return "هاد الفيديو ما فيهش الصوت"
    if "not a bot" in low:
        return "يوتيوب بلوكا هاد السيرفر. جرب من البيسي (start.bat) ولا جرب منصة أخرى"
    if "private" in low or "login" in low or "cookies" in low:
        return "هاد الفيديو خاص ولا خاصو تسجيل الدخول"
    return msg[:300]


@app.get("/api/progress/<job_id>")
def progress(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify(error="ما كايناش هاد العملية"), 404
    return jsonify({k: v for k, v in job.items() if k != "created"})


@app.get("/api/file/<job_id>")
def get_file(job_id):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify(error="الملف ما واجدش"), 404
    path = DOWNLOAD_DIR / job["file"]
    ext = path.suffix
    return send_file(path, as_attachment=True, download_name=f"{job['title']}{ext}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  ✅ التطبيق خدام: http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
