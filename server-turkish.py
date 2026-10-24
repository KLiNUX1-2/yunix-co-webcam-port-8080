from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import ssl
import os
import json
import socket

HOST = "0.0.0.0"
PORT = 8080
latest_frame = b""
MAX_FRAME_SIZE = 2_000_000

class VXCHandler(BaseHTTPRequestHandler):
    def send_text(self, text, content_type="text/html; charset=utf-8"):
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        global latest_frame
        path = urlparse(self.path).path

        if path == "/capture":
            return self.send_text(CAPTURE_PAGE)

        if path == "/frame.jpg":
            if not latest_frame:
                self.send_error(404, "Henüz görüntü yok")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(latest_frame)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(latest_frame)
            return

        if path == "/status":
            data = json.dumps({
                "camera_ready": bool(latest_frame)
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        with open("index.html", "r", encoding="utf-8") as f:
            self.send_text(f.read())

    def do_POST(self):
        global latest_frame
        if urlparse(self.path).path != "/frame":
            self.send_error(404)
            return

        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > MAX_FRAME_SIZE:
            self.send_error(413, "Görüntü boyutu uygun değil")
            return

        frame = self.rfile.read(size)
        if not frame.startswith(b"\xff\xd8"):
            self.send_error(400, "JPEG görüntüsü gerekli")
            return

        latest_frame = frame
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        print("[YUNiX]", fmt % args)

DASHBOARD_PAGE = r"""
<!doctype html>
<html lang="tr">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VXC IP Webcam 0.1</title>
<style>
body{font:16px Arial;background:#101827;color:#fff;margin:0;padding:20px}
main{max-width:750px;margin:auto} .panel{background:#1d293b;padding:18px;
border-radius:14px;margin:14px 0} img{width:100%;border-radius:10px;
background:#080d14;min-height:180px;object-fit:contain}
a,button{color:white;background:#2563eb;padding:12px 16px;border:0;
border-radius:8px;text-decoration:none;display:inline-block}
small{color:#cbd5e1}
</style>
<main>
<header>
<a href="index.html">
<img src="https://i.hizliresim.com/ao9mkgzhtw5pjczfj6kv.png"
<h1> YUNiX IP Webcam</h1>
<p>Sürüm 0.1 · Web kontrol paneli</p>
<div class="panel">
<h2>Canlı görüntü</h2>
<img id="cam" alt="Kamera bekleniyor">
<p id="status">Kamera bağlantısı bekleniyor...</p>
<button onclick="refreshNow()">Görüntüyü yenile</button>
</div>
<div class="panel">
<h3>Kamera kurulumu</h3>
<p>Bu sayfayı tabletin kendisinde aç:</p>
<a href="/capture">Kamerayı başlat</a>
<p><small>Kamera iznini tarayıcı sorarsa izin ver.</small></p>
</div>
</main>
<script>
const img=document.getElementById("cam");
const statusText=document.getElementById("status");
function refreshNow(){
 img.src="/frame.jpg?t="+Date.now();
}
img.onerror=()=>{statusText.textContent="Görüntü bekleniyor. Tablette kamerayı başlat.";};
img.onload=()=>{statusText.textContent="Görüntü alınıyor.";};
setInterval(refreshNow,500);
refreshNow();
</script>
</html>
"""

CAPTURE_PAGE = r"""
<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VXC Kamera Kaynağı</title>
<style>
body{font:16px Arial;background:#101827;color:white;padding:18px}
video{width:100%;max-width:600px;background:#000;border-radius:12px}
button,a{padding:12px;background:#2563eb;color:white;border:0;border-radius:8px;text-decoration:none;display:inline-block;margin:5px 0}
</style>
</head>
<body>
<h1>VXC Kamera Kaynağı</h1>
<p>Kamera izni ver ve başlat düğmesine bas.</p>
<video id="video" autoplay playsinline muted></video>
<p id="msg">Kamera henüz başlamadı.</p>
<button id="start" type="button">Kamerayı başlat</button>
<p><a href="/">Kontrol paneline dön</a></p>
<canvas id="canvas" hidden></canvas>
<button id="downloadFrame">Video karesini indir</button>
<script>
const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const msg = document.getElementById("msg");
document.getElementById("downloadFrame").onclick = function() {
  if (!video.videoWidth) {
    msg.textContent = "Önce kamerayı başlat!";
    return;
  }

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;

  canvas.getContext("2d").drawImage(video, 0, 0);

  const link = document.createElement("a");
  link.download = "videoeym.jpg";
  link.href = canvas.toDataURL("image/jpeg", 0.9);
  link.click();

  msg.textContent = "Video karesi indirildi!";
};


let running = false;

document.getElementById("start").onclick = async function() {
  msg.textContent = "Başlat düğmesine basıldı!";
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Kamera için Chrome'da localhost veya HTTPS kullan.");
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {facingMode: "environment"},
      audio: false
    });
    video.srcObject = stream;
    await video.play();
    running = true;
    msg.textContent = "Kamera çalışıyor.";
    sendFrame();
  } catch (e) {
    msg.textContent = "Kamera açılamadı: " + e.message;
  }
};

async function sendFrame() {
  if (!running) return;
  try {
    if (video.readyState >= 2 && video.videoWidth > 0) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d").drawImage(video, 0, 0);
      const blob = await new Promise(resolve =>
        canvas.toBlob(resolve, "image/jpeg", 0.7)
      );
      if (blob) {
        await fetch("/frame", {
          method: "POST",
          headers: {"Content-Type": "image/jpeg"},
          body: blob
        });
      }
    }
  } catch (e) {
    msg.textContent = "Görüntü gönderilemedi: " + e.message;
  }
  if (running) setTimeout(sendFrame, 500);
}
</script>
</body>
</html>
"""

def get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "TABLET_IP_ADRESI"
    finally:
        sock.close()

if __name__ == "__main__":
    print("================================")
    print(" Yunix Co Webcam Port 8080 0.2")
    print("================================")
    print("Tablet kamera sayfasi:")
    print("http://127.0.0.1:8443/capture")
    print("Kontrol paneli:")
    print("http://" + get_local_ip() + ":8080")
    print("Durdurmak icin CTRL+C yerine Termux'ta Ctrl+C tusunu kullan.")
    server = HTTPServer(("0.0.0.0", 8443),VXCHandler)

cert_file = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "cert", "server.crt"
)
key_file = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "cert", "server.key"
)

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile=cert_file, keyfile=key_file)
server.socket = context.wrap_socket(server.socket, server_side=True)

print("[YUNiX] HTTPS sunucusu çalışıyor!")
print("[YUNiX] https://127.0.0.1:8080")
server.serve_forever()
