import random
import time
import math
import os
import asyncio
import collections
from vars import CREDIT
from pyrogram.errors import FloodWait
from datetime import datetime, timedelta

class Timer:  
    def __init__(self, time_between=4):  
        self.start_time = time.time()  
        self.time_between = time_between  

    def can_send(self):  
        if time.time() > (self.start_time + self.time_between):  
            self.start_time = time.time()  
            return True  
        return False  

# ── Rolling-window speed tracker ──────────────────────────────────────────────
class SpeedTracker:
    """Track real-time speed using a sliding window of the last N samples."""
    def __init__(self, window=8):
        self._samples = collections.deque(maxlen=window)   # (time, bytes)

    def update(self, current_bytes: int):
        self._samples.append((time.time(), current_bytes))

    @property
    def speed(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        t0, b0 = self._samples[0]
        t1, b1 = self._samples[-1]
        dt = t1 - t0
        return (b1 - b0) / dt if dt > 0 else 0.0

# Global speed tracker (one per upload session – reset via SpeedTracker())
_speed_tracker = SpeedTracker()

def hrb(value, digits=2, delim="", postfix=""):  
    """Return a human-readable file size."""  
    if value is None:  
        return None  
    chosen_unit = "B"  
    for unit in ("KB", "MB", "GB", "TB"):  
        if value > 1000:  
            value /= 1024  
            chosen_unit = unit  
        else:  
            break  
    return f"{value:.{digits}f}" + delim + chosen_unit + postfix  

def hrt(seconds, precision=0):  
    """Return a human-readable time delta as a string."""  
    pieces = []  
    value = timedelta(seconds=max(0, seconds))

    if value.days:  
        pieces.append(f"{value.days}d")  

    seconds = value.seconds  

    if seconds >= 3600:  
        hours = int(seconds / 3600)  
        pieces.append(f"{hours}h")  
        seconds -= hours * 3600  

    if seconds >= 60:  
        minutes = int(seconds / 60)  
        pieces.append(f"{minutes}m")  
        seconds -= minutes * 60  

    if seconds > 0 or not pieces:  
        pieces.append(f"{seconds}s")  

    if not precision:  
        return " ".join(pieces)  

    return " ".join(pieces[:precision])  

timer = Timer()

# ── Animated upload bar ────────────────────────────────────────────────────────
_FILLED  = "█"
_EMPTY   = "░"
BAR_LEN  = 12

async def progress_bar(current, total, reply, start):
    if not timer.can_send():
        return

    now  = time.time()
    diff = now - start
    if diff < 0.5:
        return

    # update rolling speed
    _speed_tracker.update(current)
    speed = _speed_tracker.speed or (current / diff if diff > 0 else 0)

    perc_val = current * 100 / total if total else 0
    perc     = f"{perc_val:.1f}%"

    remaining_bytes = total - current
    eta  = hrt(remaining_bytes / speed, precision=2) if speed > 0 else "—"
    sp   = hrb(speed) + "/s"
    tot  = hrb(total)
    cur  = hrb(current)

    filled         = int(perc_val / 100 * BAR_LEN)
    bar            = _FILLED * filled + _EMPTY * (BAR_LEN - filled)

    try:
        await reply.edit(
            f"╭──⚡ 𝗨𝗣𝗟𝗢𝗔𝗗𝗜𝗡𝗚 ⚡──╮\n"
            f"┣ [{bar}] {perc}\n"
            f"┣ 🚀 Speed   : {sp}\n"
            f"┣ 📂 Done    : {cur} / {tot}\n"
            f"┣ ⏳ ETA     : {eta}\n"
            f"╰── 𖤓 {CREDIT} 𖤓 ──╯"
        )
    except FloodWait as e:
        await asyncio.sleep(e.value if hasattr(e, 'value') else e.x)
    except Exception:
        pass

