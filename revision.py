"""Révision locale et publication des variantes du catalogue Québec."""
import hashlib
from io import BytesIO
import secrets

from generation import atomic_write, output_path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def approval_path(state, job):
    return state / 'validations' / job.theme / job.discipline / job.course / (job.slot + '.sha256')


def destination(root, job):
    return root / 'publications' / 'visuels-themes' / job.theme / job.course / (job.slot + '.webp')


def matches(path, signature):
    return path.is_file() and digest(path.read_bytes()) == signature


def list_images(state, jobs, root):
    rows = []
    for job in jobs:
        path = output_path(state, job)
        if not path.is_file():
            continue
        record = approval_path(state, job)
        status = 'nouvelle'
        if record.is_file():
            signature = record.read_text(encoding='ascii')
            if matches(path, signature):
                status = 'integree' if root and matches(destination(root, job), signature) else 'validee'
        rows.append({'key': job.key, 'titre': job.title, 'slot': job.slot, 'cours': job.course,
                     'status': status, 'path': path, 'prompt': job.prompt})
    return rows


def apply(state, jobs, keys, action, root):
    from PIL import Image

    index = {job.key: job for job in jobs}
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k in index for k in keys):
        raise ValueError('Sélection vide ou invalide.')
    done, errors = 0, []
    for key in dict.fromkeys(keys):
        job = index[key]
        try:
            path = output_path(state, job)
            record = approval_path(state, job)
            if action == 'supprimer':
                if not path.resolve().is_relative_to(state.resolve()):
                    raise ValueError('Image hors de la galerie.')
                path.unlink()
                record.unlink(missing_ok=True)
                done += 1
                continue
            data = path.read_bytes()
            if action == 'ecarter':
                if record.is_file() and record.read_text(encoding='ascii') == digest(data):
                    raise ValueError('Seules les nouvelles images peuvent être écartées.')
                archive = state / 'ecartees' / path.relative_to(state / 'lots')
                archive = archive.with_name(archive.stem + '-' + secrets.token_hex(8) + archive.suffix)
                archive.parent.mkdir(parents=True, exist_ok=True)
                path.rename(archive)
                done += 1
                continue
            if len(data) > 12 * 1024 * 1024:
                raise ValueError('Image trop volumineuse.')
            with Image.open(BytesIO(data)) as image:
                if image.format != 'WEBP' or not all(120 <= dim <= 8192 for dim in image.size):
                    raise ValueError('Format ou dimensions invalides.')
                image.verify()
            signature = digest(data)
            if action == 'valider':
                atomic_write(record, signature.encode('ascii'))
            else:
                if not record.is_file() or record.read_text(encoding='ascii') != signature:
                    raise ValueError('Valide cette version avant de l’intégrer.')
                target = destination(root, job)
                if not target.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Dossier de publication hors du catalogue.')
                atomic_write(target, data)
            done += 1
        except (OSError, ValueError) as error:
            errors.append(f'{key} : {error}')
    return {'done': done, 'errors': errors}
