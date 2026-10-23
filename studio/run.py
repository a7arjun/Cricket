"""Drive/Sheets handoff with explicit opt-in for public publishing."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, os, re, subprocess, sys, uuid, zipfile
import urllib.request, urllib.parse

def request(url, token=None, data=None, method='GET', content_type=None):
    headers={}
    if token:headers['Authorization']='Bearer '+token
    if content_type:headers['Content-Type']=content_type
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=180) as response:return response.read()

def refresh(prefix):
    names=[prefix+'CLIENT_ID',prefix+'CLIENT_SECRET',prefix+'REFRESH_TOKEN']
    missing=[name for name in names if not os.environ.get(name)]
    if missing:raise RuntimeError('Missing configuration: '+', '.join(missing))
    payload=dict(zip(['client_id','client_secret','refresh_token'],[os.environ[x] for x in names]))
    payload['grant_type']='refresh_token'
    raw=request('https://oauth2.googleapis.com/token',data=urllib.parse.urlencode(payload).encode(),method='POST',content_type='application/x-www-form-urlencoded')
    return json.loads(raw)['access_token']

def valid_drive_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,150}',value):raise ValueError('Invalid Drive file ID')
    return value

def drive_bytes(file_id,token):
    return request('https://www.googleapis.com/drive/v3/files/'+valid_drive_id(file_id)+'?alt=media',token)

def validate_job(job):
    if job.get('schema_version') not in (1,2) or not re.fullmatch(r'CK\d{3,6}',job.get('episode_id','')):raise ValueError('Invalid episode schema or ID')
    if job['schema_version']==1 and job['episode_id']!='CK001':raise ValueError('Legacy artwork belongs to CK001 only')
    if job.get('privacy')!='private':raise ValueError('Only private uploads are allowed')
    if job.get('story_mode') not in ('scripted_what_if','empirical_what_if'):raise ValueError('Expected a disclosed what-if story')
    results=job.get('results',[])
    if not 1<=len(results)<=6 or any(r!='W' and (type(r) is not int or r not in (0,1,2,3,4,6)) for r in results):raise ValueError('Invalid ball outcomes')
    if type(job.get('target')) is not int or not 1<=job['target']<=36:raise ValueError('Invalid chase target')
    if 'W' in results[:-1] or results.count('W')>1:raise ValueError('A wicket ends the solo attempt')
    running=0
    for i,r in enumerate(results):
        running+=r if isinstance(r,int) else 0
        if running>=job['target'] and i<len(results)-1:raise ValueError('Chase must end when target is reached')
    if len(results)<6 and results[-1]!='W' and running<job['target']:raise ValueError('Incomplete chase')
    if job['schema_version']==1 and results!=[0,4,2,4,0,2]:raise ValueError('Legacy CK001 story changed')
    if not re.fullmatch(r'[a-f0-9]{64}',job.get('bundle_sha256','')):raise ValueError('Missing bundle SHA-256')
    valid_drive_id(job.get('bundle_drive_id'))
    if job.get('preview_drive_id'):
        valid_drive_id(job['preview_drive_id'])
        if not re.fullmatch(r'[a-f0-9]{64}',job.get('preview_sha256','')):raise ValueError('Missing preview checksum')

def unpack(data,sha,destination,job=None):
    import io
    if hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Bundle checksum mismatch')
    destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(i.file_size for i in archive.infolist())>200_000_000:raise ValueError('Bundle exceeds size limit')
        for info in archive.infolist():
            path=PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename:raise ValueError('Unsafe archive member')
            if info.filename!='asset_checksums.json' and not info.filename.startswith('assets/'):raise ValueError('Unexpected bundle member')
        archive.extractall(destination)
    checks=json.loads((destination/'asset_checksums.json').read_text())
    for name,digest in checks.items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or not name.startswith('assets/'):raise ValueError('Unsafe checksum member')
        if hashlib.sha256((destination/name).read_bytes()).hexdigest()!=digest:raise ValueError('Asset checksum mismatch: '+name)
    actual={str(p.relative_to(destination)) for p in (destination/'assets').rglob('*') if p.is_file()}
    if actual!=set(checks):raise ValueError('Asset inventory mismatch')
    scenes=json.loads((destination/'assets/scenes.json').read_text())
    simulation=json.loads((destination/'assets/simulation.json').read_text())
    if simulation['mode'] not in ('scripted_what_if','empirical_what_if'):raise ValueError('Bundle story mismatch')
    if job and simulation['mode']!=job['story_mode']:raise ValueError('Job and model mode disagree')
    if job and any(simulation.get(k)!=job.get(k) for k in ('episode_id','target','results')):raise ValueError('Job and bundle disagree')
    if job and job['schema_version']==2:
        config=json.loads((destination/'assets/template.json').read_text())
        for k in ('batter','bowler'):
            if config[k]['name']!=job[k]:raise ValueError('Job and artwork player disagree')
    if [s['result'] for s in scenes if s['kind']=='ball']!=simulation['results']:raise ValueError('Scene results mismatch')
    (destination/'output').mkdir(exist_ok=True)

def find_episode(rows,episode_id):
    if not rows:return None
    headers=rows[0]
    matches=[(i+2,dict(zip(headers,row))) for i,row in enumerate(rows[1:]) if row and row[0]==episode_id]
    if len(matches)!=1:raise ValueError('Expected exactly one queue row for '+episode_id)
    return matches[0]

def sheet_values(sheet_id,token):
    rng=urllib.parse.quote("'Queue'!A1:N101",safe='')
    data=json.loads(request(f'https://sheets.googleapis.com/v4/spreadsheets/{valid_drive_id(sheet_id)}/values/{rng}',token))
    return data.get('values',[])

def set_cell(sheet_id,row,col,value,token):
    rng=urllib.parse.quote(f"'Queue'!{col}{row}",safe='')
    request(f'https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{rng}?valueInputOption=RAW',token,
        json.dumps({'values':[[value]]}).encode(),'PUT','application/json')

def upload_metadata(job, privacy='private'):
    if privacy not in ('private','public'):raise ValueError('Unsupported upload privacy')
    if privacy=='public' and os.environ.get('CRICKET_PUBLIC_ENABLED')!='true':
        raise RuntimeError('Public publishing is disabled')
    return {'snippet':{'title':job['title'][:100],'description':job['description'],'categoryId':'17','defaultLanguage':'hi'},
            'status':{'privacyStatus':privacy,'selfDeclaredMadeForKids':False,'containsSyntheticMedia':True}}

def private_metadata(job):
    return upload_metadata(job)

def upload_private(job,video,token,receipt_path,privacy='private'):
    metadata=upload_metadata(job,privacy)
    expected=os.environ.get('CRICKET_YOUTUBE_CHANNEL_ID','')
    if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}',expected):raise RuntimeError('Configure the verified cricket YouTube channel ID first')
    if receipt_path.exists():raise RuntimeError('Upload receipt exists; refusing a duplicate upload')
    channels=json.loads(request('https://www.googleapis.com/youtube/v3/channels?part=id,snippet&mine=true',token))
    if expected not in [item['id'] for item in channels.get('items',[])]:raise RuntimeError('Authenticated channel does not match the cricket channel')
    boundary='cricket_'+uuid.uuid4().hex
    media=video.read_bytes()
    body=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()+json.dumps(metadata).encode()+
        f'\r\n--{boundary}\r\nContent-Type: video/mp4\r\n\r\n'.encode()+media+f'\r\n--{boundary}--\r\n'.encode())
    # Never automatically retry this POST after an uncertain network response.
    raw=request('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=multipart&part=snippet,status&notifySubscribers=false',token,
        body,'POST','multipart/related; boundary='+boundary)
    item=json.loads(raw)
    receipt={'episode_id':job['episode_id'],'video_id':item['id'],'channel_id':expected,'privacy':item.get('status',{}).get('privacyStatus'),
        'sha256':hashlib.sha256(media).hexdigest(),'url':'https://www.youtube.com/watch?v='+item['id']}
    receipt_path.write_text(json.dumps(receipt,indent=2))
    if receipt['privacy']!=privacy:raise RuntimeError('YouTube did not confirm requested status; inspect the saved receipt')
    return receipt

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sheet-id')
    parser.add_argument('--episode-id',default='CK001')
    parser.add_argument('--local-job',type=Path)
    parser.add_argument('--local-bundle',type=Path)
    parser.add_argument('--work-dir',type=Path,default=Path('work/CK001'))
    parser.add_argument('--validate-only',action='store_true')
    uploads=parser.add_mutually_exclusive_group()
    uploads.add_argument('--upload-private',action='store_true')
    uploads.add_argument('--publish-public',action='store_true')
    args=parser.parse_args()
    privacy='public' if args.publish_public else 'private'
    uploading=args.upload_private or args.publish_public
    if args.publish_public:upload_metadata({'title':'','description':''},privacy)
    token=None;row=None;receipt_path=args.work_dir/'upload_receipt.json'
    if args.local_job:
        if uploading:raise RuntimeError('Local validation does not upload; use the verified Sheet handoff')
        job=json.loads(args.local_job.read_text());data=args.local_bundle.read_bytes()
    else:
        if not args.sheet_id:raise ValueError('A queue spreadsheet ID is required')
        token=refresh('CRICKET_DRIVE_')
        row,record=find_episode(sheet_values(args.sheet_id,token),args.episode_id)
        if record.get('YouTube URL'):print('Upload already recorded; nothing to do.');return
        if record.get('Status') not in ['ASSETS_READY','PREVIEW_READY']:raise ValueError('Queue row is not ready; inspect status before retrying')
        job=json.loads(drive_bytes(record['Job Drive ID'],token))
        data=drive_bytes(job['bundle_drive_id'],token)
    validate_job(job)
    if not args.local_job and job['episode_id']!=args.episode_id:raise ValueError('Queue job episode mismatch')
    unpack(data,job['bundle_sha256'],args.work_dir,job)
    if args.validate_only:print('Validated job, checksums and six-ball score.');return
    video=args.work_dir/'output'/('CK001_Kohli_vs_Bumrah_Private_Preview.mp4' if job['schema_version']==1 else job['episode_id']+'_Private_Preview.mp4')
    env=os.environ.copy();env['CRICKET_EPISODE_DIR']=str(args.work_dir.resolve())
    try:
        if token and job.get('preview_drive_id'):
            media=drive_bytes(job['preview_drive_id'],token)
            if hashlib.sha256(media).hexdigest()!=job['preview_sha256']:raise ValueError('Preview checksum mismatch')
            video.write_bytes(media)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(video)]))
            if not 0<float(probe['format']['duration'])<=60.2:raise ValueError('Preview duration is invalid')
        else:
            if token:set_cell(args.sheet_id,row,'C','RENDERING',token)
            subprocess.run([sys.executable,str(Path(__file__).with_name('render.py'))],check=True,env=env)
    except Exception:
        if token:set_cell(args.sheet_id,row,'C','RENDER_FAILED',token)
        raise
    if token:
        set_cell(args.sheet_id,row,'C','PREVIEW_READY',token)
        run_url=os.environ.get('GITHUB_SERVER_URL','https://github.com')+'/'+os.environ.get('GITHUB_REPOSITORY','')+'/actions/runs/'+os.environ.get('GITHUB_RUN_ID','')
        if os.environ.get('GITHUB_RUN_ID'):set_cell(args.sheet_id,row,'M',run_url,token)
    if uploading:
        yt=refresh('CRICKET_YOUTUBE_')
        # Fail closed before any upload if the verified channel setting is absent.
        expected=os.environ.get('CRICKET_YOUTUBE_CHANNEL_ID','')
        if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}',expected):raise RuntimeError('Missing verified cricket channel ID')
        set_cell(args.sheet_id,row,'C','UPLOADING_PRIVATE' if privacy=='private' else 'UPLOADING_PUBLIC',token)
        try:receipt=upload_private(job,video,yt,receipt_path,privacy)
        except Exception:
            set_cell(args.sheet_id,row,'C','UPLOAD_NEEDS_REVIEW',token)
            raise
        set_cell(args.sheet_id,row,'E',receipt['url'],token)
        set_cell(args.sheet_id,row,'C','PRIVATE_UPLOADED' if privacy=='private' else 'PUBLISHED',token)
    print('Finished '+job['episode_id']+'; privacy mode: '+privacy)

if __name__=='__main__':main()
