"""Opt-in CPU candidate generation. Does not write sources or legacy SQLite."""
from __future__ import annotations
import hashlib
import math
from pathlib import Path
import re
import statistics
import subprocess

import vlog_maker as core

STRATEGY_VERSION = 'candidates-1'


def scene_cuts(path, threshold=0.30):
    if not 0 < threshold < 1: raise ValueError('Invalid scene threshold')
    # Keep native timestamps; resize before scoring. No LLM and no GPU required.
    proc = subprocess.run([core.exe('ffmpeg'), '-nostdin', '-hide_banner', '-i', str(path),
        '-an', '-vf', f"scale=160:-2,select='gt(scene,{threshold})',showinfo",
        '-fps_mode', 'vfr', '-f', 'null', '-'], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=900)
    log = proc.stderr.decode('utf-8', 'replace')
    if proc.returncode: raise RuntimeError(log[-1800:])
    return sorted(set(float(x) for x in re.findall(r'pts_time:([0-9.eE+\-]+)', log)))


def intervals(duration, mode='fixed', step=8., maximum=36, cuts=()):
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(step) or step <= 0 or maximum < 1:
        raise ValueError('Invalid candidate settings')
    if mode == 'fixed':
        n = min(maximum, max(1, math.ceil(duration / step)))
        return [(i*duration/n, (i+1)*duration/n) for i in range(n)]
    if mode != 'scene': raise ValueError('Unknown strategy')
    boundaries = [0.] + sorted(set(float(x) for x in cuts if math.isfinite(x) and 0 < x < duration)) + [duration]
    # Preserve every detected scene interval. Long scenes use multiple representatives.
    return list(zip(boundaries, boundaries[1:]))


def representatives(start, end):
    if not 0 <= start < end: raise ValueError('Invalid interval')
    fractions = (0.2, 0.5, 0.8) if end-start >= 4 else (0.5,)
    return [start+(end-start)*f for f in fractions]


def frame(path, position):
    raw = core.command(['ffmpeg','-nostdin','-v','error','-ss',str(position),'-i',str(path),
        '-frames:v','1','-vf','scale=64:36,format=gray','-f','rawvideo','-'], True, True)
    if len(raw) != 64*36: raise ValueError('Incomplete representative frame')
    return raw


def frame_metrics(raw, width=64, height=36):
    if len(raw) != width*height or width < 3 or height < 3: raise ValueError('Invalid frame')
    laplacian = [4*raw[y*width+x]-raw[y*width+x-1]-raw[y*width+x+1]-raw[(y-1)*width+x]-raw[(y+1)*width+x]
                 for y in range(1,height-1) for x in range(1,width-1)]
    bits = 0
    for y in range(8):
        for x in range(8):
            row = round(y*(height-1)/7)*width
            bits = (bits << 1) | int(raw[row+round(x*(width-1)/8)] > raw[row+round((x+1)*(width-1)/8)])
    return dict(brightness=statistics.mean(raw), laplacian_variance=statistics.pvariance(laplacian),
                contrast=statistics.pstdev(raw), dhash=f'{bits:016x}')


def technical_summary(frames, adjacent_pairs=()):
    metrics = [frame_metrics(raw) for raw in frames]
    if not metrics: raise ValueError('No representative frames')
    # Adjacent pixel difference cannot distinguish subject movement from camera shake.
    motion = [statistics.mean(abs(a-b) for a,b in zip(left,right))/255
              for left,right in adjacent_pairs if len(left)==len(right)==64*36]
    flags = []
    if any(m['brightness'] < 13 for m in metrics): flags.append('dark_representative')
    if any(m['laplacian_variance'] < 20 for m in metrics): flags.append('soft_or_low_detail')
    if motion and max(motion) > .20: flags.append('motion_risk_unconfirmed_shake')
    return dict(frames=metrics, brightness_median=statistics.median(m['brightness'] for m in metrics),
                blur_proxy_median=statistics.median(m['laplacian_variance'] for m in metrics),
                motion_proxy=max(motion) if motion else None, camera_shake=None,
                flags=flags, reject=False, confidence=None)


def near_duplicate(a, b, threshold=5):
    """Conservative multi-representative visual proxy; flat frames stay uncertain."""
    left = [f for f in a.get('frames', []) if f['contrast'] >= 8]
    right = [f for f in b.get('frames', []) if f['contrast'] >= 8]
    if len(left) < 2 or len(right) < 2: return False
    return (sum(any(core.distance(x['dhash'],y['dhash']) <= threshold for y in right) for x in left)/len(left) >= 2/3
            and sum(any(core.distance(x['dhash'],y['dhash']) <= threshold for x in left) for y in right)/len(right) >= 2/3)


def generate(item, mode='fixed', step=8., maximum=36, technical=True):
    path = Path(item['path'])
    duration = core.probe(path)[0] if path.suffix.lower() in core.VIDEOS else 0
    ranges = intervals(duration, mode, step, maximum, scene_cuts(path) if mode=='scene' else ()) if duration else [(0.,0.)]
    result = []
    for start,end in ranges:
        positions = representatives(start,end) if duration else [0.]
        identity = f"{STRATEGY_VERSION}|{item['sha256']}|{mode}|{start:.9f}|{end:.9f}"
        candidate = dict(id=hashlib.sha256(identity.encode()).hexdigest()[:24], path=str(path),
                         source_sha256=item['sha256'], kind='video' if duration else 'photo',
                         start=start, end=end, positions=positions, strategy=mode,
                         strategy_version=STRATEGY_VERSION, source_duration=duration)
        if technical:
            raws = [frame(path,p) for p in positions]
            pairs = [(raw, frame(path,min(duration-.001,p+.1))) for raw,p in zip(raws,positions)] if duration else []
            candidate['technical'] = technical_summary(raws,pairs)
        result.append(candidate)
    return result
