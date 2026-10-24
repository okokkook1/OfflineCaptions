"""Bounded streaming segmentation. No network, microphone or disk recording."""
from dataclasses import dataclass
from collections import deque
import re
import numpy as np

RATE = 16000

@dataclass
class Job:
    id: int
    start: float
    end: float
    audio: np.ndarray
    final: bool

class Segmenter:
    def __init__(self, emit, max_seconds=8.0, pause_seconds=0.64, partial_seconds=2.0):
        self.emit = emit
        self.max_seconds, self.pause_seconds, self.partial_seconds = max_seconds, pause_seconds, partial_seconds
        self.next_id = 0
        self.reset()

    def reset(self):
        self.blocks = []
        self.start = self.end = self.last_voice = self.last_partial = None
        self.preroll = None

    def push(self, audio, start, speech):
        # A device outage, pause or dropped transport packet is a real discontinuity.
        if self.end is not None and start - self.end > 0.5:
            self.finish()
            self.preroll = None
        end = start + len(audio) / RATE
        if not self.blocks:
            if not speech:
                self.preroll = (audio.copy(), start)
                self.end = end
                return
            self.next_id += 1
            self.start = start
            if self.preroll is not None:
                old, stamp = self.preroll
                if abs(start - (stamp + len(old) / RATE)) < 0.1:
                    self.blocks.append(old)
                    self.start = stamp
            self.preroll = None
            self.last_partial = self.start
        self.blocks.append(audio.copy())
        self.end = end
        if speech:
            self.last_voice = end
        duration = end - self.start
        if duration >= self.max_seconds or end - self.last_voice >= self.pause_seconds:
            self.finish()
        elif end - self.last_partial >= self.partial_seconds:
            self.emit(Job(self.next_id, self.start, end, np.concatenate(self.blocks), False))
            self.last_partial = end

    def finish(self):
        if self.blocks and self.last_voice is not None:
            self.emit(Job(self.next_id, self.start, self.last_voice, np.concatenate(self.blocks), True))
        self.reset()

class JobBuffer:
    """Caller owns synchronization. Finals supersede drafts; queue never grows unbounded."""
    def __init__(self, limit=3):
        self.limit = limit
        self.items = deque()

    def add(self, job):
        self.items = deque(x for x in self.items if x.id != job.id)
        # Drafts must not evict completed speech waiting for recognition.
        if not job.final and len(self.items) >= self.limit:
            return []
        dropped = []
        while len(self.items) >= self.limit:
            draft = next((x for x in self.items if not x.final), None)
            old = draft if draft is not None else self.items[0]
            self.items = deque(x for x in self.items if x is not old)
            if old.final:
                dropped.append(old.id)
        self.items.append(job)
        return dropped

    def pop(self):
        # Serve chronological audio, not the latest draft first.
        return self.items.popleft() if self.items else None

EN_SPAN = re.compile(r"[A-Za-z][A-Za-z0-9'’ ,.;:!?()\-/]*")
HAN = re.compile(r"[\u3400-\u9fff]")

def translate_text(text, language, translate, convert):
    text = text.strip()
    if not text:
        return ""
    if not HAN.search(text):
        return convert(translate(text)) if re.search(r"[A-Za-z]", text) else convert(text)
    # Preserve the Chinese context. Short acronyms and product identifiers remain legible.
    def span(m):
        s = m.group().strip()
        if len(s) <= 5 and s.isupper():
            return m.group()
        return " " + translate(s) + " "
    return convert(EN_SPAN.sub(span, text)).strip()

def srt_time(seconds):
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"
