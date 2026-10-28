"""Deterministic bounded recommendations. Never writes a user's selection file."""
from __future__ import annotations
import copy
import math
from assessment_v16 import validate
from candidate_engine import near_duplicate


def recommend(candidates, target=180., shot=5., existing=(), excluded_ids=(), excluded_paths=()):
    if not math.isfinite(target) or not math.isfinite(shot) or target<=0 or shot<.5:
        raise ValueError('Invalid duration settings')
    plan=copy.deepcopy(list(existing))
    used=sum(p['seconds'] for p in plan)
    if any(not math.isfinite(p['seconds']) or p['seconds']<=0 for p in plan):raise ValueError('Invalid existing plan')
    excluded_ids=set(excluded_ids);excluded_paths=set(excluded_paths)
    selected_ids={p['candidate_id'] for p in plan};sources={};categories={}
    for part in plan:
        sources[part['path']]=sources.get(part['path'],0)+1
        categories[part.get('category')]=categories.get(part.get('category'),0)+1
    eligible=[]
    for candidate in sorted(candidates,key=lambda c:(c['path'],c['start'],c['id'])):
        if candidate['id'] in selected_ids|excluded_ids or candidate['path'] in excluded_paths:continue
        analysis=candidate.get('analysis',{})
        if analysis.get('status')!='ok':continue
        score=validate(analysis['assessment'])
        if candidate['kind']=='video' and not (0<=candidate['start']<candidate['end']<=candidate['source_duration']):
            raise ValueError('Candidate outside source bounds')
        eligible.append((candidate,score))
    source_count=len({c['path'] for c,s in eligible})
    cap=max(2,math.ceil(math.ceil(target/shot)/max(1,source_count)))
    by_id={c['id']:c for c in candidates}
    selected=[by_id[p['candidate_id']] for p in plan if p['candidate_id'] in by_id]
    while used < target-.499:
        feasible=[(c,s) for c,s in eligible if c['id'] not in selected_ids
                  and sources.get(c['path'],0)<cap
                  and not any(near_duplicate(c.get('technical',{}),x.get('technical',{})) for x in selected)]
        if not feasible:break
        def rank(item):
            c,s=item
            return (.30*s['technical_quality']+.40*s['visual_interest']+.30*s['event_importance']
                    -12*sources.get(c['path'],0)-8*categories.get(s['category'],0))
        c,s=max(feasible,key=rank)
        selected_ids.add(c['id'])
        seconds=min(shot,target-used,c['end']-c['start'] if c['kind']=='video' else shot)
        if seconds<.5:continue
        start=max(c['start'],(c['start']+c['end']-seconds)/2) if c['kind']=='video' else 0.
        reason=dict(technical_quality=s['technical_quality'],visual_interest=s['visual_interest'],
                    event_importance=s['event_importance'],prior_source_count=sources.get(c['path'],0),
                    prior_category_count=categories.get(s['category'],0),
                    redundancy='no confirmed multi-frame match with selected representatives',
                    story_relevance=None)
        plan.append(dict(candidate_id=c['id'],path=c['path'],kind=c['kind'],start=start,seconds=seconds,
                         source_duration=c['source_duration'],candidate_position=(c['start']+c['end'])/2,
                         scene_start=c['start'],scene_end=c['end'],category=s['category'],
                         description=s['description'],score=None,event=s['event_importance'],
                         trim_locked=True,reason=reason))
        sources[c['path']]=sources.get(c['path'],0)+1
        categories[s['category']]=categories.get(s['category'],0)+1
        used+=seconds;selected.append(c)
    return dict(schema_version=1,target_seconds=target,selection_seconds=used,plan=plan,
                shortfall_seconds=max(0.,target-used),overrun_seconds=max(0.,used-target),
                note='Proposal only. Existing edits preserved; source scarcity is not padded or repeated.')
