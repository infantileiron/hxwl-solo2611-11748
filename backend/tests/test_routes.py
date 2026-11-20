import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config.database import Base, connection
from src.domain.demo import demo_calibration_rows, demo_rows
from src.main import app
from src.services import calibrations, execution as execution_module
from src.utils.security import hash_password


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    from src.models.identity import User
    with Session.begin() as db:
        db.add(User(username='admin', role='admin', password_hash=hash_password('pw')))
        db.add(User(username='viewer', role='viewer', password_hash=hash_password('pw')))

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[connection] = override
    monkeypatch.setattr('src.services.execution.Session', Session)
    from src.utils import exports
    monkeypatch.setattr(exports, 'write_report', lambda job_id, attempt, result: f'report-{job_id}-{attempt}.csv')
    monkeypatch.setattr(execution_module, 'write_report', exports.write_report)
    with TestClient(app) as test_client:
        yield test_client, Session
    app.dependency_overrides.clear()


def _token(client, name='admin'):
    response = client.post('/auth/login', json={'username': name, 'password': 'pw'})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['token']}"}


def _csv(rows, fields):
    import csv
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def test_calibration_requires_write_role(client):
    http, _ = client
    headers = _token(http, 'viewer')
    response = http.get('/calibration', headers=headers)
    assert response.status_code == 200
    assert response.json()['version'] == 0
    response = http.post('/calibrations', headers=headers,
                         json={'name': 'x', 'filename': 'x.csv', 'csv_text': 'a,b\n1,2\n'})
    assert response.status_code == 403


def test_calibration_upload_conflict_and_old_revision(client):
    http, _ = client
    headers = _token(http)

    good = [{'probe': 'TP-23', 'handoff_date': '2026-11-16', 'revision': 2,
             'offset': -0.6, 'calibration_id': 'CAL-B'}]
    response = http.post('/calibrations', headers=headers,
                         json={'name': '校准A', 'filename': 'a.csv', 'csv_text': _csv(good, ['probe', 'handoff_date', 'revision', 'offset', 'calibration_id'])})
    assert response.status_code == 201, response.text
    assert response.json()['current_version'] == 1

    # 晚到的旧修订被忽略，不覆盖新修订，也不报错。
    old = [{'probe': 'TP-23', 'handoff_date': '2026-11-16', 'revision': 1,
            'offset': -0.3, 'calibration_id': 'CAL-A'}]
    response = http.post('/calibrations', headers=headers,
                         json={'name': '旧修订', 'filename': 'b.csv', 'csv_text': _csv(old, ['probe', 'handoff_date', 'revision', 'offset', 'calibration_id'])})
    assert response.status_code == 201, response.text
    assert response.json()['applied_count'] == 0
    assert response.json()['ignored_count'] == 1

    # 同修订冲突整批退回，版本不前进。
    conflict = [{'probe': 'TP-23', 'handoff_date': '2026-11-16', 'revision': 2,
                 'offset': -0.4, 'calibration_id': 'CAL-C'}]
    response = http.post('/calibrations', headers=headers,
                         json={'name': '冲突', 'filename': 'c.csv', 'csv_text': _csv(conflict, ['probe', 'handoff_date', 'revision', 'offset', 'calibration_id'])})
    assert response.status_code == 422
    assert '同修订冲突' in response.json()['detail']

    state = http.get('/calibration', headers=headers).json()
    assert state['version'] == 2
    entry = next(item for item in state['entries'] if item['probe'] == 'TP-23')
    assert entry['offset'] == -0.6


def test_analysis_through_api_records_and_uses_calibration(client):
    http, Session = client
    headers = _token(http)
    fields = ['handoff_id', 'handoff_date', 'route', 'shift', 'store', 'batch', 'probe', 'temperature']
    response = http.post('/datasets', headers=headers,
                         json={'name': '交接批', 'filename': 'h.csv', 'csv_text': _csv(demo_rows(), fields)})
    assert response.status_code == 201, response.text
    dataset_id = response.json()['id']

    cal_fields = ['probe', 'handoff_date', 'revision', 'offset', 'calibration_id']
    http.post('/calibrations', headers=headers,
              json={'name': '校准', 'filename': 'c.csv', 'csv_text': _csv(demo_calibration_rows(), cal_fields)})

    created = http.post('/runs', headers=headers, json={'dataset_id': dataset_id, 'name': '复核', 'params': {}})
    assert created.status_code == 202, created.text
    run_id = created.json()['id']
    assert created.json()['calibration_version'] >= 1

    from src.services import execution
    lease = execution.claim()
    assert lease and lease[0] == run_id
    execution.execute(lease)

    detail = http.get(f'/runs/{run_id}', headers=headers).json()
    assert detail['status'] == 'complete', detail.get('error')
    inspection = next(t for t in detail['result']['tables'] if t['title'].startswith('越界交接'))
    row = next(r for r in inspection['rows'] if r['handoff_id'] == 'MY-20261116-S-P-03')
    assert row['raw_temperature'] == 8.1
    assert round(row['temperature'], 2) == 7.5
    assert row['calibration_id'] == 'CAL-2611-23-R2'
    missing = next(t for t in detail['result']['tables'] if t['title'].startswith('缺校准'))
    assert len(missing['rows']) == 6
