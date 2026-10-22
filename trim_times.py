"""Python-only trim validation shared by GUI and tests."""
import math


def parse_time(value):
    parts=str(value).strip().split(':')
    if not 1<=len(parts)<=3:raise ValueError('請輸入秒數、分:秒或時:分:秒。')
    try:nums=[float(x) for x in parts]
    except ValueError as exc:raise ValueError('時間格式不正確，請輸入 12.5 或 00:12.5。') from exc
    if any(not math.isfinite(n) or n<0 for n in nums):raise ValueError('時間不能為負數、無限大或非數值。')
    if len(parts)>1 and any(x>=60 for x in nums[1:]):raise ValueError('分、秒欄位必須小於 60。')
    value=0.
    for n in nums:value=value*60+n
    return round(value,3)


def validate_times(start,end,duration):
    start,end,duration=map(float,(start,end,duration))
    if not all(map(math.isfinite,(start,end,duration))):raise ValueError('時間必須是有限數值。')
    if not 0<=start<end:raise ValueError('結束時間必須晚於開始時間。')
    if end>duration+0.005:raise ValueError(f'結束時間不可超過來源影片長度 {duration:.3f} 秒。')
    if end-start<0.5:raise ValueError('保留片段不可短於 0.5 秒。')
    return round(start,3),round(min(end,duration),3)


def display_time(seconds):
    seconds=max(0.,float(seconds))
    hours=int(seconds//3600);minutes=int(seconds//60)%60
    if hours:return f'{hours:02d}:{minutes:02d}:{seconds%60:06.3f}'
    return f'{minutes:02d}:{seconds%60:06.3f}'
