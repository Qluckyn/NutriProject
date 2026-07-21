"""SQLite 历史快照：保存评估数据、可选建议及独立 DOCX 副本。"""
import json, shutil, sqlite3, uuid
from datetime import datetime
from pathlib import Path
from typing import Dict
from fastapi import HTTPException
from services.draft_service import read_draft_file

BASE = Path(__file__).resolve().parents[1]
DB = BASE / 'history.db'
REPORTS = BASE / 'history_reports'
KEYS = ('nrs2002_result','mnasf_result','image_result','glim_result')

def init_history_storage():
    REPORTS.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as con:
        con.execute('CREATE TABLE IF NOT EXISTS history (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, patient_name TEXT NOT NULL, snapshot TEXT NOT NULL, advice TEXT)')

def _conn():
    init_history_storage(); return sqlite3.connect(DB)

def create(advice=None):
    draft=read_draft_file()
    if not all(draft.get(k) for k in ('nrs2002_result','image_result','glim_result')): raise HTTPException(422,'请先完成 NRS-2002、面部图像筛查和 GLIM 评估。')
    rid=uuid.uuid4().hex; now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'); name=str((draft.get('patient_info') or {}).get('name') or '未命名患者')
    snap=json.loads(json.dumps(draft, ensure_ascii=False)); folder=REPORTS/rid; folder.mkdir(parents=True)
    for key in KEYS:
        r=snap.get(key) or {}; src=Path(r.get('document_output',''))
        if src.is_file():
            dest=folder/src.name; shutil.copy2(src,dest); r['history_report']=dest.name
    with _conn() as con: con.execute('INSERT INTO history VALUES (?,?,?,?,?)',(rid,now,name,json.dumps(snap,ensure_ascii=False),json.dumps(advice,ensure_ascii=False) if advice else None))
    return {'id':rid,'created_at':now,'patient_name':name}

def list_all():
    with _conn() as con: rows=con.execute('SELECT id,created_at,patient_name FROM history ORDER BY created_at DESC').fetchall()
    return [{'id':r[0],'created_at':r[1],'patient_name':r[2]} for r in rows]

def get(rid):
    with _conn() as con: row=con.execute('SELECT id,created_at,patient_name,snapshot,advice FROM history WHERE id=?',(rid,)).fetchone()
    if not row: raise HTTPException(404,'历史记录不存在。')
    return {'id':row[0],'created_at':row[1],'patient_name':row[2],'snapshot':json.loads(row[3]),'personalized_analysis':json.loads(row[4]) if row[4] else None}

def delete(rid):
    with _conn() as con:
        if not con.execute('DELETE FROM history WHERE id=?',(rid,)).rowcount: raise HTTPException(404,'历史记录不存在。')
    shutil.rmtree(REPORTS/rid,ignore_errors=True); return {'deleted':True}

def report(rid,name):
    path=(REPORTS/rid/name).resolve()
    if REPORTS.resolve() not in path.parents or not path.is_file() or path.suffix!='.docx': raise HTTPException(404,'历史报告不存在。')
    return path
