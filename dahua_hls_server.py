import os
import signal
import subprocess
import threading
from pathlib import Path

from flask import Flask, Response, send_from_directory

# =====================
# Konfigurasi dasar
# =====================
# RTSP Dahua biasanya seperti:
# rtsp://user:password@ip_kamera:554/cam/realmonitor?channel=1&subtype=0
# Kita pakai dua kamera: Room 1 dan Room 2
RTSP_ROOM1_URL = os.environ.get(
    "DAHUA_RTSP_ROOM1_URL",
    "rtsp://erispro:Erispro123%23@10.39.122.100:554/cam/realmonitor?channel=1&subtype=0",
)
RTSP_ROOM2_URL = os.environ.get(
    "DAHUA_RTSP_ROOM2_URL",
    "rtsp://erispro:Erispro123%23@10.39.122.101:554/cam/realmonitor?channel=1&subtype=0",
)

BASE_DIR = Path(__file__).resolve().parent
HLS_DIR = Path(os.environ.get("HLS_DIR", BASE_DIR / "hls"))
HLS_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")

# Konfigurasi dua stream (Room 1 dan Room 2)
streams: dict[str, dict] = {
    "room1": {
        "label": "Room 1",
        "rtsp_url": RTSP_ROOM1_URL,
        "hls_dir": HLS_DIR / "room1",
        "process": None,
        "lock": threading.Lock(),
    },
    "room2": {
        "label": "Room 2",
        "rtsp_url": RTSP_ROOM2_URL,
        "hls_dir": HLS_DIR / "room2",
        "process": None,
        "lock": threading.Lock(),
    },
}

for s in streams.values():
    Path(s["hls_dir"]).mkdir(parents=True, exist_ok=True)


def build_ffmpeg_cmd(rtsp_url: str, hls_dir: Path) -> list[str]:
    """Bangun perintah FFmpeg untuk konversi RTSP → HLS."""
    hls_playlist = hls_dir / "stream.m3u8"
    hls_segments = hls_dir / "segment_%03d.ts"

    cmd = [
        FFMPEG_BIN,
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-max_delay",
        "500000",
        "-c:v",
        "copy",  # gunakan "libx264" jika ingin selalu re-encode ke H.264
        "-c:a",
        "aac",
        "-f",
        "hls",
        "-hls_time",
        "2",
        "-hls_list_size",
        "5",
        "-hls_flags",
        "delete_segments+independent_segments",
        "-hls_segment_filename",
        str(hls_segments),
        str(hls_playlist),
    ]
    return cmd


def _start_ffmpeg_stream(key: str) -> None:
    """Jalankan FFmpeg untuk satu stream (room1/room2)."""
    stream = streams[key]
    lock: threading.Lock = stream["lock"]

    with lock:
        proc: subprocess.Popen | None = stream["process"]
        if proc is not None and proc.poll() is None:
            print(f"FFmpeg untuk {stream['label']} sudah berjalan.")
            return

        cmd = build_ffmpeg_cmd(stream["rtsp_url"], stream["hls_dir"])
        print(f"Menjalankan FFmpeg untuk {stream['label']} dengan perintah:")
        print(" ", " ".join(cmd))

        try:
            proc = subprocess.Popen(cmd)
        except FileNotFoundError:
            print(
                "ERROR: ffmpeg tidak ditemukan. Install ffmpeg atau set env FFMPEG_BIN "
                "ke path biner ffmpeg yang benar."
            )
            stream["process"] = None
            return

        stream["process"] = proc

    monitor_thread = threading.Thread(target=_monitor_ffmpeg_stream, args=(key,), daemon=True)
    monitor_thread.start()


def _monitor_ffmpeg_stream(key: str) -> None:
    """Pantau proses FFmpeg untuk satu stream dan log ketika berhenti."""
    stream = streams[key]
    lock: threading.Lock = stream["lock"]

    with lock:
        proc: subprocess.Popen | None = stream["process"]

    if proc is None:
        return

    exit_code = proc.wait()
    print(f"FFmpeg untuk {stream['label']} berhenti dengan kode exit {exit_code}")


def start_ffmpeg() -> None:
    """Start FFmpeg untuk semua stream yang dikonfigurasi."""
    for key in streams.keys():
        _start_ffmpeg_stream(key)


def stop_ffmpeg() -> None:
    """Hentikan semua proses FFmpeg dengan aman."""
    for key, stream in streams.items():
        lock: threading.Lock = stream["lock"]
        with lock:
            proc: subprocess.Popen | None = stream["process"]

        if proc is not None and proc.poll() is None:
            print(f"Menghentikan FFmpeg untuk {stream['label']}...")
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

        with lock:
            stream["process"] = None


app = Flask(__name__)


@app.route("/")
def index() -> Response:
    """Halaman web untuk menampilkan dua stream CCTV (Room 1 & Room 2)."""
    html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Cold Storage CCTV</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {
        --bg: #020617;
        --panel: #0f172a;
        --border: #1f2937;
        --accent: #38bdf8;
        --text: #e5e7eb;
        --text-muted: #9ca3af;
      }
      * {
        box-sizing: border-box;
      }
      body {
        margin: 0;
        padding: 16px;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: radial-gradient(circle at top, #172554 0, var(--bg) 45%, #020617 100%);
        color: var(--text);
        min-height: 100vh;
      }
      .shell {
        max-width: 1200px;
        margin: 0 auto;
      }
      header {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 16px;
      }
      .title-block {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      h1 {
        margin: 0;
        font-size: 1.4rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }
      .subtitle {
        font-size: 0.85rem;
        color: var(--text-muted);
      }
      .badge-bar {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .badge {
        padding: 4px 10px;
        border-radius: 999px;
        border: 1px solid rgba(148, 163, 184, 0.3);
        background: rgba(15, 23, 42, 0.85);
        font-size: 0.75rem;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: var(--text-muted);
      }
      .badge-dot {
        width: 7px;
        height: 7px;
        border-radius: 999px;
        background: #22c55e;
        box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.35);
      }
      .badge-label {
        text-transform: uppercase;
        letter-spacing: 0.1em;
      }
      .grid {
        display: flex;
        flex-direction: column;
        gap: 16px;
        align-items: stretch;
      }
      .card {
        position: relative;
        background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.08), rgba(15, 23, 42, 0.96));
        border-radius: 16px;
        padding: 12px 12px 16px;
        border: 1px solid rgba(15, 23, 42, 0.9);
        box-shadow: 0 18px 45px rgba(15, 23, 42, 0.9);
        backdrop-filter: blur(16px);
      }
      .card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 8px;
      }
      .card-title {
        font-size: 0.95rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .card-sub {
        font-size: 0.7rem;
        color: var(--text-muted);
      }
      .pill {
        padding: 2px 8px;
        border-radius: 999px;
        border: 1px solid rgba(148, 163, 184, 0.4);
        font-size: 0.7rem;
        color: var(--text-muted);
      }
      video {
        width: 100%;
        height: auto;
        background: #020617;
        border-radius: 10px;
        border: 1px solid rgba(15, 23, 42, 1);
      }
      .note {
        font-size: 0.75rem;
        color: var(--text-muted);
        margin-top: 6px;
      }
      .footer {
        margin-top: 20px;
        font-size: 0.7rem;
        color: var(--text-muted);
        text-align: right;
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <header>
        <div class="title-block">
          <h1>Cold Storage CCTV</h1>
          <div class="subtitle">Monitoring visual ruang penyimpanan — Room 1 &amp; Room 2</div>
        </div>
        <div class="badge-bar">
          <div class="badge"><span class="badge-dot"></span><span class="badge-label">Live Dashboard</span></div>
          <div class="badge">RTSP → HLS via FFmpeg</div>
        </div>
      </header>

      <div class="grid">
        <section class="card">
          <div class="card-header">
            <div>
              <div class="card-title">Room 1</div>
              <div class="card-sub">Kamera utama cold storage</div>
            </div>
            <div class="pill">STREAM 01</div>
          </div>
          <video id="video-room1" controls autoplay muted playsinline></video>
          <div class="note">Jika stream tidak muncul, cek koneksi RTSP Room 1 &amp; status FFmpeg.</div>
        </section>

        <section class="card">
          <div class="card-header">
            <div>
              <div class="card-title">Room 2</div>
              <div class="card-sub">Kamera tambahan cold storage</div>
            </div>
            <div class="pill">STREAM 02</div>
          </div>
          <video id="video-room2" controls autoplay muted playsinline></video>
          <div class="note">Jika stream tidak muncul, cek koneksi RTSP Room 2 &amp; status FFmpeg.</div>
        </section>
      </div>

      <div class="footer">Selene IoT — Cold Storage CCTV Monitor</div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <script>
      function setupHls(videoId, src) {
        const video = document.getElementById(videoId);
        if (!video) return;

        if (video.canPlayType('application/vnd.apple.mpegurl')) {
          video.src = src;
        } else if (window.Hls && Hls.isSupported()) {
          const hls = new Hls({
            lowLatencyMode: true,
            backBufferLength: 30,
          });
          hls.loadSource(src);
          hls.attachMedia(video);
        } else {
          video.outerHTML = '<p>Browser tidak mendukung HLS. Coba Chrome/Firefox (desktop) atau Safari.</p>';
        }
      }

      setupHls('video-room1', '/hls/room1/stream.m3u8');
      setupHls('video-room2', '/hls/room2/stream.m3u8');
    </script>
  </body>
</html>"""
    return Response(html, mimetype="text/html")


@app.route("/hls/<path:filename>")
def hls_files(filename: str):
    """Melayani file HLS (.m3u8 dan .ts)."""
    # filename sudah termasuk subfolder room1/room2
    return send_from_directory(HLS_DIR, filename)


def run_server() -> None:
    """Start FFmpeg dan jalankan web server Flask."""
    start_ffmpeg()

    try:
        app.run(host="0.0.0.0", port=8000, debug=False)
    finally:
        stop_ffmpeg()


if __name__ == "__main__":
    print("RTSP Room 1:", RTSP_ROOM1_URL)
    print("RTSP Room 2:", RTSP_ROOM2_URL)
    print("Folder HLS:", HLS_DIR)
    run_server()
