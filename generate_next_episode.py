#!/usr/bin/env python3
"""Durable one-episode worker for Eat The Bible 120.

The `start` command launches one detached worker and returns immediately.
The worker itself owns the sequence lock and runs outside Hermes' cron timeout.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/opt/data/Eat The Bible 120')
PLAN_PATH = ROOT / 'reading-plan.json'
STATE_PATH = ROOT / 'sequence-state.json'
LOCK_PATH = ROOT / '.generation.lock'
LOG_PATH = ROOT / 'generation.log'
API_BASE = 'https://bible-api.com/'
LOCALAI_URL = 'http://100.92.91.30:33445/tts'
TOTAL_DAYS = 120

BOOK_NAMES = {
    'Gen':'Genesis','Exod':'Exodus','Lev':'Leviticus','Num':'Numbers','Deut':'Deuteronomy',
    'Josh':'Joshua','Judg':'Judges','Ruth':'Ruth','1Sam':'1 Samuel','2Sam':'2 Samuel',
    '1Kgs':'1 Kings','2Kgs':'2 Kings','1Chr':'1 Chronicles','2Chr':'2 Chronicles',
    'Ezra':'Ezra','Neh':'Nehemiah','Esth':'Esther','Job':'Job','Ps':'Psalms',
    'Prov':'Proverbs','Pro':'Proverbs','Eccl':'Ecclesiastes','Song':'Song of Solomon',
    'Isa':'Isaiah','Jer':'Jeremiah','Lam':'Lamentations','Ezek':'Ezekiel','Dan':'Daniel',
    'Hos':'Hosea','Joel':'Joel','Amos':'Amos','Obad':'Obadiah','Jonah':'Jonah',
    'Mic':'Micah','Nah':'Nahum','Hab':'Habakkuk','Zeph':'Zephaniah','Hag':'Haggai',
    'Zech':'Zechariah','Mal':'Malachi','Matt':'Matthew','Mark':'Mark','Luk':'Luke',
    'John':'John','Acts':'Acts','Rom':'Romans','1Cor':'1 Corinthians','2Cor':'2 Corinthians',
    'Gal':'Galatians','Eph':'Ephesians','Phil':'Philippians','Col':'Colossians',
    '1Thess':'1 Thessalonians','2Thess':'2 Thessalonians','1Tim':'1 Timothy','2Tim':'2 Timothy',
    'Titus':'Titus','Phlm':'Philemon','Heb':'Hebrews','Jas':'James','1Pet':'1 Peter',
    '2Pet':'2 Peter','1John':'1 John','2John':'2 John','3John':'3 John','Jude':'Jude','Rev':'Revelation'
}
OT = set('Gen Exod Lev Num Deut Josh Judg Ruth 1Sam 2Sam 1Kgs 2Kgs 1Chr 2Chr Ezra Neh Esth Job Eccl Song Isa Jer Lam Ezek Dan Hos Joel Amos Obad Jonah Mic Nah Hab Zeph Hag Zech Mal'.split())
NT = set('Matt Mark Luk John Acts Rom 1Cor 2Cor Gal Eph Phil Col 1Thess 2Thess 1Tim 2Tim Titus Phlm Heb Jas 1Pet 2Pet 1John 2John 3John Jude Rev'.split())
ALIASES = {
    'Ex':'Exod','Ecc':'Eccl','Sos':'Song','Est':'Esth','Eze':'Ezek','Ezr':'Ezra','Amo':'Amos',
    'Jdg':'Judg','Joe':'Joel','Jon':'Jonah','Oba':'Obad','Zec':'Zech','Zep':'Zeph','Rut':'Ruth',
    'Mk':'Mark','Mat':'Matt','Jam':'Jas','Tit':'Titus','1 Sa':'1Sam','2 Sa':'2Sam',
    '1 Chr':'1Chr','2 Chr':'2Chr','1 Kgs':'1Kgs','2 Kgs':'2Kgs','1 Co':'1Cor','2 Co':'2Cor','1 Th':'1Thess','2 Th':'2Thess',
    '1 Ti':'1Tim','2 Ti':'2Tim','1 Pe':'1Pet','2 Pe':'2Pet','1 Jn':'1John','2 Jn':'2John','3 Jn':'3John',
}
BOOK_PREFIXES = sorted(set(BOOK_NAMES) | set(ALIASES), key=len, reverse=True)


def log(message: str) -> None:
    line = f'[{datetime.now(timezone.utc).isoformat()}] {message}\n'
    ROOT.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(line)
    # The detached launcher redirects stdout to this same file. Writing here
    # and also printing would duplicate every line in generation.log.


def js_round(value: float) -> int:
    return math.floor(value + 0.5)


def parse_passage(value: str) -> list[tuple[str, int]]:
    value = value.strip().rstrip(',')
    book = next((b for b in BOOK_PREFIXES if value == b or value.startswith(b + ' ')), None)
    if book is None:
        raise RuntimeError(f'Cannot parse passage: {value}')
    canonical = ALIASES.get(book, book)
    chapter_text = value[len(book):].strip()
    if not chapter_text:
        chapter_text = '1'
    result = []
    for item in chapter_text.split(','):
        item = item.strip()
        if '-' in item:
            first, last = item.split('-', 1)
            result.extend((canonical, n) for n in range(int(first), int(last) + 1))
        else:
            result.append((canonical, int(item)))
    return result


def load_plan() -> list[dict]:
    data = json.loads(PLAN_PATH.read_text(encoding='utf-8'))
    if len(data) != TOTAL_DAYS:
        raise RuntimeError(f'Expected {TOTAL_DAYS} plan entries, found {len(data)}')
    return data


def rendered_days() -> list[list[tuple[str, int]]]:
    raw = load_plan()
    ot_all: list[tuple[str, int]] = []
    nt_all: list[tuple[str, int]] = []
    ps_pro: list[list[tuple[str, int]]] = []
    for day in raw:
        extras: list[tuple[str, int]] = []
        for passage in day['passages']:
            parsed = parse_passage(passage)
            book = parsed[0][0]
            if book in OT:
                ot_all.extend(parsed)
            elif book in NT:
                nt_all.extend(parsed)
            elif book in {'Ps', 'Pro', 'Prov'}:
                extras.extend(parsed)
            else:
                raise RuntimeError(f'Unknown book abbreviation: {book}')
        ps_pro.append(extras)

    days: list[list[tuple[str, int]]] = []
    for index in range(TOTAL_DAYS):
        # Day 1 is already approved as Genesis 1-8. Its boundary is retained
        # explicitly, then the remaining OT stream is distributed evenly over
        # Days 2-120 with non-overlapping ceiling boundaries.
        def ot_boundary(day_index: int) -> int:
            if day_index == 0:
                return 0
            if day_index == 1:
                return 8
            return 8 + math.ceil((day_index - 1) * (len(ot_all) - 8) / (TOTAL_DAYS - 1))
        ot_start = ot_boundary(index)
        ot_end = ot_boundary(index + 1)
        nt_start = js_round(index * len(nt_all) / TOTAL_DAYS)
        nt_end = js_round((index + 1) * len(nt_all) / TOTAL_DAYS)
        days.append(ot_all[ot_start:ot_end] + nt_all[nt_start:nt_end] + ps_pro[index])
    return days


def collapse(chapters: list[tuple[str, int]]) -> list[tuple[str, int, int]]:
    result: list[tuple[str, int, int]] = []
    for book, chapter in chapters:
        if result and result[-1][0] == book and result[-1][2] + 1 == chapter:
            old_book, first, _ = result[-1]
            result[-1] = (old_book, first, chapter)
        else:
            result.append((book, chapter, chapter))
    return result


def spoken_passage_list(chapters: list[tuple[str, int]]) -> str:
    pieces = []
    for book, first, last in collapse(chapters):
        name = BOOK_NAMES[book]
        if first == last:
            pieces.append(f'{name} chapter {first}')
        else:
            pieces.append(f'{name} chapters {first} through {last}')
    if len(pieces) == 1:
        return pieces[0]
    return ', '.join(pieces[:-1]) + ', and ' + pieces[-1]


def fetch_chapter(book: str, chapter: int) -> list[str]:
    # bible-api.com accepts full book names more consistently than compact
    # plan abbreviations (notably `Phlm`, which returns 404). Keep the plan's
    # canonical abbreviation internally, but use the spoken/full name on the
    # wire for every request.
    api_book = BOOK_NAMES.get(book, book)
    ref = f'{api_book} {chapter}'
    url = API_BASE + urllib.parse.quote(ref) + '?translation=web'
    request = urllib.request.Request(
        url,
        headers={'User-Agent': 'Eat-The-Bible-120/1.0 (+local scheduled podcast worker)'},
        method='GET',
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read())
            verses = [str(v.get('text', '')).strip() for v in data.get('verses', [])]
            verses = [v for v in verses if v]
            if not verses:
                raise RuntimeError(f'No verses returned for {ref}')
            return verses
        except urllib.error.HTTPError as exc:
            # Bad references are permanent; rate limiting and server errors
            # are transient and deserve a longer backoff.
            if exc.code == 404 or attempt == 4:
                raise
            retry_after = exc.headers.get('Retry-After')
            try:
                delay = max(5, int(retry_after)) if retry_after else 15 * (2 ** attempt)
            except ValueError:
                delay = 15 * (2 ** attempt)
            time.sleep(delay)
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            if attempt == 4:
                raise
            time.sleep(5 * (2 ** attempt))
    raise AssertionError


def render_text(chapters: list[tuple[str, int]]) -> str:
    parts = [f"Today's Scripture reading is {spoken_passage_list(chapters)}."]
    for index, (book, chapter) in enumerate(chapters, 1):
        log(f'Fetching {book} {chapter} ({index}/{len(chapters)})')
        parts.append(f'{BOOK_NAMES[book]}, chapter {chapter}.')
        parts.extend(fetch_chapter(book, chapter))
    return '\n\n'.join(parts) + '\n'


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def atomic_write(path: Path, value: str) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def worker() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log('Another generation is already running; exiting safely.')
            return 0
        state = json.loads(STATE_PATH.read_text(encoding='utf-8'))
        day = int(state['next_day'])
        if day > TOTAL_DAYS:
            log('Sequence is complete; no work needed.')
            return 0
        mp3 = ROOT / f'day-{day:03d}.mp3'
        narration_path = ROOT / f'day-{day:03d}-narration.txt'
        wav = ROOT / f'.day-{day:03d}.wav'
        if mp3.exists() or narration_path.exists():
            raise RuntimeError(f'Refusing to overwrite existing day {day}: {mp3.name} or {narration_path.name} exists')

        chapters = rendered_days()[day - 1]
        if not chapters:
            raise RuntimeError(f'Day {day} has no chapters')
        log(f'Starting Day {day}: {spoken_passage_list(chapters)}')
        text = render_text(chapters)
        atomic_write(narration_path, text)
        payload = json.dumps({'input': text, 'model': 'kokoro', 'voice': 'am_michael'}).encode()
        request = urllib.request.Request(LOCALAI_URL, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        log(f'Sending Day {day} ({len(text)} characters) to LocalAI Kokoro')
        with urllib.request.urlopen(request, timeout=3600) as response:
            audio = response.read()
            content_type = response.headers.get('Content-Type', '')
            if response.status != 200 or 'audio' not in content_type.lower():
                raise RuntimeError(f'Unexpected TTS response: HTTP {response.status}, {content_type}')
        if len(audio) < 10000:
            raise RuntimeError(f'TTS response is unexpectedly small: {len(audio)} bytes')
        wav.write_bytes(audio)
        subprocess.run(['ffmpeg', '-y', '-i', str(wav), '-codec:a', 'libmp3lame', '-qscale:a', '3', str(mp3)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        duration = ffprobe_duration(mp3)
        if duration < 10 or mp3.stat().st_size < 10000:
            raise RuntimeError(f'Invalid MP3 validation: {duration}s, {mp3.stat().st_size} bytes')
        wav.unlink(missing_ok=True)
        state['current_day'] = day
        state['next_day'] = day + 1
        state['last_completed_date'] = datetime.now(timezone.utc).date().isoformat()
        state['last_duration_seconds'] = round(duration, 3)
        state['last_passages'] = spoken_passage_list(chapters)
        atomic_write(STATE_PATH, json.dumps(state, indent=2) + '\n')
        log(f'Completed Day {day}: {mp3} ({duration:.1f}s)')
        return 0


def start() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    log_file = LOG_PATH.open('a', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker'], stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    log_file.close()
    print(json.dumps({'started': True, 'pid': proc.pid, 'log': str(LOG_PATH)}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['start', 'worker', 'dry-run'])
    parser.add_argument('--day', type=int)
    args = parser.parse_args()
    if args.command == 'start':
        return start()
    if args.command == 'dry-run':
        days = rendered_days()
        day = args.day or int(json.loads(STATE_PATH.read_text())['next_day'])
        chapters = days[day - 1]
        print(json.dumps({'day': day, 'chapters': len(chapters), 'passages': spoken_passage_list(chapters), 'files': [f'day-{day:03d}.mp3', f'day-{day:03d}-narration.txt']}, indent=2))
        return 0
    return worker()

if __name__ == '__main__':
    raise SystemExit(main())
