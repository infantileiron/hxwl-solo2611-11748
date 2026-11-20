from src.utils.time import iso


def dataset(item):
    return {'id': item.id, 'name': item.name, 'filename': item.filename, 'row_count': item.row_count,
            'checksum': item.checksum, 'author': item.author, 'created_at': iso(item.created_at)}


def run(item, detail=False):
    item_view = {'id': item.id, 'dataset_id': item.dataset_id, 'name': item.name, 'status': item.status,
                 'author': item.author, 'review': item.review, 'decision': item.decision,
                 'calibration_version': item.calibration_version,
                 'created_at': iso(item.created_at), 'finished_at': iso(item.finished_at),
                 'scheduled_at': iso(item.scheduled_at), 'schedule_id': item.schedule_id,
                 'has_export': bool(item.export_file), 'error': item.error}
    if detail:
        item_view.update(params=item.params, result=item.result, review_note=item.review_note)
    return item_view


def schedule(item):
    return {'id': item.id, 'name': item.name, 'dataset_id': item.dataset_id, 'recipient': item.recipient,
            'next_at': iso(item.next_at), 'repeat_daily': item.repeat_daily, 'enabled': item.enabled}


def delivery(item):
    return {'id': item.id, 'run_id': item.run_id, 'recipient': item.recipient,
            'state': item.state, 'detail': item.detail, 'created_at': iso(item.created_at)}


def calibration_batch(item):
    return {'id': item.id, 'name': item.name, 'filename': item.filename, 'checksum': item.checksum,
            'row_count': item.row_count, 'applied_count': item.applied_count,
            'ignored_count': item.ignored_count, 'version': item.version, 'status': item.status,
            'author': item.author, 'created_at': iso(item.created_at)}


def calibration_entry(item):
    get = item.get if isinstance(item, dict) else lambda name: getattr(item, name)
    return {'probe': get('probe'), 'handoff_date': get('handoff_date'), 'revision': get('revision'),
            'offset': get('offset'), 'calibration_id': get('calibration_id'), 'version': get('version')}


def calibration_state(version, entries):
    return {'version': version, 'entries': [calibration_entry(item) for item in entries],
            'entry_count': len(entries)}
