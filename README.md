# PopVid Twist Downloader

A local web app for discovering and downloading PopVid.ai video branches (twists). Videos on PopVid can have nested story continuations — branches within branches. This tool discovers the full tree and lets you navigate, preview, and download any path through it.

![Python](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Hierarchical branch discovery** — finds all nested story continuations, no matter how deep
- **Tree navigation UI** — drill into branches level by level, go back to try different paths
- **Live path preview** — selected videos play in sequence at the top so you can preview before downloading
- **Single or combined download** — download individual clips or combine your entire selected path into one file
- **No auth required** — uses public PopVid API endpoints

## How It Works

PopVid videos can have "twists" — story continuations created by users. Each twist can itself have further twists, forming a tree. The app queries PopVid's story API (`/api/v3/meme/{id}/story/{node_id}`) to walk this tree on demand as you navigate.

## Quick Start

### Prerequisites

- **Python 3.8+**
- **ffmpeg** (optional — only needed to combine multiple videos into one file)

### Install & Run

```bash
git clone https://github.com/george3232-foo/PopVid_Twist_Downloader.git
cd PopVid_Twist_Downloader

pip install -r requirements.txt

python3 app.py
```

Open **http://localhost:5000** in your browser.

### Usage

1. Paste a PopVid URL (e.g. `https://popvid.ai/vid/your_video_id`)
2. Click **Discover** — the main video and its direct branches appear
3. Click a branch to select it — it gets added to your path preview at the top
4. If that branch has sub-branches, they appear in the grid below
5. Keep drilling down, or click **Back** to try a different path
6. When satisfied with the preview, click **Download Path**

### Installing ffmpeg (optional)

Only needed if you want to combine multiple branch videos into a single file.

```bash
# Debian/Ubuntu/Kali
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

Without ffmpeg, you can still download individual branch videos — just not combine them.

## Project Structure

```
PopVid_Twist_Downloader/
├── app.py              # Flask backend — discovery, proxy, combine
├── templates/
│   └── index.html      # Single-page UI
├── requirements.txt    # Python dependencies
└── README.md
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the web UI |
| `/api/discover` | POST | Discovers main video + direct branches for a PopVid URL |
| `/api/branches` | POST | Discovers sub-branches for a story node |
| `/api/proxy` | GET | Proxies video through local server (bypasses CORS) |
| `/api/download` | GET | Downloads a single video as attachment |
| `/api/combine` | POST | Combines multiple videos with ffmpeg |
| `/api/combined/<id>` | GET | Serves a combined video file |

## How Discovery Works

1. **Original clip** — probes CDN for the main video in multiple quality variants
2. **Story nodes** — queries `/api/v3/meme/{meme_id}/story/{node_id}` for twist continuations
3. Each story node with `subtreeHeight > 0` has further branches — discovered on demand when you click into it

### CDN URL Patterns

| Type | Pattern |
|------|---------|
| Download quality | `cdn.popvid.ai/{id}/animation_download_{id}.mp4` |
| Pro quality | `cdn.popvid.ai/{id}/animationPro_{id}.mp4` |
| Gallery quality | `cdn.popvid.ai/{id}/animation_gallery_{id}.mp4` |
| Story node | `cdn.popvid.ai/{node_id}/enhanced_{node_id}.mp4` |

## License

MIT
