#!/usr/bin/env bash
# Prépare une session vierge pour le montage : dépendances Python + modèle de transcription (Whisper small, via npm).
set -e
pip install --break-system-packages -q faster-whisper num2words numpy pillow 2>&1 | grep -v WARNING || true
command -v ffmpeg >/dev/null || { echo "ffmpeg manquant"; exit 1; }
M=${WHISPER_MODEL:-/tmp/wmodel}
if [ ! -s "$M/model.bin" ]; then
  T=$(mktemp -d); cd "$T"
  for i in 0 1 2 3; do npm pack --silent @skillninja/shortmovie-telop-model-p$i >/dev/null; done
  for f in *.tgz; do mkdir -p "x_${f%.tgz}"; tar xzf "$f" -C "x_${f%.tgz}"; done
  mkdir -p "$M"; P=$(ls -d x_*p0*)/package
  cp $P/config.json $P/preprocessor_config.json $P/tokenizer.json $P/vocabulary.json "$M/"
  cat x_*p0*/package/model.bin.part0 x_*p1*/package/model.bin.part1 x_*p2*/package/model.bin.part2 x_*p3*/package/model.bin.part3 > "$M/model.bin"
  echo "attendu : $(cat $P/model.sha256)"; sha256sum "$M/model.bin"
fi
echo "Prêt."
