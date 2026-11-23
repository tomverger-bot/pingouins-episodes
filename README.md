# Les Pingouins — kit de montage

Vidéos anime de FC Pierrelaye CDM (« Les Pingouins »), comptes TikTok et Instagram @lespingouinscdm.
Ce dépôt contient tout ce qu'il faut pour monter un épisode dans une session vierge : le script de montage,
les images du pilote, les portraits, la musique du générique et les polices.

La bible de la série (équipage, surnoms validés, lignes rouges, saison, style des prompts) est dans le projet claude.ai
« CDM 26/27 - FC Pierrelaye », document `claude/pingouins_bible_episodes.md`. Elle prime sur ce README pour le contenu.

## Démarrer une session

```bash
./setup.sh          # dépendances + modèle de transcription (≈ 2 min la première fois)
```

## Commandes

```bash
python3 pingouins.py episode episodes/epNN/episode.json        # épisode avec voix off
python3 pingouins.py short   episodes/epNN/short_mercredi.json # format court, musique seule
python3 pingouins.py cover   episodes/epNN/episode.json        # couverture du Reel
python3 page_episode.py      episodes/epNN/episode.json        # page de l'épisode pour Tom (page.html, à publier en artifact)
```

Les vidéos et fichiers de travail ne sont pas versionnés (.gitignore). Les livrer avec SendUserFile.

## Format d'un épisode (`episode.json`)

Voir episodes/ep02/episode.json comme modèle complet (champs de page : kicker, motto, next, caption, acts, prompts, plans[].screen, plans[].kind).

```json
{
 "episode": 2, "title": "Eaubonne", "voice": "voix.mp3", "output": "Les_Pingouins_E02.mp4",
 "music": {"file": "assets/music/run_toward_tomorrow.mp3", "start": 0},
 "cover": {"image": "N4.jpg", "kicker": "ÉPISODE 2", "title": "Eaubonne", "subtitle": "Le lob du Petit"},
 "plans": [
  {"image": "N4.jpg", "lines": ["Trente-cinq mètres…", "!! 2-1"], "voice": "[whispers] Trente-cinq mètres…", "opts": {}}
 ]
}
```

- `voice` d'un plan : le paragraphe exact envoyé à ElevenLabs pour ce plan (balises comprises). L'ordre des plans = l'ordre des paragraphes. Le fichier de voix complet est découpé automatiquement (transcription + alignement).
- `lines` : les sous-titres. « !! texte » = gros texte central avec flash et impact (scores « 2-1 » : montée sonore avant). « Prénom : réplique » = dialogue (nom en blanc, réplique en jaune).
- `opts` : `n` (un seul cadrage, zoom lent), `shake`, `zoom`, `rain`, `thunder` (orage sur le score), `heart` (battements de cœur).
- Images : chemin relatif au dossier de l'épisode, ou `assets/pilot/NN.jpg`, `assets/portraits/prenom.jpg`.

## Formats courts (`short_*.json`)

Même structure sans `voice` : `{"type": "short", "plans": [...], "music": {"start": 51.9}}`. La musique démarre sur le refrain (51,9 s). 15 à 20 secondes, 2 à 4 plans, uniquement des images existantes.

## Voix off

ElevenLabs, voix « Fred - Radio Host », modèle Eleven v4, stabilité 30, similarité 75, langue Français.
Tout le script en une génération, une ligne vide entre les plans. Variante japonaise : « Ryu - Calm Japanese Male Narration ».

## Images

- `assets/pilot/01.jpg` à `18.jpg` : plans de l'épisode 1. 01 terrain à l'aube ; 02 l'équipe de dos ; 03 Tom regard doré ;
  04 parchemin ; 05 et 06 l'équipe ; 07 Kevin (5) et la défense qui monte ; 08 les dix-neuf alignés ; 09 célébration du 7-1 ;
  10 lune rouge, François au sol ; 11 les géants ; 12 entraînement de nuit ; 13 Herblay ; 14 Thomas face au gardien ;
  15 coup franc (horloge 94:00) ; 16 Kilian qui plonge ; 17 l'équipe en cercle ; 18 le stade au soleil (fin).
- `assets/portraits/` : portraits anime par joueur. Les numéros sur les maillots de certains portraits sont anciens (avant la renumérotation de nov. 2026) : se fier à la bible.
- Nouvelles images d'un épisode : `N1.jpg`… dans le dossier de l'épisode, générées par Tom avec Gemini.

## Semaine type

| Jour | Quoi | Qui |
| --- | --- | --- |
| Dimanche | Débrief du match dans le projet claude.ai | Tom |
| Lundi 12h | Script, voix off, prompts, page de l'épisode, fichier `episode.json` | Claude (tâche programmée) |
| Lundi après-midi | 5 images Gemini + voix ElevenLabs, envoyées dans la session | Tom |
| Lundi | Montage, vidéo + couverture + légende | Claude |
| Lundi 18h | Publication programmée TikTok + Instagram | Tom |
| Mercredi 12h | Format court « joueur de la semaine », publié à 18h | Claude, puis Tom programme |
| Vendredi 12h | Format court « avant-match », publié à 18h | Claude, puis Tom programme |
