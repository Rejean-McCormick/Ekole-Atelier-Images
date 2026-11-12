"""Catalogue des moteurs de génération et des workflows locaux préconfigurés."""
from pathlib import Path

from generation import KEY, read_json

DIRECTORY = Path(__file__).resolve().with_name('moteurs')
BUILTINS = {
    'cloudflare': {'name': 'Cloudflare', 'mode': 'cloud'},
    'comfy': {'name': 'ComfyUI local avec LoRA', 'mode': 'upload'},
}


def catalogue():
    engines = BUILTINS.copy()
    for profile in sorted(DIRECTORY.glob('*.profil.json')):
        key = profile.name.removesuffix('.profil.json')
        if not KEY.fullmatch(key) or key in engines:
            raise ValueError(f'Identifiant de moteur invalide : {key}')
        data = read_json(profile)
        filename = data['workflow']
        if Path(filename).name != filename or not filename.endswith('.workflow.json'):
            raise ValueError(f'Fichier de workflow invalide pour {key}.')
        engines[key] = {
            'name': data['nom'], 'mode': 'preset', 'description': data.get('description', ''),
            'workflow': filename,
        }
    return engines


def public_catalogue(engines):
    return {key: {k: value for k, value in engine.items() if k != 'workflow'}
            for key, engine in engines.items()}


def load_workflow(engine):
    return read_json(DIRECTORY / engine['workflow'])
