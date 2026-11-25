#!/usr/bin/env python3
"""Les Pingouins — montage automatique des vidéos anime de FC Pierrelaye CDM.

Commandes :
  python3 pingouins.py episode episodes/ep02/episode.json   # voix + images -> MP4 vertical 1080x1920
  python3 pingouins.py short   episodes/ep02/short_mer.json # format court sans voix (musique + textes)
  python3 pingouins.py cover   episodes/ep02/episode.json   # couverture du Reel

Le fichier JSON décrit les plans (voir README.md). Les chemins d'images et de voix sont relatifs au dossier du JSON,
ou commencent par « assets/ » pour les fichiers du kit.
"""
import os, sys, json, re, math, random, subprocess, unicodedata, difflib, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont

KIT = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, SR = 1080, 1920, 30, 44100
ANTON = os.path.join(KIT, 'assets/fonts/anton.woff')
BARLOW = os.path.join(KIT, 'assets/fonts/barlow-800.woff')
YEL, GOLD, WHITE = (246, 235, 60), (232, 184, 75), (250, 250, 245)
WHISPER = os.environ.get('WHISPER_MODEL', '/tmp/wmodel')
_FONTS = {}


def font(path, size):
    k = (path, size)
    if k not in _FONTS: _FONTS[k] = ImageFont.truetype(path, size)
    return _FONTS[k]


def resolve(base, p):
    if p.startswith('assets/'): return os.path.join(KIT, p)
    return p if os.path.isabs(p) else os.path.join(base, p)


# ------------------------------------------------------------------ texte à l'écran
def text_center(d, y, text, f, fill, stroke=6):
    tw = d.textlength(text, font=f)
    d.text(((W - tw) / 2, y), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))


def wrap(d, text, f, maxw):
    words, lines, cur = text.split(' '), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if d.textlength(t, font=f) <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines


def speaker_of(line):
    """« Tom : réplique » -> ('Tom', 'réplique'). Un seul mot avant « : », avec majuscule."""
    if ' : ' in line:
        sp, rest = line.split(' : ', 1)
        if re.fullmatch(r"[A-ZÉÈ][\wéèêëàâîïôöûüç'-]{1,14}", sp): return sp, rest
    return None, line


def chunks_of(line):
    """Une ligne du script -> morceaux de 2 à 4 mots : [(type, interlocuteur, texte)]. « !! texte » = gros texte central."""
    if line.startswith('!! '):
        sp, t = speaker_of(line[3:])
        return [('big', sp, t)]
    sp, line = speaker_of(line)
    line = (line.replace(' :', ' :').replace(' ?', ' ?').replace(' !', ' !'))
    line = re.sub(r'(\d+) h (\d+)', r'\1h\2', line)
    phrases = [p.strip() for p in re.split(r'(?<=[,.…:])\s+', line) if p.strip()]
    merged = []
    for ph in phrases:
        if merged and len((merged[-1] + ' ' + ph).split()) <= 4 and len(merged[-1] + ph) < 26: merged[-1] += ' ' + ph
        else: merged.append(ph)
    out = []
    for ph in merged:
        words = ph.split()
        g = min(len(words), max(1, math.ceil(len(words) / 4), math.ceil(len(ph) / 27))); i = 0
        for k in range(g):
            n = round((len(words) - i) / (g - k)); out.append(' '.join(words[i:i + n])); i += n
    return [('dlg' if sp else 'sub', sp, t) for t in out]


def dur_of(kind, text):
    if kind == 'big': return 1.25 if len(text) < 8 else 1.4
    d = 0.32 * len(text.split()) + 0.33
    if text[-1] in '….': d += 0.25
    return max(0.85, d)


def build(lines):
    items = []
    for ln in lines:
        cs = chunks_of(ln)
        for i, (k, sp, t) in enumerate(cs):
            items.append([k, sp, t, dur_of(k, t) + (0.2 if i == len(cs) - 1 else 0)])
    return items


def draw_sub(fr, k, sp, t):
    d = ImageDraw.Draw(fr)
    if k == 'big':
        f = font(ANTON, 200 if len(t) <= 6 else 130)
        if sp: text_center(d, 650, sp.upper() + ' :', font(BARLOW, 60), WHITE)
        text_center(d, 760, t, f, YEL, stroke=12); return
    FS = font(BARLOW, 66)
    txt = (sp + ' : ' + t) if sp else t
    lines = wrap(d, txt, FS, W - 240)
    y0 = 1330 - (len(lines) - 1) * 40
    for i, ln in enumerate(lines):
        y = y0 + i * 80
        if sp and i == 0 and ln.startswith(sp + ' :'):
            name = sp + ' : '; x = (W - d.textlength(ln, font=FS)) / 2
            d.text((x, y), name, font=FS, fill=WHITE, stroke_width=6, stroke_fill=(0, 0, 0))
            d.text((x + d.textlength(name, font=FS), y), ln[len(name):], font=FS, fill=YEL, stroke_width=6, stroke_fill=(0, 0, 0))
        else: text_center(d, y, ln, FS, YEL)


def cover_img(path):
    src = Image.open(path).convert('RGB')
    s = max(W / src.width, H / src.height)
    src = src.resize((round(src.width * s), round(src.height * s)), Image.LANCZOS)
    l, t = (src.width - W) // 2, (src.height - H) // 2
    return src.crop((l, t, l + W, t + H))



def video_frames(path, nfr, o):
    """Lit un clip (Gemini/Veo…) recadré en 1080x1920. o : clip [début, fin] en s, speed (0.5 = ralenti)."""
    st, en = (o.get('clip') or [0, None]) + [None] * (2 - len(o.get('clip') or [0, None]))
    sp = o.get('speed', 1.0)
    vf = f'setpts=PTS/{sp},fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}'
    cmd = ['ffmpeg', '-v', 'error', '-ss', str(st)] + (['-to', str(en)] if en else []) + ['-i', path, '-an', '-vf', vf,
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    fs = [Image.frombytes('RGB', (W, H), raw[i:i + W * H * 3]) for i in range(0, len(raw) - W * H * 3 + 1, W * H * 3)]
    if not fs: raise SystemExit('clip illisible : ' + path)
    return [fs[min(i, len(fs) - 1)] for i in range(nfr)]


def speed_lines(seed, cx=.5, cy=.45, n=70, inner=.32):
    """Traits de vitesse façon manga, rayonnants depuis (cx, cy)."""
    r = random.Random(seed); im = Image.new('RGBA', (W, H)); d = ImageDraw.Draw(im)
    R = math.hypot(W, H)
    for _ in range(n):
        a = r.uniform(0, 2 * math.pi); r0 = R * r.uniform(inner, inner + .18); wd = r.uniform(.004, .012)
        x0, y0 = cx * W + math.cos(a) * r0, cy * H + math.sin(a) * r0
        pts = [(x0, y0), (cx * W + math.cos(a - wd) * R, cy * H + math.sin(a - wd) * R),
               (cx * W + math.cos(a + wd) * R, cy * H + math.sin(a + wd) * R)]
        d.polygon(pts, fill=(255, 255, 255, r.randint(120, 210)))
    return im


def draw_big_anim(fr, sp, t, age):
    """Gros texte qui claque : arrive grossi, se pose en 5 images, léger tremblement."""
    lay = Image.new('RGBA', (W, H)); d = ImageDraw.Draw(lay)
    f = font(ANTON, 200 if len(t) <= 6 else 130)
    if sp: text_center(d, 650, sp.upper() + ' :', font(BARLOW, 60), WHITE)
    text_center(d, 760, t, f, YEL, stroke=12)
    s = 1 + 0.7 * max(0, 1 - age / 5) ** 2
    if s > 1.001:
        big = lay.resize((round(W * s), round(H * s)), Image.BILINEAR)
        l, tp = (big.width - W) // 2, round((big.height - H) * 0.45)
        lay = big.crop((l, tp, l + W, tp + H))
    jx = random.Random(age).randint(-8, 8) if age < 8 else 0
    fr.alpha_composite(lay, (jx, 0))


SHOTS = [(1.00, .5, .5), (1.32, .5, .36), (1.22, .5, .58), (1.40, .5, .42)]


def render_plan(job):
    """job : image, items [type, interlocuteur, texte, début_s], total_s, opts, out, idx, first, last."""
    o = job['opts']; items = job['items']; nfr = round(job['total'] * FPS); idx = job['idx']
    starts = [0] + [round(it[3] * FPS) for it in items[1:]]
    vids = video_frames(job['video'], nfr, o) if job.get('video') else None
    base = cover_img(job['image']) if not vids else None
    lines_cache = {}
    grad = Image.new('L', (1, H))
    for y in range(H): grad.putpixel((0, y), int(140 * max(0, (y - H * .6) / (H * .4)) ** 1.4))
    shade = Image.new('RGBA', (W, H), (0, 0, 0, 255)); shade.putalpha(grad.resize((W, H)))
    nshots = 1 if (o.get('n') or vids) else max(1, round(job['total'] / 2.4)); shot_len = nfr / nshots
    flashes = [starts[i] for i, it in enumerate(items) if it[0] == 'big']
    rnd = random.Random(idx); order = [0] + [1 + ((idx + j) % 3) for j in range(nshots - 1)]
    tmp = job['out'] + '.tmp.mp4'
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                          '-c:v', 'libx264', '-crf', '19', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-r', str(FPS), tmp], stdin=subprocess.PIPE)
    for n in range(nfr):
        si = min(nshots - 1, int(n / shot_len)); z0, cx, cy = SHOTS[order[si]]
        q = (n - si * shot_len) / shot_len
        z = z0 * (1 + (o.get('zoom', 0.06) if nshots == 1 else 0.05) * q)
        if q < 0.12 and si > 0: z *= 1 + 0.05 * (1 - q / 0.12)
        dx = dy = 0
        if o.get('shake'): dx, dy = rnd.uniform(-6, 6), rnd.uniform(-6, 6)
        a = 1 / z; px, py = cx * W + dx, cy * H + dy
        px = min(max(px, W * a / 2), W - W * a / 2); py = min(max(py, H * a / 2), H - H * a / 2)
        k = max(i for i in range(len(starts)) if starts[i] <= n)
        age = n - starts[k]; hit = items[k][0] == 'big' and age < 7
        if hit:  # impact : coup de zoom + secousse
            z *= 1 + 0.10 * (1 - age / 7); r2 = random.Random(n); dx += r2.uniform(-14, 14); dy += r2.uniform(-14, 14)
        src = vids[n] if vids else base
        if vids:
            a = 1 / (1 + 0.10 * (1 - age / 7)) if hit else 1 / (1 + o.get('zoom', 0.0) * q)
            px, py = W / 2 + dx, H / 2 + dy
        fr = src.transform((W, H), Image.AFFINE, (a, 0, px - a * W / 2, 0, a, py - a * H / 2), resample=Image.BILINEAR).convert('RGBA')
        if o.get('lines') or (items[k][0] == 'big' and age < 14):
            key = (n // 2) % 4
            if key not in lines_cache: lines_cache[key] = speed_lines(idx * 10 + key)
            fr.alpha_composite(lines_cache[key])
        fr.alpha_composite(shade)
        if items[k][0] == 'big': draw_big_anim(fr, items[k][1], items[k][2], age)
        else: draw_sub(fr, items[k][0], items[k][1], items[k][2])
        fr = fr.convert('RGB')
        for fs in flashes:
            if fs <= n < fs + 8: fr = Image.blend(fr, Image.new('RGB', (W, H), (255, 255, 255)), 0.8 * (1 - (n - fs) / 8))
        if job.get('first') and n < 12: fr = Image.blend(Image.new('RGB', (W, H)), fr, n / 12)
        if job.get('last') and n > nfr - 20: fr = Image.blend(Image.new('RGB', (W, H)), fr, (nfr - n) / 20)
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    if p.wait() != 0: raise SystemExit('ffmpeg a échoué sur le plan ' + str(idx + 1))
    os.replace(tmp, job['out'])
    return nfr / FPS


# ------------------------------------------------------------------ alignement voix / script
def numword(m):
    from num2words import num2words
    s = m.group(0)
    if re.fullmatch(r'\d+(er|e|ème)', s): return num2words(int(re.match(r'\d+', s).group()), lang='fr', to='ordinal')
    return num2words(int(s), lang='fr')


def norm_tokens(text):
    t = text.replace('’', "'")
    t = re.sub(r'\[[^\]]*\]', ' ', t)
    t = re.sub(r'(\d+)\s*h\s*(\d+)', lambda m: f'{m.group(1)} heures {m.group(2)}', t)
    t = re.sub(r'\d+(?:er|ème|e)?\b', numword, t)
    t = unicodedata.normalize('NFD', t.lower())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    t = re.sub(r"[-'’]", ' ', t)
    return [w for w in re.sub(r'[^a-z0-9 ]', ' ', t).split() if w]


def interp_times(n, pairs):
    st, en = [None] * n, [None] * n
    for i, (a, b) in pairs.items(): st[i], en[i] = a, b
    known = [i for i in range(n) if st[i] is not None]
    for i in range(n):
        if st[i] is None:
            prv = max([k for k in known if k < i], default=None); nxt = min([k for k in known if k > i], default=None)
            if prv is None: st[i] = en[i] = st[nxt]
            elif nxt is None: st[i] = en[i] = en[prv]
            else:
                f = (i - prv) / (nxt - prv); st[i] = en[prv] + f * (st[nxt] - en[prv]); en[i] = st[i]
    return st, en


def align_map(a_tok, b_tok):
    sm = difflib.SequenceMatcher(None, a_tok, b_tok, autojunk=False)
    return {m.a + k: m.b + k for m in sm.get_matching_blocks() for k in range(m.size)}


def load_wav(p):
    w = wave.open(p); x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return x.reshape(-1, w.getnchannels()).mean(1) if w.getnchannels() > 1 else x


def write_wav(p, x, ch=1):
    w = wave.open(p, 'wb'); w.setnchannels(ch); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()


def rms_db(x): return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9)


def transcribe(wav44, lang='fr'):
    from faster_whisper import WhisperModel
    x = load_wav(wav44); x16 = np.interp(np.arange(0, len(x), SR / 16000), np.arange(len(x)), x).astype(np.float32)
    m = WhisperModel(WHISPER, device='cpu', compute_type='int8')
    segs, _ = m.transcribe(x16, language=lang, word_timestamps=True, beam_size=5, condition_on_previous_text=False)
    return [(w.start, w.end, w.word) for s in segs for w in s.words]


def align_voice(plans, voice_wav, work):
    """Découpe la voix par plan et calcule l'instant de chaque sous-titre. Renvoie [{wav, dur, items}]."""
    x = load_wav(voice_wav)
    words = transcribe(voice_wav)
    json.dump(words, open(os.path.join(work, 'words.json'), 'w'), ensure_ascii=False)
    S_tok, S_par = [], []
    for i, p in enumerate(plans):
        tk = norm_tokens(p['voice']); S_tok += tk; S_par += [i] * len(tk)
    w_tok, w_t = [], []
    for s, e, w in words:
        for t in norm_tokens(w): w_tok.append(t); w_t.append((s, e))
    m = align_map(S_tok, w_tok)
    print(f'mots reconnus : {len(m)} / {len(S_tok)}')
    st, en = interp_times(len(S_tok), {i: w_t[j] for i, j in m.items()})
    fr = int(0.01 * SR); out = []
    def quietest(lo, hi):
        if hi - lo < 0.03: return (lo + hi) / 2
        ks = np.arange(lo, hi - 0.02, 0.005)
        return float(ks[np.argmin([rms_db(x[int(k * SR):int(k * SR) + 2 * fr]) for k in ks])])
    for pi, p in enumerate(plans):
        idx = [i for i in range(len(S_tok)) if S_par[i] == pi]
        t0, t1 = st[idx[0]], en[idx[-1]]
        prev_end = en[idx[0] - 1] if idx[0] > 0 else 0
        next_st = st[idx[-1] + 1] if idx[-1] + 1 < len(S_tok) else len(x) / SR
        thr = rms_db(x[int(t0 * SR):max(int(t1 * SR), int(t0 * SR) + fr)]) - 24
        a = quietest(prev_end, t0) if pi > 0 else 0.0
        b = quietest(t1, next_st) if pi < len(plans) - 1 else len(x) / SR
        while a + 0.01 < t0 and rms_db(x[int(a * SR):int(a * SR) + fr]) < thr: a += 0.01
        a = max(0, a - 0.04)
        while b - 0.01 > t1 and rms_db(x[int(b * SR) - fr:int(b * SR)]) < thr: b -= 0.01
        b = min(len(x) / SR, b + 0.12)
        seg = x[int(a * SR):int(b * SR)].copy()
        n = int(0.008 * SR); seg[:n] *= np.linspace(0, 1, n); n = int(0.06 * SR); seg[-n:] *= np.linspace(1, 0, n)
        wav = os.path.join(work, f'voix_{pi + 1:02d}.wav'); write_wav(wav, seg)
        items = build(p['lines'])
        d_tok, d_item = [], []
        for ii, it in enumerate(items):
            tk = norm_tokens(it[2]); d_tok += tk; d_item += [ii] * len(tk)
        p_tok = [S_tok[i] for i in idx]
        mm = align_map(d_tok, p_tok)
        dst, _ = interp_times(len(d_tok), {i: (st[idx[j]], en[idx[j]]) for i, j in mm.items()}) if mm else ([t0] * len(d_tok), None)
        starts = []
        for ii in range(len(items)):
            toks = [k for k in range(len(d_tok)) if d_item[k] == ii]
            starts.append(max(0.0, dst[toks[0]] - a) if toks else None)
        starts[0] = 0.0
        for ii in range(1, len(starts)):
            if starts[ii] is None or starts[ii] < starts[ii - 1] + 0.3: starts[ii] = starts[ii - 1] + 0.3
        for it, s in zip(items, starts): it[3] = s
        out.append({'wav': wav, 'dur': len(seg) / SR, 'items': items})
        print(f"plan {pi + 1:02d} : {len(seg) / SR:5.2f} s")
    return out


# ------------------------------------------------------------------ bruitages
def add(buf, t, x, gain_db=0.0):
    i = int(t * SR); x = x * 10 ** (gain_db / 20); j = min(len(buf), i + len(x))
    if i < 0: x = x[-i:]; i = 0
    if j > i: buf[i:j] += x[:j - i]

rng = np.random.default_rng(7)

def bandsweep(noise, f_start, f_end, width=0.6):
    hop, win = 512, 2048; out = np.zeros(len(noise) + win); w = np.hanning(win)
    n = max(1, (len(noise) - win) // hop + 1)
    for k in range(n):
        seg = noise[k * hop:k * hop + win]
        if len(seg) < win: seg = np.pad(seg, (0, win - len(seg)))
        f = f_start * (f_end / f_start) ** (k / max(1, n - 1))
        X = np.fft.rfft(seg * w); fr = np.fft.rfftfreq(win, 1 / SR)
        mask = np.exp(-0.5 * (np.log2(np.maximum(fr, 1) / f) / width) ** 2)
        out[k * hop:k * hop + win] += np.fft.irfft(X * mask) * w
    return out[:len(noise)] / 1.5

def lowpass(x, fc):
    X = np.fft.rfft(x); fr = np.fft.rfftfreq(len(x), 1 / SR); return np.fft.irfft(X / (1 + (fr / fc) ** 4), len(x))

def highpass(x, fc):
    X = np.fft.rfft(x); fr = np.fft.rfftfreq(len(x), 1 / SR); return np.fft.irfft(X * (1 / (1 + (fc / np.maximum(fr, 1)) ** 4)), len(x))

def norm(x): return x / (np.abs(x).max() + 1e-9)

def whoosh(L=0.55):
    n = int(L * SR); t = np.linspace(0, 1, n)
    x = bandsweep(rng.standard_normal(n), 500, 3200, 0.7)
    return norm(x * np.where(t < 0.62, (t / 0.62) ** 2.2, np.exp(-(t - 0.62) * 9)))

def impact():
    n = int(1.1 * SR); t = np.arange(n) / SR; f = 38 + 70 * np.exp(-t * 14)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.2)
    click = lowpass(rng.standard_normal(n), 3500) * np.exp(-t * 60) * 0.6
    tail = lowpass(rng.standard_normal(n), 900) * np.exp(-t * 6) * 0.25
    return norm(np.tanh(2.2 * (boom + click + tail)))

def riser(L=1.5):
    n = int(L * SR); t = np.linspace(0, 1, n)
    x = bandsweep(rng.standard_normal(n), 300, 5000, 0.5)
    tone = np.sin(2 * np.pi * np.cumsum(180 + 520 * t ** 2) / SR) * 0.35
    return norm((x + tone) * t ** 2.5)

def rain(L):
    n = int(L * SR); x = highpass(lowpass(rng.standard_normal(n), 7000), 900) * 0.5
    drops = np.zeros(n)
    for i in rng.integers(0, n - 400, int(L * 140)): drops[i:i + 300] += rng.uniform(.2, 1) * np.exp(-np.arange(300) / 40) * rng.standard_normal(300)
    x = x + highpass(drops, 1500) * 0.6
    return norm(x) * np.minimum(1, np.minimum(np.arange(n), n - np.arange(n)) / (0.6 * SR))

def thunder():
    n = int(3.5 * SR); t = np.arange(n) / SR
    b = np.cumsum(rng.standard_normal(n)); b -= np.convolve(b, np.ones(4410) / 4410, 'same')
    rumble = lowpass(b, 160) * (1 - np.exp(-t * 6)) * np.exp(-t * 0.9)
    crack = highpass(rng.standard_normal(n), 800) * np.exp(-t * 18) * 0.5
    mod = 0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 1.7 * t + rng.uniform(0, 3)))
    return norm(np.tanh(1.5 * norm(rumble * mod) + crack))

def heartbeat(L, bpm0=72, bpm1=104):
    n = int(L * SR); x = np.zeros(n); t = 0.0
    while t < L - 0.3:
        bpm = bpm0 + (bpm1 - bpm0) * t / L
        for off, f, g in ((0, 55, 1.0), (0.24, 48, 0.7)):
            k = np.arange(int(0.18 * SR)) / SR; th = np.sin(2 * np.pi * f * k) * np.exp(-k * 22) * g
            i = int((t + off) * SR); j = min(n, i + len(th)); x[i:j] += th[:j - i]
        t += 60 / bpm
    return norm(np.tanh(1.8 * x))


SCORE = re.compile(r'^\d+-\d+$')

def build_sfx(timeline, total):
    """timeline : [{t0, dur, items (début relatif), opts}] -> piste de bruitages."""
    sfx = np.zeros(int(total * SR) + SR, np.float32)
    for i, p in enumerate(timeline):
        t, o = p['t0'], p['opts']
        if i > 0: add(sfx, t - 0.34, whoosh(), -13)
        for it in p['items']:
            if it[0] != 'big': continue
            tb = t + it[3] + 0.04
            add(sfx, tb - 0.02, impact(), -5 if SCORE.match(it[2]) or '!' in it[2] else -9)
            if SCORE.match(it[2]) and it[3] > 1.2: add(sfx, tb - 1.5, riser(1.5), -15)
            if o.get('thunder') and SCORE.match(it[2]): add(sfx, tb - 0.1, thunder(), -6)
        if o.get('rain'): add(sfx, t, rain(p['dur']), -27)
        if o.get('heart'): add(sfx, t, heartbeat(p['dur']), -14)
    return sfx[:int(total * SR)] * 0.5


VCH = ('highpass=f=70,equalizer=f=2800:t=q:w=1.2:g=3.5,equalizer=f=180:t=q:w=1:g=1.5,'
       'acompressor=threshold=-20dB:ratio=4:attack=5:release=120:makeup=3,aecho=0.8:0.5:45:0.12,loudnorm=I=-16:TP=-2:LRA=6,aresample=44100')


def music_track(spec, base, total, work):
    m = spec.get('music', {})
    path = resolve(base, m.get('file', 'assets/music/run_toward_tomorrow.mp3'))
    start = float(m.get('start', 0)); fade = float(m.get('fade_out', 2.5))
    out = os.path.join(work, 'music.wav')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(start), '-i', path, '-t', f'{total:.3f}', '-ac', '2', '-ar', str(SR),
                    '-af', f'afade=t=in:d=0.6,afade=t=out:st={max(0, total - fade):.3f}:d={fade},apad,atrim=0:{total:.3f}', out], check=True)
    return out


def mix_and_mux(video, voice, sfx, music, total, out, music_db=-2):
    mixw = out.replace('.mp4', '_mix.wav')
    if voice:
        fc = (f'[0:a]{VCH},asplit=3[v1][v2][v3];[1:a][v2]sidechaincompress=threshold=0.05:ratio=3:attack=20:release=300,volume=-3dB[sd];'
              f'[2:a]equalizer=f=2600:t=q:w=1.0:g=-4,aresample=44100,volume={music_db}dB[mu];[mu][v3]sidechaincompress=threshold=0.04:ratio=3.5:attack=25:release=400:knee=4[md];'
              f'[v1]aformat=channel_layouts=stereo[vs];[sd]aformat=channel_layouts=stereo[ss];[md]aformat=channel_layouts=stereo[ms];'
              f'[vs][ss][ms]amix=inputs=3:normalize=0,alimiter=limit=0.89,loudnorm=I=-14:TP=-1.5:LRA=9,aresample=48000,apad,atrim=0:{total:.4f}[o]')
        ins = ['-i', voice, '-i', sfx, '-i', music]
    else:
        fc = (f'[0:a]volume=-2dB,aformat=channel_layouts=stereo[ss];[1:a]aresample=44100,volume={music_db}dB,aformat=channel_layouts=stereo[ms];'
              f'[ss][ms]amix=inputs=2:normalize=0,alimiter=limit=0.89,loudnorm=I=-14:TP=-1.5:LRA=9,aresample=48000,apad,atrim=0:{total:.4f}[o]')
        ins = ['-i', sfx, '-i', music]
    subprocess.run(['ffmpeg', '-v', 'error', '-y'] + ins + ['-filter_complex', fc, '-map', '[o]', '-c:a', 'pcm_s16le', mixw], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-i', mixw, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart', out], check=True)
    os.remove(mixw)


def render_all(jobs):
    with Pool(min(6, os.cpu_count() or 2)) as pool: pool.map(render_plan, jobs)


def concat(files, out):
    lst = out + '.txt'
    open(lst, 'w').write(''.join(f"file '{f}'\n" for f in files))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', out], check=True)
    os.remove(lst)


# ------------------------------------------------------------------ commandes
def cmd_episode(spec_path):
    spec = json.load(open(spec_path)); base = os.path.dirname(os.path.abspath(spec_path))
    work = os.path.join(base, 'work'); os.makedirs(work, exist_ok=True)
    voice44 = os.path.join(work, 'voice44.wav')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', resolve(base, spec['voice']), '-ac', '1', '-ar', str(SR), voice44], check=True)
    plans = spec['plans']
    al = align_voice(plans, voice44, work)
    jobs, timeline, t = [], [], 0.0
    vtrack = []
    for i, (p, a) in enumerate(zip(plans, al)):
        lead = 0.55 if i == 0 else 0.12; tail = 2.2 if i == len(plans) - 1 else 0.30
        total = round((lead + a['dur'] + tail) * FPS) / FPS
        items = [[k, sp, tx, (lead + s - 0.04) if j else 0] for j, (k, sp, tx, s) in enumerate(a['items'])]
        jobs.append({'image': resolve(base, p['image']) if p.get('image') else None, 'video': resolve(base, p['video']) if p.get('video') else None, 'items': items, 'total': total, 'opts': p.get('opts', {}),
                     'out': os.path.join(work, f'plan_{i + 1:02d}.mp4'), 'idx': i, 'first': i == 0, 'last': i == len(plans) - 1})
        timeline.append({'t0': t, 'dur': total, 'items': items, 'opts': p.get('opts', {})})
        vtrack.append((t + lead, a['wav'])); t += total
    render_all(jobs)
    voice = np.zeros(int(t * SR) + SR, np.float32)
    for t0, wv in vtrack: add(voice, t0, load_wav(wv))
    vpath = os.path.join(work, 'voice_track.wav'); write_wav(vpath, voice[:int(t * SR)])
    spath = os.path.join(work, 'sfx.wav'); write_wav(spath, build_sfx(timeline, t))
    mpath = music_track(spec, base, t, work)
    vid = os.path.join(work, 'video.mp4'); concat([j['out'] for j in jobs], vid)
    out = os.path.join(base, spec.get('output', 'episode.mp4'))
    mix_and_mux(vid, vpath, spath, mpath, t, out)
    print(f'OK {out} ({t:.1f} s)')


def cmd_short(spec_path):
    spec = json.load(open(spec_path)); base = os.path.dirname(os.path.abspath(spec_path))
    work = os.path.join(base, 'work_' + os.path.splitext(os.path.basename(spec_path))[0]); os.makedirs(work, exist_ok=True)
    plans = spec['plans']; jobs, timeline, t = [], [], 0.0
    for i, p in enumerate(plans):
        items = build(p['lines']); s = 0.0
        for it in items: d = it[3]; it[3] = s; s += d
        total = round((s + (1.2 if i == len(plans) - 1 else 0.1)) * FPS) / FPS
        jobs.append({'image': resolve(base, p['image']) if p.get('image') else None, 'video': resolve(base, p['video']) if p.get('video') else None, 'items': items, 'total': total, 'opts': p.get('opts', {}),
                     'out': os.path.join(work, f'plan_{i + 1:02d}.mp4'), 'idx': i, 'first': i == 0, 'last': i == len(plans) - 1})
        timeline.append({'t0': t, 'dur': total, 'items': items, 'opts': p.get('opts', {})}); t += total
    render_all(jobs)
    spath = os.path.join(work, 'sfx.wav'); write_wav(spath, build_sfx(timeline, t))
    spec.setdefault('music', {}).setdefault('start', 51.9)
    mpath = music_track(spec, base, t, work)
    vid = os.path.join(work, 'video.mp4'); concat([j['out'] for j in jobs], vid)
    out = os.path.join(base, spec.get('output', 'short.mp4'))
    mix_and_mux(vid, None, spath, mpath, t, out, music_db=-1)
    print(f'OK {out} ({t:.1f} s)')


def cmd_cover(spec_path):
    spec = json.load(open(spec_path)); base = os.path.dirname(os.path.abspath(spec_path))
    c = spec['cover']
    img = cover_img(resolve(base, c['image'])).convert('RGBA')
    grad = Image.new('L', (1, H))
    for y in range(H): grad.putpixel((0, y), int(225 * min(1, max(0, (y - H * .60) / (H * .18)))))
    sh = Image.new('RGBA', (W, H), (0, 0, 0, 255)); sh.putalpha(grad.resize((W, H))); img.alpha_composite(sh)
    d = ImageDraw.Draw(img)
    text_center(d, 1300, c.get('kicker', 'ÉPISODE'), font(BARLOW, 70), WHITE)
    t = c['title'].upper(); size = 160
    while d.textlength(t, font=font(ANTON, size)) > W - 100: size -= 8
    text_center(d, 1380, t, font(ANTON, size), YEL, stroke=12)
    if c.get('subtitle'): text_center(d, 1590, c['subtitle'].upper(), font(BARLOW, 62), WHITE)
    out = os.path.join(base, c.get('output', 'couverture.jpg')); img.convert('RGB').save(out, quality=93); print('OK', out)


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] not in ('episode', 'short', 'cover'):
        raise SystemExit(__doc__)
    {'episode': cmd_episode, 'short': cmd_short, 'cover': cmd_cover}[sys.argv[1]](sys.argv[2])
