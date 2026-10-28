"""Read-only media manifests and isolated legacy benchmark replay (stdlib only)."""
from __future__ import annotations
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import vlog_maker as core
from qt_store import readonly_db, save_json_atomic


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(roots):
    paths = set()
    for root in roots:
        root = Path(root).expanduser().resolve(strict=True)
        paths.update(p.resolve() for p in ([root] if root.is_file() else root.rglob('*'))
                     if p.is_file() and p.suffix.lower() in core.VIDEOS | core.PHOTOS)
    records = []
    for path in sorted(paths):
        before = path.stat()
        digest = fingerprint(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f'Source changed while hashing: {path}')
        records.append(dict(path=str(path), sha256=digest, size=after.st_size,
                            mtime_ns=after.st_mtime_ns))
    identity = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
    return dict(schema_version=1, manifest_id=identity, media=records)


def annotation_template(data):
    return dict(schema_version=1, manifest_id=data['manifest_id'],
                status='尚未評估', segments=[],
                instructions='segments: {sha256, start, end, decision: include|exclude, note}; seconds in source time')


def verify_manifest(data):
    for item in data['media']:
        path = Path(item['path'])
        if not path.is_file() or fingerprint(path) != item['sha256']:
            raise ValueError(f'Manifest mismatch: {path}')


def replay(index, target=180, shot=5, minimum=45):
    """Freeze an existing cache in memory: never migrate/write the original database."""
    started = time.monotonic()
    errors = []
    with closing(readonly_db(index)) as source, closing(sqlite3.connect(':memory:')) as db:
        source.backup(db)
        count = db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]
        errors = [dict(candidate_id=r[0], error=r[1]) for r in db.execute(
            "SELECT id,error FROM candidates WHERE error IS NOT NULL AND error!='' ORDER BY id")]
        plan = core.choose(db, target, shot, minimum)
        hashes = {r[0]: r[1] for r in db.execute('SELECT id,phash FROM candidates')}
    duplicate_count = sum(any(core.distance(hashes.get(p['candidate_id']), hashes.get(q['candidate_id'])) <= 5
                              for q in plan[:i]) for i, p in enumerate(plan))
    comparable = all(hashes.get(p['candidate_id']) for p in plan)
    return dict(candidate_count=count, plan=plan, errors=errors,
                selection_seconds=sum(p['seconds'] for p in plan),
                duplicate_ratio=duplicate_count / len(plan) if plan and comparable else None,
                duplicate_definition='selected candidates matching an earlier dHash within 5 bits; proxy only',
                planning_seconds=time.monotonic() - started,
                analysis_seconds=None, quality_status='尚未評估',
                quality_note='No human quality metric inferred from algorithm scores; cache replay excludes AI runtime.')


def report_markdown(result):
    return ('# Benchmark\n\n'
            f"- Status: {result.get('status', 'ok')}\n"
            f"- Mode: {result.get('mode')}\n"
            f"- Manifest: {result.get('manifest_id')}\n"
            f"- Candidates: {result.get('candidate_count', 0)}\n"
            f"- Selected: {len(result.get('plan', []))}\n"
            f"- Duplicate ratio (dHash proxy): {result.get('duplicate_ratio')}\n"
            f"- Analysis seconds: {result.get('analysis_seconds')}\n"
            f"- Planning seconds: {result.get('planning_seconds')}\n"
            f"- Human quality: {result.get('quality_status', '尚未評估')}\n"
            f"- Errors: {json.dumps(result.get('errors', []), ensure_ascii=False)}\n")


def compare(a, b):
    if a['manifest_id'] != b['manifest_id']:
        raise ValueError('Cannot compare different manifests')
    left = {p['candidate_id'] for p in a.get('plan', [])}
    right = {p['candidate_id'] for p in b.get('plan', [])}
    return dict(schema_version=1, manifest_id=a['manifest_id'],
                candidate_delta=b.get('candidate_count', 0)-a.get('candidate_count', 0),
                shared=sorted(left & right), removed=sorted(left-right), added=sorted(right-left),
                quality_status='尚未評估',
                note='Selection differences are not evidence of improved quality.')


def safe_output(output, data):
    output = Path(output).resolve()
    for item in data['media']:
        source = Path(item['path']).resolve()
        if output == source or output.is_relative_to(source.parent):
            raise ValueError('Benchmark output must be outside source directories')
    output.mkdir(parents=True, exist_ok=False)
    return output


def run(data, output, index=None, analyze=False, model='gemma3:4b', target=180, analyze_limit=0):
    verify_manifest(data)
    output = safe_output(output, data)
    result = dict(schema_version=1, manifest_id=data['manifest_id'], status='ok',
                  mode='cache-replay' if index else 'legacy-live', quality_status='尚未評估',
                  errors=[], model=model, target_seconds=target, analyze_limit=analyze_limit)
    result['revision'] = subprocess.run(['git','rev-parse','HEAD'], capture_output=True,
                                        text=True, check=True).stdout.strip()
    started = time.monotonic()
    try:
        if index:
            with closing(readonly_db(index)) as source:
                indexed = {r[0] for r in source.execute('SELECT path FROM media WHERE error IS NULL')}
            if indexed != {i['path'] for i in data['media']}:
                raise ValueError('Cache sources do not match the fixed manifest')
            result.update(replay(index, target=target))
        else:
            with closing(core.connect(output/'legacy')) as db:
                core.scan(db, [Path(i['path']) for i in data['media']], output/'legacy', 0)
                core.candidates(db, 8, 36)
                scanned = db.execute('SELECT COUNT(*) FROM media').fetchone()[0]
                if scanned != len(data['media']):
                    raise RuntimeError(f'Incomplete media scan: {scanned}/{len(data["media"])}; check FFprobe')
                scan_end = time.monotonic()
                if analyze:
                    core.analyze(db, output/'legacy', model, analyze_limit, 8, 36, False,
                                 mode='quality', temporal=False, timeout=120)
                analysis_end = time.monotonic()
            result.update(replay(output/'legacy'/'index.sqlite', target=target))
            result.update(scan_seconds=scan_end-started,
                          analysis_seconds=analysis_end-scan_end if analyze else None,
                          mode='legacy-live' if analyze else 'legacy-candidates-only')
        verify_manifest(data)
    except Exception as exc:
        result['status'] = 'failed'
        result['errors'].append(dict(error=str(exc), type=type(exc).__name__))
    result['elapsed_seconds'] = time.monotonic()-started
    save_json_atomic(output/'result.json', result)
    (output/'report.md').write_text(report_markdown(result), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('manifest'); make.add_argument('--input', action='append', required=True)
    make.add_argument('--out', type=Path, required=True)
    execute = sub.add_parser('run'); execute.add_argument('--manifest', type=Path, required=True)
    execute.add_argument('--out', type=Path, required=True)
    execute.add_argument('--index', type=Path); execute.add_argument('--analyze', action='store_true')
    execute.add_argument('--model', default='gemma3:4b'); execute.add_argument('--seconds', type=int, default=180)
    execute.add_argument('--analyze-limit', type=int, default=0)
    diff = sub.add_parser('compare'); diff.add_argument('before', type=Path); diff.add_argument('after', type=Path)
    diff.add_argument('--out', type=Path, required=True)
    strategy = sub.add_parser('candidates')
    strategy.add_argument('--manifest', type=Path, required=True)
    strategy.add_argument('--out', type=Path, required=True)
    strategy.add_argument('--strategy', choices=['fixed','scene'], required=True)
    strategy.add_argument('--no-technical', action='store_true')
    assess = sub.add_parser('assess')
    assess.add_argument('--manifest', type=Path, required=True)
    assess.add_argument('--candidates', type=Path, required=True)
    assess.add_argument('--out', type=Path, required=True)
    assess.add_argument('--cache', type=Path)
    assess.add_argument('--model', default='gemma3:4b')
    assess.add_argument('--limit', type=int, default=12, help='0=all candidates; default bounded review')
    propose=sub.add_parser('recommend')
    propose.add_argument('--assessments',type=Path,required=True)
    propose.add_argument('--out',type=Path,required=True)
    propose.add_argument('--seconds',type=float,default=180)
    propose.add_argument('--existing-plan',type=Path)
    propose.add_argument('--review-file',type=Path)
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    if args.command == 'manifest':
        data = manifest(args.input); output = safe_output(args.out, data)
        save_json_atomic(output/'manifest.json', data)
        save_json_atomic(output/'annotations.json', annotation_template(data))
    elif args.command == 'run':
        if args.seconds <= 0 or args.analyze_limit < 0: parser.error('Invalid seconds/analyze-limit')
        return 0 if run(read(args.manifest), args.out, args.index, args.analyze, args.model, args.seconds,args.analyze_limit)['status']=='ok' else 1
    elif args.command == 'recommend':
        from recommendation_v16 import recommend
        data=read(args.assessments)
        existing=read(args.existing_plan)['plan'] if args.existing_plan else []
        review=read(args.review_file) if args.review_file else {}
        result=recommend(data['candidates'],args.seconds,existing=existing,
                         excluded_ids=review.get('excluded_ids',[]),excluded_paths=review.get('excluded_paths',[]))
        result.update(manifest_id=data['manifest_id'],mode='v16-recommendation',quality_status='尚未評估')
        if args.out.exists():raise ValueError('Never overwrite an existing plan')
        save_json_atomic(args.out,result)
        args.out.with_suffix('.md').write_text(report_markdown(result),encoding='utf-8')
    elif args.command == 'assess':
        from assessment_v16 import AssessmentCache, model_identity, SCHEMA_VERSION, PROMPT_VERSION
        data=read(args.manifest); verify_manifest(data); source=read(args.candidates)
        if source['manifest_id'] != data['manifest_id']: raise ValueError('Candidate manifest mismatch')
        if args.limit < 0: raise ValueError('Invalid review limit')
        media={i['path']:i['sha256'] for i in data['media']}
        candidates=source['candidates']
        for c in candidates:
            if media.get(c['path']) != c['source_sha256']: raise ValueError('Candidate source mismatch')
        output=safe_output(args.out,data)
        cache_path=args.cache or output/'assessments.sqlite'
        for item in data['media']:
            if Path(cache_path).resolve().is_relative_to(Path(item['path']).parent): raise ValueError('Cache cannot be written under source directory')
        model,digest=model_identity(args.model)
        # Round-robin sources before spending the bounded LLM budget.
        grouped={}
        for c in candidates: grouped.setdefault(c['path'],[]).append(c)
        pending=[]
        while any(grouped.values()):
            for path in sorted(grouped):
                if grouped[path]: pending.append(grouped[path].pop(0))
        if args.limit: pending=pending[:args.limit]
        result=dict(schema_version=SCHEMA_VERSION,prompt_version=PROMPT_VERSION,manifest_id=data['manifest_id'],
                    model=model,model_digest=digest,candidate_count=len(candidates),review_limit=args.limit,
                    candidates=[],errors=[],quality_status='尚未評估',mode='v16-assessment')
        started=time.monotonic();cache=AssessmentCache(cache_path)
        try:
            for c in pending:
                evaluated=cache.assess(c,model,digest)
                result['candidates'].append(dict(c,analysis=evaluated))
                if evaluated['status']=='failed':result['errors'].append(dict(id=c['id'],error=evaluated['error']))
                save_json_atomic(output/'result.json',result)
        finally:cache.close()
        result['analysis_seconds']=time.monotonic()-started
        result['status']='failed' if result['errors'] else 'ok'
        verify_manifest(data);save_json_atomic(output/'result.json',result)
        (output/'report.md').write_text(report_markdown(result),encoding='utf-8')
        return 1 if result['errors'] else 0
    elif args.command == 'candidates':
        from candidate_engine import generate, near_duplicate
        data = read(args.manifest); verify_manifest(data)
        output = safe_output(args.out, data); started = time.monotonic()
        result = dict(schema_version=1, manifest_id=data['manifest_id'], mode=args.strategy,
                      candidates=[], errors=[], quality_status='尚未評估')
        for item in data['media']:
            try: result['candidates'].extend(generate(item,args.strategy,technical=not args.no_technical))
            except Exception as exc: result['errors'].append(dict(path=item['path'],error=str(exc)))
        result['candidate_count'] = len(result['candidates'])
        result['analysis_seconds'] = time.monotonic()-started
        result['duplicate_ratio'] = (sum(any(near_duplicate(c.get('technical',{}),p.get('technical',{}))
            for p in result['candidates'][:i]) for i,c in enumerate(result['candidates']))/result['candidate_count']) if result['candidate_count'] and not args.no_technical else None
        result['status'] = 'failed' if result['errors'] else 'ok'
        verify_manifest(data)
        save_json_atomic(output/'result.json',result)
        (output/'report.md').write_text(report_markdown(result),encoding='utf-8')
        return 1 if result['errors'] else 0
    else:
        data = compare(read(args.before), read(args.after))
        if args.out.exists(): raise ValueError('Comparison output already exists')
        save_json_atomic(args.out, data)
        args.out.with_suffix('.md').write_text('# Comparison\n\n```json\n'+json.dumps(data, indent=2, ensure_ascii=False)+'\n```\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
