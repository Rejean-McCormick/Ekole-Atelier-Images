"""Variantes par moteur, galerie comparative et provenance de publication Ékole.

Respecte le stockage historique de Cloudflare et les collections de chaque modèle.
La publication ne modifie que la cible Ékole explicitement demandée.
"""
from collections import defaultdict
from datetime import datetime, timezone
import json

from collections_images import state_for
from generation import atomic_write, output_path
import revision


def publication_record(state, job):
    """Identité du modèle choisi lors d'une publication via Atelier Images."""
    return state / 'publications' / job.theme / job.discipline / job.course / (job.slot + '.json')


def get_published(state, jobs, root):
    """Inspecte l'état réel de Ékole; métadonnées du modèle uniquement si le hash concorde."""
    data = {}
    if root is None:
        return data
    for job in jobs:
        target = revision.destination(root, job)
        if not target.is_file():
            continue
        fingerprint = revision.digest(target.read_bytes())
        origin = None
        record = publication_record(state, job)
        if record.is_file():
            try:
                meta = json.loads(record.read_text(encoding='utf-8'))
                if isinstance(meta, dict) and meta.get('sha256') == fingerprint:
                    origin = meta.get('engine')
            except (OSError, UnicodeError, ValueError):
                pass
        data[job.key] = {'sha256': fingerprint, 'engine': origin}
    return data


def list_variants(state, jobs, root, engines):
    by_job = {job.key: job for job in jobs}
    published = get_published(state, jobs, root)
    rows = []
    signatures = defaultdict(dict)

    for engine, detail in engines.items():
        collection = state_for(state, engine)
        for row in revision.list_images(collection, jobs, root):
            job_key = row['key']
            job = by_job[job_key]
            row['key'] = engine + '@' + job_key
            row['scene_key'] = job_key
            row['theme'] = job.theme
            row['engine'] = engine
            row['provider'] = detail['provider']
            row['engine_name'] = detail['name']
            row['published'] = False
            row['covered_elsewhere'] = False
            row['same_as_published'] = False
            row['published_engine'] = None
            row['published_engine_name'] = None
            # La provenance n'est pas inférée d'un simple fichier publié : elle est
            # lue dans le manifeste, ou reconnue sans ambiguïté par hash.
            if job_key in published:
                signatures[job_key][engine] = revision.digest(row['path'].read_bytes())
            rows.append(row)

    for row in rows:
        entry = published.get(row['scene_key'])
        if entry is None:
            continue
        source = entry['engine'] if entry['engine'] in engines else None
        if not source:
            matching = [engine for engine, sha in signatures[row['scene_key']].items()
                        if sha == entry['sha256']]
            if len(matching) == 1:
                source = matching[0]
        same = signatures[row['scene_key']].get(row['engine']) == entry['sha256']
        row['published'] = True
        row['same_as_published'] = same
        row['published_engine'] = source
        row['published_engine_name'] = engines[source]['name'] if source else None
        if same and source == row['engine']:
            row['status'] = 'integree'
        elif same:
            # Deux moteurs peuvent produire le même fichier à l'octet près.
            # Sans provenance sûre, on n'attribue pas l'intégration à tort.
            row['status'] = 'identique-publiee'
        else:
            row['covered_elsewhere'] = True
            if row['status'] == 'integree':
                row['status'] = 'validee'

    provider_order = {'cloudflare': 0, 'local': 1, 'replicate': 2, 'bfl': 3}
    rows.sort(key=lambda row: (row['scene_key'], provider_order.get(row['provider'], 9), row['engine']))
    return rows


def apply(state, jobs, keys, action, root, engines):
    if not isinstance(keys, list) or not keys:
        raise ValueError('Sélection vide.')
    by_job = {job.key: job for job in jobs}
    parsed = []
    for key in dict.fromkeys(keys):
        if not isinstance(key, str) or '@' not in key:
            raise ValueError('Identifiant de variante invalide.')
        engine, job_key = key.split('@', 1)
        if engine not in engines or job_key not in by_job:
            raise ValueError('Moteur ou scène de variante inconnu.')
        parsed.append((engine, job_key))

    # Une scène n'a qu'une cible d'intégration dans Ékole : empêcher une
    # sélection simultanée ambiguë de plusieurs moteurs pour la même scène.
    if action == 'integrer':
        if root is None:
            raise ValueError('Intégration indisponible pour ce profil.')
        job_keys = [key for _, key in parsed]
        if len(set(job_keys)) != len(job_keys):
            raise ValueError('Choisis une seule variante par scène à intégrer dans Ékole.')

    result = {'done': 0, 'errors': []}
    for engine, job_key in parsed:
        collection = state_for(state, engine)
        operation = revision.apply(collection, jobs, [job_key], action, root)
        result['done'] += operation['done']
        result['errors'] += [engine + ' / ' + error for error in operation['errors']]
        if action == 'integrer' and operation['done'] == 1:
            job = by_job[job_key]
            image_file = output_path(collection, job)
            signature = revision.digest(image_file.read_bytes())
            data = {
                'engine': engine,
                'sha256': signature,
                'published_at_utc': datetime.now(timezone.utc).isoformat(),
            }
            try:
                atomic_write(publication_record(state, job),
                             json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))
            except OSError as error:
                result['errors'].append(f'{engine} / {job_key} : image publiée, mais provenance non enregistrée ({error}).')
    return result
