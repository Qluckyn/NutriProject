"""SQLite 历史快照：保存评估数据、可选建议及独立 DOCX 副本。"""
import json
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from config import DRAFT_VIEWS
from services.draft_service import draft_image_path, read_draft_file

BASE = Path(__file__).resolve().parents[1]
DB = BASE / 'history.db'
REPORTS = BASE / 'history_reports'
KEYS = ('nrs2002_result', 'mnasf_result', 'image_result', 'glim_result')


def init_history_storage():
    REPORTS.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as con:
        con.execute(
            'CREATE TABLE IF NOT EXISTS history '
            '(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, patient_name TEXT NOT NULL, '
            'snapshot TEXT NOT NULL, advice TEXT)'
        )
        columns = {row[1] for row in con.execute('PRAGMA table_info(history)')}
        if 'folder_name' not in columns:
            con.execute('ALTER TABLE history ADD COLUMN folder_name TEXT')
        # 兼容改造前的归档：其目录名就是完整历史记录 ID。
        con.execute(
            "UPDATE history SET folder_name = id "
            "WHERE folder_name IS NULL OR trim(folder_name) = ''"
        )


def _conn():
    init_history_storage()
    return sqlite3.connect(DB)


def _folder_name(rid):
    with _conn() as con:
        row = con.execute(
            'SELECT folder_name FROM history WHERE id = ?', (rid,)
        ).fetchone()
    if not row:
        raise HTTPException(404, '历史记录不存在。')
    return row[0]


def _folder_path(rid):
    folder_name = _folder_name(rid)
    folder = (REPORTS / folder_name).resolve()
    if REPORTS.resolve() not in folder.parents:
        raise HTTPException(404, '历史归档目录不存在。')
    return folder


def create(advice=None):
    draft = read_draft_file()
    if not all(draft.get(key) for key in ('nrs2002_result', 'image_result', 'glim_result')):
        raise HTTPException(422, '请先完成 NRS-2002、面部图像筛查和 GLIM 评估。')

    rid = uuid.uuid4().hex
    created_at = datetime.now()
    now = created_at.strftime('%Y-%m-%d %H:%M:%S')
    folder_name = '{}_{}'.format(created_at.strftime('%Y%m%d_%H%M%S'), rid[:8])
    name = str((draft.get('patient_info') or {}).get('name') or '未命名患者')
    snap = json.loads(json.dumps(draft, ensure_ascii=False))

    folder = REPORTS / folder_name
    report_folder = folder / 'reports'
    image_folder = folder / 'images'
    report_folder.mkdir(parents=True)
    image_folder.mkdir(parents=True)

    for key in KEYS:
        result = snap.get(key) or {}
        source = Path(result.get('document_output', ''))
        if source.is_file():
            destination = report_folder / source.name
            shutil.copy2(source, destination)
            result['history_report'] = destination.name

    for view in DRAFT_VIEWS:
        source = draft_image_path(view)
        if source.is_file():
            destination = image_folder / f'{view}.jpg'
            shutil.copy2(source, destination)
            image_info = snap.setdefault('images', {}).get(view) or {}
            image_info['history_image'] = destination.name
            snap['images'][view] = image_info

    with _conn() as con:
        con.execute(
            'INSERT INTO history (id, created_at, patient_name, snapshot, advice, folder_name) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (
                rid, now, name, json.dumps(snap, ensure_ascii=False),
                json.dumps(advice, ensure_ascii=False) if advice else None, folder_name,
            ),
        )
    return {'id': rid, 'created_at': now, 'patient_name': name}


def list_all():
    with _conn() as con:
        rows = con.execute(
            'SELECT id, created_at, patient_name FROM history ORDER BY created_at DESC'
        ).fetchall()
    return [{'id': row[0], 'created_at': row[1], 'patient_name': row[2]} for row in rows]


def get(rid):
    with _conn() as con:
        row = con.execute(
            'SELECT id, created_at, patient_name, snapshot, advice FROM history WHERE id = ?',
            (rid,),
        ).fetchone()
    if not row:
        raise HTTPException(404, '历史记录不存在。')
    return {
        'id': row[0], 'created_at': row[1], 'patient_name': row[2],
        'snapshot': json.loads(row[3]),
        'personalized_analysis': json.loads(row[4]) if row[4] else None,
    }


def delete(rid):
    folder = _folder_path(rid)
    with _conn() as con:
        if not con.execute('DELETE FROM history WHERE id = ?', (rid,)).rowcount:
            raise HTTPException(404, '历史记录不存在。')
    shutil.rmtree(folder, ignore_errors=True)
    return {'deleted': True}


def report(rid, name):
    folder = _folder_path(rid)
    candidates = (folder / 'reports' / name, folder / name)
    for candidate in candidates:
        path = candidate.resolve()
        if folder in path.parents and path.is_file() and path.suffix == '.docx':
            return path
    raise HTTPException(404, '历史报告不存在。')


def image(rid, view):
    if view not in DRAFT_VIEWS:
        raise HTTPException(404, '历史图片不存在。')
    folder = _folder_path(rid)
    path = (folder / 'images' / f'{view}.jpg').resolve()
    if folder not in path.parents or not path.is_file():
        raise HTTPException(404, '历史图片不存在。')
    return path
