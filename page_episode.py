#!/usr/bin/env python3
"""Génère la page HTML d'un épisode à partir de son episode.json.

    python3 page_episode.py episodes/ep02/episode.json   ->  episodes/ep02/page.html

Champs utilisés en plus de ceux du montage :
  plans[].screen : ce qu'on voit à l'écran (texte pour Tom)
  plans[].kind   : "new" (nouvelle image), "reuse" (image réutilisée) ou "veo"
  acts           : [{"label": "Acte 1", "title": "…", "from": 1, "dark": false}, …]  (numéro du premier plan de l'acte)
  prompts        : [{"title": "N1 · plan 04 · …", "note": "…", "text": "…"}]
  caption        : légende TikTok / Instagram
  kicker, motto, next : textes d'en-tête et de fin
"""
import html, json, os, re, sys

KIT = os.path.dirname(os.path.abspath(__file__))
e = html.escape
TAG = {'new': ('fixe', 'Nouvelle image'), 'reuse': ('reuse', 'Image réutilisée'), 'veo': ('veo', 'Animé · Veo')}
EXTRA = """
.bloc{margin-top:40px}
.bloc h2{font-family:var(--titre);font-weight:400;font-size:clamp(30px,7vw,42px);letter-spacing:.03em;border-bottom:2px solid var(--or);padding-bottom:8px;margin-bottom:16px}
.bloc p.intro{color:var(--doux);font-size:15px;margin-bottom:14px}
.prompt{border:1px solid var(--bord);border-radius:14px;background:var(--encre);margin-bottom:12px;overflow:hidden}
.ptete{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 14px;border-bottom:1px solid var(--bord)}
.ptete b{display:block;font-family:var(--cond);font-weight:700;font-size:17px}
.ptete span{display:block;color:var(--or);font-size:13px;font-family:var(--cond);font-weight:600}
.copy{flex:none;font-family:var(--cond);font-weight:700;font-size:14px;background:var(--or);color:#1b1405;border:0;border-radius:999px;min-height:40px;padding:0 16px;cursor:pointer}
.copy:focus-visible{outline:2px solid var(--sous-titre);outline-offset:2px}
.prompt pre{white-space:pre-wrap;word-break:break-word;font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:#cfd6e4;padding:14px;margin:0;background:#05070d}
.tag.reuse{background:#173527;color:#8fe0ae}
.rappel{margin-top:12px;border:1px dashed var(--or);border-radius:12px;padding:12px 14px;color:var(--craie);font-size:15px}
"""
JS = """(function(){
var btns=document.querySelectorAll('.seg button');
btns.forEach(function(b){b.addEventListener('click',function(){document.body.setAttribute('data-mode',b.dataset.m);
btns.forEach(function(x){x.setAttribute('aria-pressed',String(x===b));});});});
document.querySelectorAll('.copy').forEach(function(b){b.addEventListener('click',function(){
var t=document.getElementById(b.dataset.t).textContent;
function ok(){b.textContent='Copié ✓';setTimeout(function(){b.textContent='Copier';},1500);}
function fb(){var ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');ok();}catch(x){}document.body.removeChild(ta);}
if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(ok,fb);}else fb();});});
})();"""


def strip_tags(t): return re.sub(r'\s*\[[^\]]*\]\s*', ' ', t).strip()


def block(title, note, text, i):
    return (f'<div class="prompt"><div class="ptete"><div><b>{e(title)}</b>' + (f'<span>{e(note)}</span>' if note else '') +
            f'</div><button type="button" class="copy" data-t="p{i}">Copier</button></div><pre id="p{i}">{e(text)}</pre></div>')


def main(path):
    s = json.load(open(path)); out = os.path.join(os.path.dirname(path), 'page.html')
    plans = s['plans']; acts = s.get('acts') or [{'label': 'Épisode', 'title': s['title'], 'from': 1}]
    body = ''
    for ai, a in enumerate(acts):
        end = acts[ai + 1]['from'] - 1 if ai + 1 < len(acts) else len(plans)
        cards = ''
        for n in range(a['from'], end + 1):
            p = plans[n - 1]; cls, lab = TAG[p.get('kind', 'reuse')]
            cards += (f'<article class="scene"><div class="num"><strong>{n:02d}</strong><span class="tag {cls}">{lab}</span></div>'
                      f'<div class="vu"><div class="lab">À l\'écran</div><p>{e(p.get("screen", ""))}</p></div>'
                      f'<div class="vo"><div class="lab">Voix off</div><p>{e(strip_tags(p["voice"]))}</p></div></article>')
        body += (f'<section class="acte{" sombre" if a.get("dark") else ""}"><div class="acte-tete"><span class="acte-num">{e(a["label"])}</span>'
                 f'<h2>{e(a["title"])}</h2></div><div class="scenes">{cards}</div></section>')
    k = 0; prompts = ''
    for pr in s.get('prompts', []): prompts += block(pr['title'], pr.get('note'), pr['text'], k); k += 1
    vo = '\n\n'.join(p['voice'] for p in plans)
    vo_b = block('Voix off complète · ElevenLabs', 'Fred - Radio Host · Eleven v4 · stabilité 30 · similarité 75 · Français · en une seule génération', vo, k); k += 1
    cap_b = block('Légende TikTok et Instagram', None, s.get('caption', ''), k)
    nnew = len(s.get('prompts', []))
    words = len(strip_tags(vo).split()); minutes = (words * 0.37 + len(plans) * 0.45) / 60
    css = open(os.path.join(KIT, 'assets/page.css')).read()
    page = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Les Pingouins — Épisode {s['episode']} : {e(s['title'])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@600;700;800&display=swap" rel="stylesheet">
<style>{css}{EXTRA}</style></head>
<body data-mode="tout"><div class="page">
<header><div class="kicker">{e(s.get('kicker', ''))}</div>
<h1>Épisode {s['episode']}<br><span>{e(s['title'])}</span></h1>
<p class="devise">{e(s.get('motto', ''))}</p>
<div class="stats"><span class="stat"><b>{len(plans)}</b> plans</span><span class="stat"><b>{nnew}</b> nouvelles images</span>
<span class="stat">≈ <b>{int(minutes)} min {round((minutes % 1) * 60 / 5) * 5:02d}</b></span></div></header>
<nav class="mode" aria-label="Mode de lecture"><div class="seg" role="group">
<button type="button" data-m="tout" aria-pressed="true">Tout</button><button type="button" data-m="vo" aria-pressed="false">Voix off</button>
<button type="button" data-m="vu" aria-pressed="false">À l'écran</button></div></nav>
<main>{body}</main>
<section class="bloc"><h2>Les {nnew} nouvelles images · Gemini</h2>
<p class="intro">À coller une par une dans ta conversation Gemini qui a les portraits. Nomme-les N1, N2… et envoie-les-moi. Les autres plans reprennent des images existantes.</p>{prompts}</section>
<section class="bloc"><h2>La voix off</h2><p class="intro">À coller en une seule génération. Garde les lignes vides entre les paragraphes : elles servent au découpage par plan.</p>{vo_b}</section>
<section class="bloc"><h2>Publication</h2>{cap_b}<div class="rappel">Programme à 18h sur TikTok et Instagram, avec l'étiquette « Contenu généré par IA ».</div></section>
<div class="fin"><strong>À suivre…</strong>{e(s.get('next', ''))}<br>@lespingouinscdm</div>
</div><script>{JS}</script></body></html>"""
    open(out, 'w').write(page); print('OK', out)


if __name__ == '__main__':
    main(sys.argv[1])
