#!/usr/bin/env bash
# GalleryForge Web starten (Flask, Port 15001). Idempotent: startet nur,
# wenn der Port frei ist. Log: ~/galleryforge/logs/web.log
PORT=15001
if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
  echo "GalleryForge läuft bereits (Port ${PORT})."
else
  mkdir -p /home/olaf/galleryforge/logs
  setsid /home/olaf/galleryforge/.venv/bin/python /home/olaf/galleryforge/server.py >>/home/olaf/galleryforge/logs/web.log 2>&1
  sleep 3
  if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
    echo "GalleryForge gestartet."
  else
    echo "FEHLER: Start fehlgeschlagen – siehe ~/galleryforge/logs/web.log"
    exit 1
  fi
fi
echo "URL (WLAN/VPN): http://192.168.1.131:${PORT}/"
echo "WSL-IP: $(hostname -I | awk '{print $1}')  (nur nötig, falls Handy nicht rankommt: Portproxy-Ziel prüfen)"
echo "Token: ~/galleryforge/.env (GF_TOKEN)"
