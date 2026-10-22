"""GUI-independent workspace/storage helpers shared by the Qt application.
The workspace naming and selection file remain compatible with v1.4.
"""
from __future__ import annotations
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

SELECTION_FILE = 'ui_selected_v441.json'
PAGE_SIZE = 120
DEFAULT_OUT = str(Path.home() / 'Videos' / 'AI Vlog Maker')
CONFIG = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'AI_Vlog_Maker_V3' / 'gui_settings.json'
FILTERS = ['全部', '已完成 AI', '高分（70 以上）', '尚未分析', '預篩跳過', '分析失敗']


def workspace(inputs, output):
    digest = hashlib.sha256('\n'.join(sorted(os.path.normcase(p) for p in inputs)).encode('utf-8')).hexdigest()[:12]
    return Path(output) / ('AI_Vlog_' + digest)


def readonly_db(file):
    """Read-only by policy. Existing database should have been initialized by CLI."""
    return sqlite3.connect('file:' + quote(Path(file).resolve().as_posix(), safe='/:') + '?mode=ro', uri=True, timeout=4)


def candidates_page(file, page=0, text='', mode='全部'):
    empty = (0, 0, 0, [], {'media': 0, 'failed': 0, 'skipped': 0, 'pending': 0})
    if not Path(file).is_file():
        return empty
    with closing(readonly_db(file)) as db:
        db.row_factory = sqlite3.Row
        media_count = db.execute('SELECT COUNT(*) FROM media WHERE error IS NULL').fetchone()[0]
        stat = db.execute('''SELECT COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN v2=1 THEN 1 ELSE 0 END),0) AS ready,
            COALESCE(SUM(CASE WHEN v2!=1 AND error IS NOT NULL AND error!='' THEN 1 ELSE 0 END),0) AS failed,
            COALESCE(SUM(CASE WHEN v2!=1 AND (error IS NULL OR error='') AND prefilter_skip IS NOT NULL THEN 1 ELSE 0 END),0) AS skipped
            FROM candidates''').fetchone()
        total, ready, failed, skipped = (int(stat[k]) for k in ('total', 'ready', 'failed', 'skipped'))
        statistics = {'media': media_count, 'failed': failed, 'skipped': skipped,
                      'pending': max(0, total-ready-failed-skipped)}
        where = ['m.error IS NULL']
        params = []
        if text:
            where.append("(c.path LIKE ? OR COALESCE(c.description,'') LIKE ? OR COALESCE(c.error,'') LIKE ?)")
            params += ['%' + text + '%'] * 3
        if mode == '已完成 AI':where.append('c.v2=1')
        elif mode == '高分（70 以上）':where.append('c.v2=1 AND c.score>=70')
        elif mode == '分析失敗':where.append("c.v2!=1 AND c.error IS NOT NULL AND c.error!=''")
        elif mode == '預篩跳過':where.append("c.v2!=1 AND (c.error IS NULL OR c.error='') AND c.prefilter_skip IS NOT NULL")
        elif mode == '尚未分析':where.append("c.v2!=1 AND (c.error IS NULL OR c.error='') AND c.prefilter_skip IS NULL")
        base = ' FROM candidates c JOIN media m ON m.path=c.path WHERE ' + ' AND '.join(where)
        count = db.execute('SELECT COUNT(*)' + base, params).fetchone()[0]
        query = ('''SELECT c.id,c.path,c.position,c.score,c.event,c.category,c.description,
            c.v2,c.error,c.prefilter_skip,c.quick_done,m.kind,m.duration'''+base+
            ' ORDER BY CASE WHEN c.v2=1 THEN 0 WHEN c.error IS NOT NULL THEN 2 ELSE 1 END, '
            'c.score DESC,c.path,c.position LIMIT ? OFFSET ?')
        result = [dict(x) for x in db.execute(query, params+[PAGE_SIZE, page*PAGE_SIZE])]
        for r in result:
            if r['v2'] == 1:r['display_status'] = '已分析'
            elif r['error']:r['display_status'] = '分析失敗'
            elif r['prefilter_skip']:r['display_status'] = '預篩跳過'
            else:r['display_status'] = '未分析'
        return total, ready, count, result, statistics


def save_json_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def load_selection(path):
    """Validate external JSON before it enters the edit engine."""
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(payload, dict):raise ValueError('片單 JSON 必須是物件')
    ids = payload.get('candidate_ids', [])
    if not isinstance(ids, list) or any(not isinstance(x, str) or not x for x in ids):
        raise ValueError('candidate_ids 格式錯誤')
    trims = payload.get('trims', {})
    if not isinstance(trims, dict):raise ValueError('trims 格式錯誤')
    return list(dict.fromkeys(ids)), {k:v for k,v in trims.items() if k in ids and isinstance(v, dict)}


def prune_selection(index, ids, trims):
    """Return clean selection + diagnostics. Caller backs up and persists any change."""
    if not Path(index).is_file():return list(ids), dict(trims), []
    import math
    valid, kept_trims, warnings = [], dict(trims), []
    with closing(readonly_db(index)) as db:
        for key in ids:
            row = db.execute('''SELECT m.path,m.kind,m.duration FROM candidates c
                JOIN media m ON m.path=c.path WHERE c.id=? AND m.error IS NULL''',(key,)).fetchone()
            if row is None or not Path(row[0]).is_file():
                kept_trims.pop(key,None)
                warnings.append(f'[PRUNE] 來源失效，從片單移除 {key}')
                continue
            valid.append(key)
            trim=kept_trims.get(key)
            if trim is not None:
                try:
                    begin,end=float(trim['start']),float(trim['end'])
                    duration=float(row[2] or 0)
                    ok = row[1]=='video' and math.isfinite(begin) and math.isfinite(end) and 0<=begin<end<=duration+0.005 and end-begin>=0.5
                except (KeyError,ValueError,TypeError,OverflowError):ok=False
                if not ok:
                    kept_trims.pop(key,None)
                    warnings.append('[PRUNE] 裁切區間失效，還原自動選片：'+Path(row[0]).name)
    return valid, kept_trims, warnings
