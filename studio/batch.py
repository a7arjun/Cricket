"""Release prepared episodes in two daily slots; never invent missing assets."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import argparse, json, os, re, subprocess, sys

TZ = ZoneInfo('Asia/Kolkata')
SLOTS = (time(10), time(22))

def plan(matchups, start, privacy='private'):
    if privacy not in ('private','public'):raise ValueError('Unsupported privacy')
    if not 1 <= len(matchups) <= 20:
        raise ValueError('Supply 1–20 matchups')
    result = []
    seen = set()
    for i, item in enumerate(matchups):
        eid = item['episode_id']
        if not re.fullmatch(r'CK\d{3,6}', eid) or eid in seen:
            raise ValueError('Episode IDs must be unique CK numbers')
        seen.add(eid)
        if not item.get('batter') or not item.get('bowler') or item['batter'] == item['bowler']:
            raise ValueError('Each episode needs two distinct players')
        at = datetime.combine(start + timedelta(days=i//2), SLOTS[i%2], TZ)
        result.append({**item, 'release_at': at.isoformat(), 'privacy': privacy})
    return result

def due(episodes, now):
    """No catch-up flood: process only today's elapsed slots, at most two."""
    ids = [e['episode_id'] for e in episodes]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate episode IDs')
    selected = []
    for e in episodes:
        at = datetime.fromisoformat(e['release_at'])
        if at.tzinfo is None or e.get('privacy') not in ('private','public'):
            raise ValueError('Expected timezone-aware release slots')
        if at.astimezone(TZ).date() == now.astimezone(TZ).date() and at <= now:
            selected.append(e)
    if len(selected) > 2:
        raise ValueError('More than two releases assigned to one day')
    return selected

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, default=Path('batch.json'))
    p.add_argument('--sheet-id', default=os.environ.get('CRICKET_QUEUE_ID'))
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--execute-private', action='store_true')
    modes.add_argument('--execute-public', action='store_true')
    args = p.parse_args()
    data = json.loads(args.manifest.read_text())
    if data.get('timezone') != 'Asia/Kolkata':
        raise ValueError('Unexpected batch timezone')
    episodes = due(data['episodes'], datetime.now(TZ))
    if not (args.execute_private or args.execute_public):
        print(json.dumps({'due': episodes, 'executed': False}, indent=2)); return
    if not args.sheet_id:
        raise ValueError('Cricket queue ID is required')
    privacy='public' if args.execute_public else 'private'
    if privacy=='public' and os.environ.get('CRICKET_PUBLIC_ENABLED')!='true':
        raise RuntimeError('Public publishing is disabled')
    if any(e['privacy']!=privacy for e in episodes):raise ValueError('Manifest privacy and execution mode disagree')
    for episode in episodes:
        # run.py reads the durable Sheet status and refuses uncertain uploads.
        subprocess.run([sys.executable, str(Path(__file__).with_name('run.py')),
            '--sheet-id', args.sheet_id, '--episode-id', episode['episode_id'],
            '--work-dir', 'work/'+episode['episode_id'],
            '--publish-public' if privacy=='public' else '--upload-private'], check=True)

if __name__ == '__main__': main()
