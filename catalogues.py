"""Profils CSV génériques et adaptateur en lecture seule pour Ekole Québec."""
import csv
from pathlib import Path
import re

from generation import KEY, STYLE, Job, make_prompt, read_json, read_overrides

BASE = Path(__file__).resolve().parent
PROFILES = BASE / 'profils'
LESSON = re.compile(r'qc-pri-([a-z]+)-[0-9]+')
QUEBEC_STYLE = (
    'Illustration jeunesse en papier découpé, avec des aplats mats et des formes souples. '
    'Ambiance chaleureuse et lumière douce.'
)

# Formules récurrentes des manifestes. Le sujet, les objectifs et les garde-fous
# pédagogiques propres à chaque visuel restent dans le texte de la scène.
SOURCE_BOILERPLATE = (
    'Montrer les relations pertinentes entre les objets ou les personnages, sans imposer de style, palette, technique ou composition fixe.',
    "Laisser la manipulation et les états vérifiables aux composants d'activité.",
)


HEX_COLOR = re.compile(r'#[0-9A-Fa-f]{6}')

# Les adjectifs de teinte peuvent être retirés seuls. Pour les mots qui
# désignent aussi un objet ou un matériau, il faut une indication de couleur.
COLOR_ADJECTIVES = (
    r'bleu(?:e)?s?|vert(?:e)?s?|rouges?|jaunes?|violet(?:te)?s?|mauves?|'
    r'noir(?:e)?s?|blanc(?:he)?s?|gris(?:e)?s?|brun(?:e)?s?|beiges?|'
    r'turquoises?|écarlates?|pourpres?|bordeaux|orangé(?:e)?s?|rosé(?:e)?s?'
)
COLOR_NOUNS = r'orange|rose|crème|prune|cuivre|sable|ivoire|marron|corail|lavande|pêche|menthe|ocre|terracotta|pétrole'
COLOR_SUFFIX = r'(?:\s+(?:pétrole|marine|nuit|ciel|ardoise|glacier|sapin|pin|mousse|sauge|forêt|canneberge|doux|foncé[e]?|clair[e]?|pâle|vif|vive|pastel))?'
COLOR = rf'(?:{COLOR_ADJECTIVES}|{COLOR_NOUNS})(?:{COLOR_SUFFIX})?'
PALETTE_IN_SCENE = re.compile(r'(^|[\n.!?]\s*)[ \t]*(?:palette(?:\s+(?:dominante|de couleurs))?|couleurs(?:\s+dominantes)?)\s*:[^\n.!?]*[.!?]?', re.I)
COLOR_WITH_LABEL = re.compile(rf"\b(?:(?:de\s+)?couleur\s+|de\s+teinte\s+)({COLOR})\b", re.I)
PAINT_COLOR = re.compile(rf"\b(peint(?:e|es|s)?)\s+en\s+{COLOR}\b", re.I)
COLOR_WITH_OBJECT = re.compile(
    rf"\b(fonds?|rideaux?|chandails?|t-?shirts?|pantalons?|vestes?|manteaux?|robes?|jupes?|"
    rf"chaussures?|murs?|portes?|chaises?|tables?|pancartes?|étiquettes?|cahiers?|décors?)\s+"
    rf"(?:{COLOR_NOUNS}){COLOR_SUFFIX}\b", re.I)
COLOR_ADJECTIVE_LIST = re.compile(
    rf"\b(?:en\s+)?(?:{COLOR_ADJECTIVES}){COLOR_SUFFIX}\b"
    rf"(?:(?:\s*,\s*|\s+(?:et|ou)\s+)(?:{COLOR_ADJECTIVES}){COLOR_SUFFIX}\b)*",
    re.I,
)


def without_color_instructions(text):
    text = PALETTE_IN_SCENE.sub(r'\1', text)
    text = re.sub(r'\(\s*#[0-9a-fA-F]{6}\s*\)', '', text)
    text = HEX_COLOR.sub('', text)
    text = COLOR_WITH_LABEL.sub('', text)
    text = PAINT_COLOR.sub(r'\1', text)
    text = COLOR_WITH_OBJECT.sub(r'\1', text)
    text = COLOR_ADJECTIVE_LIST.sub('', text)
    text = re.sub(r'\s+([,.])', r'\1', text)
    return ' '.join(text.split())


def validate_palette(colors):
    if colors is None:
        return None
    if not isinstance(colors, list) or not 1 <= len(colors) <= 3 or not all(
        isinstance(color, str) and HEX_COLOR.fullmatch(color) for color in colors
    ):
        raise ValueError('Choisis de 1 à 3 couleurs au format #RRGGBB.')
    colors = [color.upper() for color in colors]
    if len(set(colors)) != len(colors):
        raise ValueError('Choisis des couleurs différentes.')
    return colors


def theme_palette(style):
    colors = list(dict.fromkeys(color.upper() for color in HEX_COLOR.findall(style.get('palette', ''))))
    return colors[:3] or ['#F4E9D6']


def compact_kristal_scene(text):
    text = re.sub(r'^(?:Illustrer le concept du cours|Concept d.image pour le cours|Concept d.image d.exploration pour) «[^»]+»\s*[.:]\s*', '', text)
    for sentence in SOURCE_BOILERPLATE:
        text = text.replace(sentence, '')
    return ' '.join(text.split())


def compose_quebec_prompt(colors, scene, priority=''):
    if priority:
        scene += ' ' + priority
    scene = without_color_instructions(scene)
    age = (
        'Les élèves représentés sont des enfants de 6 à 12 ans, avec des visages enfantins, '
        'une petite taille et des proportions de corps d’enfants du primaire. '
        'Les rôles adultes explicitement décrits gardent leur âge.'
    )
    return (
        f'Scène : {scene}\n\nPersonnages : {age}\n\n'
        f'{QUEBEC_STYLE} Palette : {", ".join(colors)}.\n\n'
        'Illustration sans texte visible. Aucune lettre, aucun chiffre, titre, sous-titre, logo '
        'ni filigrane. Les pancartes, étiquettes et pages restent vierges. '
        'Les dialogues sont suggérés par les gestes et les regards, sans bulles.'
    )


def build_jobs(root, themes, styles, overrides, palette=None):
    authored = read_json(Path(__file__).with_name('mise-en-scene-quebec.json'))
    pack = {c['id']: c for c in read_json(root / 'pack.json')['cours']}
    lessons = []
    for path in sorted(root.glob('kristals/*/experience/RESSOURCES_VISUELLES.json')):
        course = path.parents[1].name
        match = LESSON.fullmatch(course)
        if not match or course not in pack:
            continue
        doc = read_json(path)
        for entry in doc['visuels']:
            slot = entry['slot']
            if slot in ('concept', 'situation') and entry.get('prompt_conceptuel', '').strip():
                existing = any((path.parent / 'images' / f'{slot}.{ext}').is_file()
                               for ext in ('webp', 'jpg', 'jpeg', 'png'))
                lessons.append((course, match[1], entry, existing))
    jobs = []
    used_overrides = set()
    for theme in themes:
        tid = theme['id']
        if not KEY.fullmatch(tid) or tid not in styles:
            raise ValueError(f'Thème sans style de génération : {tid}')
        colors = palette or theme_palette(styles[tid])
        for course, discipline, entry, existing in lessons:
            slot = entry['slot']
            key = tid, course, slot
            if key in overrides:
                used_overrides.add(key)
            treatment = authored.get(f'{course}/{slot}', {})
            if key in overrides:
                prompt = compose_quebec_prompt(colors, overrides[key])
            elif treatment:
                prompt = compose_quebec_prompt(colors, treatment['scene'], treatment.get('priorite', ''))
            else:
                prompt = compose_quebec_prompt(colors, compact_kristal_scene(entry['prompt_conceptuel']))
            jobs.append(Job(tid, discipline, course, pack[course]['titre'], slot,
                            entry.get('texte_alternatif', ''), prompt, existing))
    unknown = overrides.keys() - used_overrides
    if unknown:
        raise ValueError('Lignes CSV sans emplacement correspondant : ' +
                         ', '.join('/'.join(key) for key in sorted(unknown)[:8]))
    return jobs


def profiles():
    return {path.name.removesuffix('.profil.json'): read_json(path) for path in sorted(PROFILES.glob('*.profil.json'))
            if KEY.fullmatch(path.name.removesuffix('.profil.json'))}



def neutral_theme(theme):
    return {**theme, 'name': without_color_instructions(theme['name']),
            'intro': without_color_instructions(theme.get('intro', ''))}

def csv_jobs(path, themes, styles, art_direction, palette=None):
    jobs, keys = [], set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        header = stream.readline()
        stream.seek(0)
        rows = csv.DictReader(stream, delimiter=';' if header.count(';') > header.count(',') else ',')
        fields = ('theme', 'branche', 'id', 'slot', 'titre', 'prompt')
        if not set(fields).issubset(rows.fieldnames or []):
            raise ValueError('Colonnes CSV requises : ' + ', '.join(fields))
        for i, row in enumerate(rows, 2):
            theme, branch, asset, slot, title, scene = ((row.get(f) or '').strip() for f in fields)
            key = theme, branch, asset, slot
            if (theme not in themes or not all(KEY.fullmatch(v) for v in key)
                    or key in keys or not title or not scene):
                raise ValueError(f'Ligne CSV {i} : identifiant inconnu, doublon ou champ manquant.')
            keys.add(key)
            jobs.append(Job(theme, branch, asset, title, slot, row.get('alt') or '',
                            make_prompt(neutral_theme(themes[theme]), ', '.join(palette or theme_palette(styles[theme])),
                                        without_color_instructions(scene), without_color_instructions(art_direction)), False))
    return jobs


def load(profile, root_override='', palette=None):
    palette = validate_palette(palette)
    if not KEY.fullmatch(profile):
        raise ValueError('Profil invalide.')
    config = read_json(PROFILES / f'{profile}.profil.json')
    state = BASE / 'donnees' / profile
    adapter = config['adapter']
    if adapter == 'kristals-quebec':
        root = Path(root_override.strip()) if root_override.strip() else BASE.parent / config['source']
        if not (root / 'data' / 'univers.json').is_file() or not (root / 'pack.json').is_file():
            raise ValueError('Indique le chemin de la copie locale Québec qui contient pack.json et data/univers.json.')
        styles = read_json(PROFILES / config['styles'])
        raw_themes = read_json(root / 'data' / 'univers.json')['themes']
        jobs = build_jobs(root, raw_themes, styles, read_overrides(state / 'prompts-excel.csv'), palette)
        art_direction = QUEBEC_STYLE
    elif adapter == 'csv':
        raw_themes = config['themes']
        styles = {t['id']: t for t in raw_themes}
        art_direction = config.get('style', STYLE)
        jobs = csv_jobs(PROFILES / config['source'], {t['id']: t for t in raw_themes}, styles, art_direction, palette)
    else:
        raise ValueError(f'Adaptateur inconnu : {adapter}')
    themes = {t['id']: t for t in raw_themes}
    if not themes or len(themes) != len(raw_themes) or any(not KEY.fullmatch(k) for k in themes):
        raise ValueError('Identifiants de thèmes invalides ou en double.')
    if not jobs:
        raise ValueError('Aucune image à préparer dans ce catalogue.')
    return state, themes, styles, art_direction, jobs
