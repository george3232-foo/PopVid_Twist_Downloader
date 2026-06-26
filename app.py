#!/usr/bin/env python3
"""PopVid Downloader — Flask backend with hierarchical branch discovery."""

from flask import Flask, request, jsonify, render_template, Response, send_file, stream_with_context
import requests as http
import json
import re
import time
import tempfile
import subprocess
import uuid
from pathlib import Path
from urllib.parse import unquote

app = Flask(__name__)

TIMEOUT = 15
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
WORK_DIR = Path(tempfile.mkdtemp(prefix="popvid_"))


def extract_meme_id(url):
    url = unquote(url)
    for pat in [r"popvid\.ai/(?:vid|watch|meme)/([^/\?#]+)", r"popvid\.ai/([a-zA-Z0-9_]{15,})\??"]:
        m = re.search(pat, url)
        if m:
            return m.group(1).split("?")[0].split("#")[0].rstrip("/")
    raise ValueError(f"Could not extract meme ID from: {url}")


def cdn_exists(url):
    try:
        r = http.head(url, headers=UA, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code != 200:
            return False
        cl = int(r.headers.get("Content-Length", 0))
        if cl < 100:
            r2 = http.get(url, headers=UA, timeout=TIMEOUT, stream=True)
            first = next(r2.iter_content(256), b"")
            r2.close()
            return len(first) > 100
        return True
    except http.RequestException:
        return False


def discover_original(meme_id):
    base = f"https://cdn.popvid.ai/{meme_id}"
    for url, label in [
        (f"{base}/animation_download_{meme_id}.mp4", "Original (Download Quality)"),
        (f"{base}/animationPro_{meme_id}.mp4", "Original (Pro)"),
        (f"{base}/animation_gallery_{meme_id}.mp4", "Original (Gallery)"),
        (f"{base}/{meme_id}.mp4", "Original"),
    ]:
        if cdn_exists(url):
            return [(url, label)]
    return []


def discover_parts(meme_id, max_parts=20):
    base = f"https://cdn.popvid.ai/{meme_id}"
    results, misses = [], 0
    for n in range(1, max_parts + 1):
        found = False
        for url, label in [
            (f"{base}/{meme_id}_part{n}.mp4", f"Part {n}"),
            (f"{base}/animationPro_{meme_id}_part{n}.mp4", f"Part {n} (Pro)"),
            (f"{base}/animation_download_{meme_id}_part{n}.mp4", f"Part {n} (Download)"),
        ]:
            if cdn_exists(url):
                results.append((url, label))
                misses = 0
                found = True
                break
        if not found:
            misses += 1
            if misses >= 3:
                break
        time.sleep(0.1)
    return results


def discover_story(meme_id, story_node_id=None):
    """Returns list of (url, label, node_id, subtree_height) tuples."""
    results = []
    story_node_id = story_node_id or meme_id
    try:
        r = http.get(
            f"https://popvid.ai/api/v3/meme/{meme_id}/story/{story_node_id}",
            headers=UA, timeout=TIMEOUT
        )
        if r.status_code != 200:
            return results
        for i, node in enumerate(r.json().get("storyNodes", [])):
            if node.get("status") != "completed":
                continue
            vid = node.get("enhancedVideoUrl") or node.get("videoUrl")
            if vid:
                prompt = node.get("textPrompt", "")
                label = f"Continuation {i + 1}"
                if prompt:
                    label += f" — {prompt[:60]}"
                results.append((vid, label, node.get("id", ""), node.get("subtreeHeight", 0)))
    except (http.RequestException, json.JSONDecodeError, KeyError):
        pass
    return results


# ── Routes ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/discover", methods=["POST"])
def api_discover():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        meme_id = extract_meme_id(url)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    main_video = None
    for u, label in discover_original(meme_id):
        main_video = {"url": u, "label": label}
        break

    branches = []
    idx = 0
    for u, label in discover_parts(meme_id):
        branches.append({"id": idx, "url": u, "label": label, "category": "part", "node_id": None})
        idx += 1
    for u, label, nid, sth in discover_story(meme_id):
        branches.append({"id": idx, "url": u, "label": label, "category": "story", "node_id": nid, "has_branches": sth > 0})
        idx += 1

    if not main_video and not branches:
        return jsonify({"error": "No video parts found for this URL", "meme_id": meme_id}), 404

    return jsonify({
        "meme_id": meme_id,
        "main_video": main_video,
        "branches": branches,
        "total": len(branches) + (1 if main_video else 0)
    })


@app.route("/api/branches", methods=["POST"])
def api_branches():
    """Discover sub-branches for a given story node ID."""
    node_id = request.json.get("node_id", "").strip()
    meme_id = request.json.get("meme_id", "").strip()
    if not node_id or not meme_id:
        return jsonify({"error": "Both node_id and meme_id required"}), 400

    branches = []
    idx = 0
    for u, label, nid, sth in discover_story(meme_id, node_id):
        branches.append({"id": idx, "url": u, "label": label, "category": "story", "node_id": nid, "has_branches": sth > 0})
        idx += 1

    return jsonify({"node_id": node_id, "branches": branches, "total": len(branches)})


@app.route("/api/proxy")
def proxy_video():
    url = request.args.get("url", "")
    if not url or "popvid" not in url:
        return "Invalid URL", 400
    fwd = dict(UA)
    if "Range" in request.headers:
        fwd["Range"] = request.headers["Range"]
    try:
        r = http.get(url, headers=fwd, stream=True, timeout=30)
        resp_headers = {
            "Content-Type": r.headers.get("Content-Type", "video/mp4"),
            "Accept-Ranges": "bytes",
        }
        for h in ("Content-Length", "Content-Range"):
            if h in r.headers:
                resp_headers[h] = r.headers[h]
        return Response(stream_with_context(r.iter_content(8192)), status=r.status_code, headers=resp_headers)
    except http.RequestException as e:
        return str(e), 502


@app.route("/api/download")
def download_video():
    url = request.args.get("url", "")
    filename = request.args.get("filename", "popvid_video.mp4")
    if not url:
        return "Missing url param", 400
    try:
        r = http.get(url, headers=UA, stream=True, timeout=60)
        r.raise_for_status()
        headers = {
            "Content-Type": "video/mp4",
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if "Content-Length" in r.headers:
            headers["Content-Length"] = r.headers["Content-Length"]
        return Response(stream_with_context(r.iter_content(8192)), status=200, headers=headers)
    except http.RequestException as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/combine", methods=["POST"])
def combine_videos():
    try:
        videos = request.json.get("videos", [])
        if not videos:
            return jsonify({"error": "No videos to combine"}), 400

        job_id = str(uuid.uuid4())[:8]
        job_dir = WORK_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        for i, v in enumerate(videos):
            path = job_dir / f"part_{i:03d}.mp4"
            r = http.get(v["url"], headers=UA, stream=True, timeout=120)
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            paths.append(path)

        if len(paths) == 1:
            output = paths[0]
        else:
            concat_file = job_dir / "concat.txt"
            concat_file.write_text("".join(f"file '{p.name}'\n" for p in paths))
            output = job_dir / f"combined_{job_id}.mp4"
            success = False
            for cmd_extra in [["-c", "copy"], ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"]]:
                result = subprocess.run(
                    ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
                    + cmd_extra + ["-y", str(output)],
                    capture_output=True, text=True, timeout=300,
                )
                if result.returncode == 0:
                    success = True
                    break
            if not success:
                return jsonify({"error": f"ffmpeg failed: {result.stderr[:300]}"}), 500

        return jsonify({
            "download_url": f"/api/combined/{job_id}",
            "filename": f"popvid_combined_{job_id}.mp4",
            "size": output.stat().st_size,
        })
    except FileNotFoundError:
        return jsonify({"error": "ffmpeg not installed. Install it to combine videos, or download individually."}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "ffmpeg timed out — videos may be too large to combine"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/combined/<job_id>")
def download_combined(job_id):
    if not re.match(r"^[a-f0-9]{8}$", job_id):
        return "Invalid ID", 400
    path = WORK_DIR / job_id / f"combined_{job_id}.mp4"
    if not path.exists():
        path = WORK_DIR / job_id / "part_000.mp4"
    if not path.exists():
        return "Not found", 404
    return send_file(str(path), as_attachment=True, download_name=f"popvid_combined_{job_id}.mp4")


if __name__ == "__main__":
    import shutil
    if not shutil.which("ffmpeg"):
        print("\n⚠  ffmpeg not found! Combining videos will fail.")
        print("   Install: sudo apt install ffmpeg  (or brew install ffmpeg on mac)\n")
    print(f"PopVid Twist Downloader running")
    print(f"Temp dir: {WORK_DIR}")
    print(f"Open: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
