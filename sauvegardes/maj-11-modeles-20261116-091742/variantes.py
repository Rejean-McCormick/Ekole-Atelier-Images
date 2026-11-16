"""Galerie multi-moteurs, révision par variante et statut d'intégration partagé."""
from generation import output_path
from collections_images import state_for
import revision


def list_variants(state, jobs, root, engines):
    rows = []
    for engine, detail in engines.items():
        collection = state_for(state, engine)
        # Les images déjà créées restent dans la collection associée à leur moteur.
        for row in revision.list_images(collection, jobs, root):
            jobkey = row['key']
            row['key'] = engine + '@' + jobkey
            row['engine'] = engine
            row['provider'] = detail['provider']
            row['engine_name'] = detail['name']
            job = next(j for j in jobs if j.key == jobkey)
            target_exists = bool(root and revision.destination(root, job).is_file())
            row['covered_elsewhere'] = target_exists and row['status'] != 'integree'
            rows.append(row)
    # Regrouper les variantes de la MÊME scène côte à côte dans la grille.
    order = {'cloudflare': 0, 'local': 1, 'replicate': 2, 'bfl': 3}
    rows.sort(key=lambda row: (row['key'].split('@', 1)[1], order.get(row['provider'], 9), row['engine']))
    return rows


def apply(state, jobs, keys, action, root, engines):
    if not isinstance(keys, list) or not keys:
        raise ValueError('Sélection vide.')
    by_engine = {}
    for key in dict.fromkeys(keys):
        if not isinstance(key, str) or '@' not in key:
            raise ValueError('Identifiant de variante invalide.')
        engine, jobkey = key.split('@', 1)
        if engine not in engines or not jobkey:
            raise ValueError('Moteur de variante inconnu.')
        by_engine.setdefault(engine, []).append(jobkey)
    result = {'done': 0, 'errors': []}
    for engine, eng_keys in by_engine.items():
        r = revision.apply(state_for(state, engine), jobs, eng_keys, action, root)
        result['done'] += r['done']
        result['errors'] += [engine + ' / ' + e for e in r['errors']]
    return result
