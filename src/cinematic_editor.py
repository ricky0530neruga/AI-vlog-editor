#!/usr/bin/env python3
"""V4.3 cinematic output layer. Reads sources; writes only under the output dir.

Uses only the Python standard library and FFmpeg/FFprobe. It never removes or
modifies source media. Rendering is deliberately chunked to bound FFmpeg usage.
"""
from __future__ import annotations

from array import array
import copy
import hashlib
import json
import math
import shutil
from pathlib import Path
import statistics
import subprocess
import sys

import vlog_maker as core

FPS = 30
GROUP_SIZE = 6  # Most boundaries dissolve; periodic chapter cuts limit CPU/RAM.


def _run(args):
    return core.command(args)


def _probe_streams(path):
    return json.loads(core.command(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)], True))


def _has_audio(path):
    info = _probe_streams(path)
    return any(s.get('codec_type') == 'audio' for s in info.get('streams',[]))


def _duration(path):
    info = _probe_streams(path)
    video = next((s for s in info.get('streams',[]) if s.get('codec_type') == 'video'), {})
    try:
        return float(video.get('duration') or info.get('format',{}).get('duration') or 0)
    except (ValueError, TypeError):
        return 0.


def _source_max(part):
    if part['kind'] == 'photo':
        return 11.0
    return min(11.0, float(part.get('source_duration') or part['start'] + part['seconds']))


def _resize_preserving_center(part, seconds):
    if part.get('trim_locked'):
        raise ValueError('已鎖定的裁切區間不可自動更改。')
    seconds = round(max(0.5,seconds), 3)
    if part['kind'] == 'video':
        full = float(part.get('source_duration') or part['start'] + part['seconds'])
        center = float(part.get('candidate_position',part['start'] + part['seconds']/2))
        part['start'] = round(max(0.,min(max(0,full-seconds),center-seconds/2)),3)
    part['seconds'] = seconds


def _extend_for_crossfades(plan, target, crossfade):
    """Recover approximate lost xfade time, subject to actual source-duration caps."""
    gaps = (len(plan) - math.ceil(len(plan)/GROUP_SIZE)) if crossfade else 0
    overlap = 0.4 * gaps
    for _ in range(12):
        missing = target - (sum(p['seconds'] for p in plan) - overlap)
        if missing <= 0.05:
            break
        adjustable = [p for p in plan if not p.get('trim_locked') and _source_max(p) - p['seconds'] > 0.06]
        if not adjustable:
            break
        each = missing / len(adjustable)
        for p in adjustable:
            _resize_preserving_center(p,min(_source_max(p),p['seconds']+each))
    return overlap


def _audio_onsets(music: Path, target: float):
    """Approximate attack/energy peaks, NOT a musical tempo or beat tracker."""
    max_time = min(float(target) + 5., 900.)
    cmd = ['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-i',str(music),'-t',str(max_time),
           '-vn','-ac','1','-ar','8000','-f','s16le','pipe:1']
    raw = core.command(cmd,True,True)
    if len(raw) < 8000:
        return []
    samples = array('h')
    samples.frombytes(raw[:len(raw)//2*2])
    # 50 ms blocks; mean absolute energy is cheap and robust on CPU.
    block = 400
    energies = [sum(abs(int(v)) for v in samples[i:i+block])/block
                for i in range(0,len(samples)-block+1,block)]
    if len(energies) < 12:
        return []
    flux = [0.,0.]+[max(0.,energies[i]-energies[i-2]) for i in range(2,len(energies))]
    positive = [f for f in flux if f > 0]
    if not positive:
        return []
    threshold = max(175.0, statistics.median(positive) * 2.5)
    peaks = []
    for i in range(3,len(flux)-3):
        if flux[i] > threshold and flux[i] >= max(flux[i-3:i+4]):
            sec = i*0.05
            if not peaks or sec-peaks[-1]>=0.30:
                peaks.append(sec)
    return peaks


def _nudge_cuts_to_onsets(plan, onsets):
    if len(plan) < 2 or not onsets:
        return 0
    changes=0
    position=0.
    for index in range(len(plan)-1):
        a,b=plan[index],plan[index+1]
        position += a['seconds']
        if a.get('trim_locked') or b.get('trim_locked'):
            continue
        possible = min(onsets,key=lambda t:abs(t-position))
        adjustment=possible-position
        if abs(adjustment)>0.18 or abs(adjustment)<0.035:
            continue
        # Keep total duration unchanged; never extend past actual video length.
        a_new=a['seconds']+adjustment
        b_new=b['seconds']-adjustment
        if min(a_new,b_new)<1.5 or a_new>_source_max(a) or b_new>_source_max(b):
            continue
        _resize_preserving_center(a,a_new)
        _resize_preserving_center(b,b_new)
        position += adjustment
        changes += 1
    return changes


def _encode_clip(part, dest, crf, is_first, is_last, preserve_audio):
    """Normalize all clips to H.264 + 48k stereo AAC for safe concat/xfade."""
    seconds = max(0.5,float(part['seconds']))
    fade_in = ',fade=t=in:st=0:d=0.8' if is_first and seconds>=1.2 else ''
    fade_out = f',fade=t=out:st={max(0,seconds-1.2):.3f}:d=1.2' if is_last and seconds>=1.8 else ''
    vf = ('scale=1920:1080:force_original_aspect_ratio=decrease,'
          'pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30,format=yuv420p' + fade_in + fade_out)
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
    if part['kind']=='photo':
        cmd+=['-loop','1','-framerate','30','-i',part['path']]
    else:
        cmd+=['-ss',str(part['start']),'-i',part['path']]
    if not preserve_audio or part['kind']=='photo' or not _has_audio(part['path']):
        cmd+=['-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000']
        audio_index=1
    else:
        audio_index=0
    # Sound from important activities/person interactions stays more audible.
    ambience = 0.85 if part.get('role')=='highlight' or part.get('people') else 0.40
    cmd+=['-t',f'{seconds:.3f}','-map','0:v:0', '-map',f'{audio_index}:a:0',
          '-vf',vf,'-af',f'aresample=async=1:first_pts=0,volume={ambience if audio_index==0 else 1.0},apad,atrim=duration={seconds:.3f}',
          '-c:v','libx264','-preset','veryfast','-crf',str(crf),'-pix_fmt','yuv420p',
          '-r','30','-c:a','aac','-b:a','160k','-ar','48000','-ac','2',
          '-movflags','+faststart',str(dest)]
    _run(cmd)


def _render_group(paths, target, crf, fade):
    """Dissolve up to six shots with xfade + audio acrossfade."""
    if len(paths)==1:
        return paths[0]
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
    for p in paths:
        cmd+=['-i',str(p)]
    pieces=[]
    for i in range(len(paths)):
        pieces += [f'[{i}:v]setpts=N/(30*TB),fps=30,format=yuv420p[v{i}]',
                   f'[{i}:a]asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0[a{i}]']
    durations=[_duration(p) for p in paths]
    # MP4/AAC timing is not exact to the millisecond; clamp to shortest safe fade.
    overlap=min(fade, min(durations)*0.18)
    current_v='v0';current_a='a0'; total=durations[0]
    for i in range(1,len(paths)):
        out_v=f'vx{i}';out_a=f'ax{i}'
        offset=max(0.,total-overlap)
        pieces.append(f'[{current_v}][v{i}]xfade=transition=fade:duration={overlap:.3f}:offset={offset:.3f},fps=30[{out_v}]')
        pieces.append(f'[{current_a}][a{i}]acrossfade=d={overlap:.3f}:c1=tri:c2=tri[{out_a}]')
        total += durations[i]-overlap
        current_v=out_v;current_a=out_a
    pieces.append(f'[{current_a}]apad,atrim=duration={total:.3f}[mixed_a]')
    cmd+=['-filter_complex',';'.join(pieces),'-map',f'[{current_v}]','-map','[mixed_a]',
          '-c:v','libx264','-preset','veryfast','-crf',str(crf),'-r','30',
          '-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-ar','48000','-ac','2',
          '-t',f'{total:.3f}','-movflags','+faststart',str(target)]
    _run(cmd)
    return target


def _mix_and_finish(concat_file, music, output, target):
    if music:
        # Music is looped; native sound stays at clip-dependent level and peaks are limited.
        fadeout=max(0.,target-2.)
        cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
             '-i',str(concat_file),'-stream_loop','-1','-i',str(music),
             '-filter_complex',
             f'[1:a:0]aresample=48000,volume=0.28,atrim=duration={target:.3f},asetpts=PTS-STARTPTS[bg];'
             f'[0:a:0]aresample=48000,asetpts=PTS-STARTPTS[nat];'
             f'[nat][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,'
             f'alimiter=limit=0.95,afade=t=in:st=0:d=1.2,afade=t=out:st={fadeout:.3f}:d=2[outa]',
             '-map','0:v:0','-map','[outa]','-c:v','copy','-c:a','aac','-b:a','192k',
             '-t',f'{target:.3f}','-movflags','+faststart',str(output)]
        _run(cmd)
    else:
        shutil.copy2(concat_file,output)


def render_v43(plan, out, target, music=None, crf=21, force=False,
               transition=True, preserve_audio=True, beat_sync=True):
    """Write V4.3 MP4 and a new plan; never modify V4.2 outputs or input media."""
    out=Path(out)
    plan=copy.deepcopy(plan)
    target=float(target)
    if not plan:
        raise ValueError('No eligible clips for V4.3')
    overlap=_extend_for_crossfades(plan,target,transition)
    onsets=[];beats=0
    if beat_sync and music and Path(music).is_file():
        try:
            onsets=_audio_onsets(Path(music),target)
            beats=_nudge_cuts_to_onsets(plan,onsets)
        except Exception as exc:
            print('[BEAT] 無法分析音樂節奏點，繼續一般剪輯：'+str(exc)[:150],flush=True)
    clips=out/'clips_v43';clips.mkdir(parents=True,exist_ok=True)
    groups_dir=out/'groups_v43';groups_dir.mkdir(parents=True,exist_ok=True)
    source_outputs=[]
    for i,part in enumerate(plan,1):
        stat=Path(part['path']).stat()
        key=hashlib.sha256(json.dumps([str(part['path']),stat.st_size,stat.st_mtime,part['start'],
                  part['seconds'],part.get('people'),part.get('role'),crf,preserve_audio,i==1,i==len(plan),'V1.4'],sort_keys=True).encode()).hexdigest()[:20]
        clip=clips/f'{key}.mp4';source_outputs.append(clip)
        reused=not force and clip.exists() and clip.stat().st_size>=1000
        if not reused:
            temp=clip.with_name(key+'.partial.mp4')
            _encode_clip(part,temp,crf,i==1,i==len(plan),preserve_audio)
            temp.replace(clip)
        print(f'[V4.3 CLIP {i}/{len(plan)}] '+('Cached ' if reused else 'Encoded ')+Path(part['path']).name,flush=True)
    render_groups=[]
    for begin in range(0,len(source_outputs),GROUP_SIZE):
        group=source_outputs[begin:begin+GROUP_SIZE]
        if transition and len(group)>1:
            key=hashlib.sha256(json.dumps([p.name for p in group]+[crf,'fade:0.4']).encode()).hexdigest()[:20]
            dest=groups_dir/f'{key}.mp4'
            if force or not dest.exists() or dest.stat().st_size<1000:
                temp=groups_dir/f'{key}.partial.mp4'
                _render_group(group,temp,crf,0.4)
                temp.replace(dest)
        else:
            dest=None
        render_groups.append(dest if dest else group[0] if len(group)==1 else None)
        if dest is None and len(group)>1:
            render_groups[-1]=group  # no transitions: flatten clips below
        print(f'[V4.3 GROUP {len(render_groups)}/{math.ceil(len(source_outputs)/GROUP_SIZE)}]',flush=True)
    ordered=[]
    for group in render_groups:
        ordered.extend(group if isinstance(group,list) else [group])
    # Use a concat manifest with normalized forward slash paths, resilient to spaces.
    manifest=out/'concat_v43.txt'
    def escape_path(p):
        return p.resolve().as_posix().replace("'", "'\\''")
    manifest.write_text('ffconcat version 1.0\n'+''.join(f"file '{escape_path(p)}'\n" for p in ordered),encoding='utf-8')
    merged=out/'merged_v43.mp4'
    _run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
          '-f','concat','-safe','0','-i',str(manifest),'-c','copy','-movflags','+faststart',str(merged)])
    actual=_duration(merged)
    final=out/'Travel_Vlog_Final_V43.mp4'
    _mix_and_finish(merged, music,final,actual)
    timeline={'version':'4.3','target_seconds':target,'expected_crossfade_loss':overlap,
              'actual_seconds':round(_duration(final),3),'transitions':'grouped dissolve' if transition else 'hard cuts',
              'preserve_audio':preserve_audio,'beat_alignment':'approximate onset' if beat_sync and music else 'off',
              'detected_onsets':len(onsets),'adjusted_cuts':beats,'plan':plan}
    planpath=out/'edit_plan_v43.json'
    planpath.write_text(json.dumps(timeline,ensure_ascii=False,indent=2),encoding='utf-8')
    if actual<target-2:
        print(f'[NOTICE] 可用素材不足或交叉淡化造成片長較短：{actual:.1f}s／目標 {target:.1f}s；未重複或慢放原片。',flush=True)
    print('[V4.3 DONE]',final,flush=True)
    print('[V4.3 PLAN]',planpath,flush=True)
    return final
