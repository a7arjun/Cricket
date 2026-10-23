from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
import numpy as np
import json, math, subprocess, wave, sys, zipfile, textwrap, os

R=Path(os.environ.get('CRICKET_EPISODE_DIR',Path(__file__).resolve().parent)); A=R/'assets'; O=R/'output'
W,H,FPS=720,1280,24
SCENES=json.loads((A/'scenes.json').read_text())
SUMMARY=json.loads((A/'matchup_summary.json').read_text())
SIM=json.loads((A/'simulation.json').read_text())
TOTAL=sum(s['duration'] for s in SCENES)
DEFAULT_CONFIG={
 'batter':{'name':'Virat Kohli','short':'KOHLI','first':'VIRAT','hero':'kohli_hero.png'},
 'bowler':{'name':'Jasprit Bumrah','short':'BUMRAH','first':'JASPRIT','hero':'bumrah_hero.png'},
 'art':{'release':'bumrah_release.png','drive':'kohli_drive.png','defense':'kohli_defense.png','pull':'kohli_pull.png','duck':'kohli_duck.png'},
 'format':'IPL','source':'Cricsheet / ODC-BY 1.0', 'snapshot':'23 Oct 2026',
 'facts':['Kohli: 159 IPL runs vs Bumrah','Bumrah: 5 IPL dismissals of Kohli']}
CONFIG=json.loads((A/'template.json').read_text()) if (A/'template.json').exists() else DEFAULT_CONFIG
BAT=CONFIG['batter']; BOWL=CONFIG['bowler']; TARGET=SIM['target']

FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
INK='#101b26'; CREAM='#f0f0e8'; MUTED='#9ba9b4'; LIME='#d9ff63'; BLUE='#6ed7ff'
RED='#ff866e'; DARK='#101c28'
FONTS={}
def font(n,b=False):
    k=(n,b)
    if k not in FONTS:FONTS[k]=ImageFont.truetype(BOLD if b else FONT,n)
    return FONTS[k]
def tx(d,xy,txt,n=30,c=CREAM,b=False):d.text(xy,txt,font=font(n,b),fill=c)
def center(d,y,txt,n=30,c=CREAM,b=False,x=360):
    bb=d.textbbox((0,0),txt,font=font(n,b));tx(d,(x-(bb[2]-bb[0])/2,y),txt,n,c,b)
def rr(d,box,c,r=18,outline=None,width=1):d.rounded_rectangle(box,radius=r,fill=c,outline=outline,width=width)
def ease(v):v=max(0,min(1,v));return 1-(1-v)**3
def wrap(d,text,n,maxw):
    lines=['']
    for word in text.split():
        a=(lines[-1]+' '+word).strip()
        if d.textlength(a,font=font(n,True))>maxw and lines[-1]:lines.append(word)
        else:lines[-1]=a
    return lines

yy=np.linspace(0,1,H)[:,None,None];top=np.array([12,24,35])[None,None,:];bot=np.array([6,13,21])[None,None,:]
bg=np.broadcast_to(top*(1-yy)+bot*yy,(H,W,3)).astype(np.uint8).copy()
BG=Image.fromarray(bg)
g=ImageDraw.Draw(BG)
for x in range(0,W,60):g.line((x,0,x,H),fill='#152635')
for y in range(0,H,60):g.line((0,y,W,y),fill='#152635')
g.polygon([(555,0),(720,0),(720,480),(320,880),(220,780),(555,445)],fill='#142d3c')

def load_art(spec):
    if isinstance(spec,str):return Image.open(A/spec).convert('RGB')
    im=Image.open(A/spec['file']).convert('RGB')
    x0,y0,x1,y1=spec['region']
    return im.crop((round(x0*im.width),round(y0*im.height),round(x1*im.width),round(y1*im.height)))
BUM=load_art(BOWL['hero'])
KOH=load_art(BAT['hero'])
ART={k:load_art(v) for k,v in CONFIG['art'].items()}
def score_of(results):return sum(r for r in results if isinstance(r,int))
def is_wicket(results):return 'W' in results

def photo(im,src,box,progress,centering=(.5,.3)):
    x,y,w,h=box;zoom=1.02+.065*math.sin(progress*math.pi/2)
    sw,sh=int(w*zoom),int(h*zoom)
    crop=ImageOps.fit(src,(sw,sh),Image.Resampling.LANCZOS,centering=centering)
    crop=crop.crop(((sw-w)//2,(sh-h)//2,(sw+w)//2,(sh+h)//2))
    mask=Image.new('L',(w,h),0);md=ImageDraw.Draw(mask);md.rounded_rectangle((0,0,w,h),radius=20,fill=255)
    im.paste(crop,(x,y),mask)
    # Layout shade, preserving the source photograph itself.
    shade=np.zeros((h,w,4),dtype=np.uint8);shade[:,:,3]=np.linspace(0,195,h).astype(np.uint8)[:,None]
    layer=Image.fromarray(shade);im.paste(layer,(x,y),layer)

def header(im,s,t):
    d=ImageDraw.Draw(im)
    tx(d,(30,28),'CRICKET LAB',22,LIME,True)
    tx(d,(30,57),SIM['episode_id']+' / ONE-OVER CHALLENGE',14,MUTED)
    tx(d,(30,100),BOWL['short'],42,CREAM,True)
    tx(d,(327,119),'vs',26,MUTED,True)
    tx(d,(391,100),BAT['short'],42,BLUE,True)
    d.line((30,182,690,182),fill='#3a4d5a',width=2)
    lab=f'6 BALLS / TARGET {TARGET}'
    tx(d,(30,194),lab,18,LIME,True)

def player_panels(im,s,t):
    p=t/max(.1,s['duration']);d=ImageDraw.Draw(im)
    if s['kind']=='ball':
        contact=s.get('contact',s['duration']*.49)
        batting=t>=contact-.12
        shot=s.get('art_key') or {'DUCK':'duck','COVER DRIVE':'drive','FIND THE GAP':'defense','ADVANCE AND DRIVE':'drive','DIG OUT':'defense','CONTROLLED PULL':'pull','LOFTED DRIVE':'drive','EDGE':'drive','SWEEP':'pull'}[s['shot']]
        key=shot if batting else 'release'
        label=(BAT['short']+' / '+s['shot']) if batting else BOWL['short']+' / DELIVERY'
        color=BLUE if batting else LIME
        # Consistent full-body action card. Keep limbs and bat inside frame.
        rr(d,(30,237,690,534),'#101f30',r=20,outline='#3b5466',width=2)
        src=ART[key]
        fitted=ImageOps.contain(src,(450,294),Image.Resampling.LANCZOS)
        x=227+(450-fitted.width)//2;y=239+(294-fitted.height)//2
        im.paste(fitted,(x,y))
        d=ImageDraw.Draw(im)
        # An opponent identity chip stays in exactly the same place.
        photo(im,BUM if batting else KOH,(46,283,141,173),p,(.5,.2))
        d=ImageDraw.Draw(im)
        tx(d,(47,465),BOWL['short'] if batting else BAT['short'],22,CREAM,True)
        tx(d,(47,499),'AI ILLUSTRATION',11,MUTED,True)
        rr(d,(211,246,673,280),'#092032',r=10)
        tx(d,(225,252),label,18,color,True)
        # Visual rhythm: a light pulse marks the switch from release to shot.
        if abs(t-contact)<.13:d.rectangle((210,283,682,529),outline=color,width=3)
        return
    photo(im,BUM,(30,237,316,348),p,(.5,.25))
    photo(im,KOH,(364,237,326,348),p,(.5,0))
    d=ImageDraw.Draw(im)
    tx(d,(48,476),BOWL['first'],18,CREAM,True);tx(d,(48,499),BOWL['short'],27,CREAM,True)
    tx(d,(384,476),BAT['first'],18,BLUE,True);tx(d,(384,499),BAT['short'],27,CREAM,True)
    for x,col in [(30,LIME),(364,BLUE)]:d.line((x+15,570,x+299,570),fill=col,width=4)

def caption(im,s,t):
    if s['kind']=='credits':return
    bs=s.get('boundaries',[]);idx=0
    for i,b in enumerate(bs):
        if t>=b['offset']/1e7:idx=i
    caps=s.get('caps',[])
    if not caps:return
    text=caps[min(idx,len(caps)-1)]
    d=ImageDraw.Draw(im);n=30
    lines=wrap(d,text,n,618)
    if len(lines)>2:n=26;lines=wrap(d,text,n,618)
    y=540 if s['kind'] in ['intro','stats','end'] else 546
    h=56 if len(lines)==1 else 92
    rr(d,(30,y,690,y+h),'#07121f',r=14,outline='#304857')
    for j,line in enumerate(lines):center(d,y+12+j*36,line,n,LIME if text.isupper() else CREAM,True)

def ball_dot(d,x,y,r=8):
    for rad,col in [(r+9,'#4b4930'),(r+4,'#928d42'),(r,LIME)]:d.ellipse((x-rad,y-rad,x+rad,y+rad),fill=col)
    d.arc((x-r*.5,y-r*.75,x+r*.5,y+r*.75),90,270,fill='#6e6930',width=2)

def silhouette(d,x,ground,duck=False,bat=False):
    head_y=ground-(81 if duck else 122)
    d.ellipse((x-10,head_y-10,x+10,head_y+10),fill=CREAM)
    shoulder=(x,head_y+24);hip=(x-8,ground-42)
    d.line([shoulder,hip,(x-19,ground)],fill=CREAM,width=9)
    d.line([hip,(x+18,ground)],fill=CREAM,width=8)
    d.line([shoulder,(x-20,head_y+42),(x-35,head_y+55)],fill=CREAM,width=7)
    if bat:d.line((x-35,head_y+55,x-42,ground-4),fill='#e5c99a',width=11)

def pitch_position(u,delivery):
    bounce={'BOUNCER':.64,'SHORT BALL':.65,'FULL LENGTH':.9,'YORKER':.96,'HARD LENGTH':.76,'SLOWER BALL':.80,'OFF BREAK':.75,'TOP SPINNER':.78,'FLOATER':.83}[delivery]
    x=87+540*u;ground=884
    if u<=bounce:
        height=110*(1-u/bounce)+22*math.sin(math.pi*u/bounce)
    else:
        rise={'BOUNCER':103,'SHORT BALL':95,'FULL LENGTH':17,'YORKER':5,'HARD LENGTH':53,'SLOWER BALL':33,'OFF BREAK':40,'TOP SPINNER':62,'FLOATER':25}[delivery]
        q=(u-bounce)/(1-bounce);height=rise*q+10*math.sin(math.pi*q)
    return x,ground-height

def field(im,s,t,contact):
    d=ImageDraw.Draw(im);cx,cy=360,805;rx,ry=276,119
    d.ellipse((cx-rx,cy-ry,cx+rx,cy+ry),fill='#183c35',outline='#8bb4a0',width=2)
    d.ellipse((cx-rx*.55,cy-ry*.55,cx+rx*.55,cy+ry*.55),outline='#396252',width=1)
    d.rectangle((cx-8,cy-40,cx+8,cy+40),fill='#bca26e')
    result=s['result'];angle= -.6 if 'DRIVE' in s['shot'] else (2.55 if 'PULL' in s['shot'] else .65)
    maxdist=.98 if result>=4 else .72
    progress=ease((t-contact)/max(1.25,s.get('reveal',contact+1.35)-contact))
    ex=cx+math.cos(angle)*rx*maxdist;ey=cy+math.sin(angle)*ry*maxdist
    d.line((cx,cy,ex,ey),fill='#5cae92',width=2)
    if result<4 and t>=s.get('reveal',contact+1.25):
        d.ellipse((ex-10,ey-10,ex+10,ey+10),fill=BLUE)
        tx(d,(ex-25,ey+15),'FIELDER',12,CREAM,True)
    x=cx+(ex-cx)*progress;y=cy+(ey-cy)*progress
    d.line((cx,cy,x,y),fill=LIME,width=4);ball_dot(d,x,y,6)
    if result==2:
        # Two runners exchange ends twice; the scoreboard waits for the reveal.
        run_progress=max(0,min(2,(t-contact)/max(.1,s['reveal']-contact)*2))
        leg=run_progress if run_progress<=1 else 2-run_progress
        y1=cy-36+72*leg;y2=cy+36-72*leg
        d.ellipse((cx-23,y1-6,cx-11,y1+6),fill=BLUE)
        d.ellipse((cx+11,y2-6,cx+23,y2+6),fill=CREAM)
        tx(d,(50,898),'RUNNING: '+('SECOND RUN...' if run_progress>=1 else 'FIRST RUN...'),13,BLUE,True)
    if t>=s.get('reveal',contact+1.25):
        badge={1:'SINGLE',2:'TWO RUNS!',3:'THREE RUNS!',4:'FOUR!',6:'SIX!'}[result]
        rr(d,(240,846,480,908),LIME if result==4 else '#d8e6e8',r=14)
        center(d,855,badge,35,INK,True)
    center(d,657,s['shot'],21,BLUE,True)

def delivery(im,s,t):
    duration=s['duration'];d=ImageDraw.Draw(im)
    contact=s.get('contact',duration*.49)
    # The pitch view is a schematic, not measured tracking.
    rr(d,(30,650,690,934),'#0c1c26',r=20,outline='#2b4450')
    if t>contact and s['result']=='W':
        center(d,716,'CHANCE CREATED...',32,BLUE,True)
        if t>=s.get('reveal',contact+1):
            center(d,792,'WICKET!',64,RED,True)
            center(d,880,'CHALLENGE ENDS',22,CREAM,True)
        return contact
    if t>contact and isinstance(s['result'],int) and s['result']>0:
        field(im,s,t,contact);return contact
    tx(d,(48,664),s['delivery'],22,LIME,True)
    tx(d,(440,669),'ILLUSTRATIVE PATH',13,MUTED)
    d.polygon([(71,884),(644,884),(670,903),(47,903)],fill='#a28a5d')
    d.line((80,884,642,884),fill='#e0cd9e',width=3)
    for x in [100,610]:d.line((x,876,x,906),fill=CREAM,width=2)
    # Generic bowler and batter figures represent positions, not a player's captured action.
    d.ellipse((83,745,103,765),fill=BLUE)
    d.line((93,765,93,832),fill=BLUE,width=8)
    d.line((93,785,76,770,88,742),fill=BLUE,width=6)
    d.line((93,832,72,882),fill=BLUE,width=7);d.line((93,832,108,882),fill=BLUE,width=7)
    duck=s['shot']=='DUCK' and t>contact-.3
    silhouette(d,630,884,duck=duck,bat=s['shot']!='DUCK')
    for x in [648,654,660]:d.line((x,848,x,884),fill='#b4e5f0',width=3)
    u=max(0,min(1,(t-.7)/max(.5,contact-.7)))
    pts=[pitch_position(x/70*u,s['delivery']) for x in range(71)]
    if len(pts)>1:d.line(pts,fill=LIME,width=4)
    if t>.7:ball_dot(d,*pts[-1],7)
    if t>=s.get('reveal',contact+.4):
        msg='DUCK / DOT BALL' if s['shot']=='DUCK' else 'NO RUN'
        rr(d,(240,690,480,744),RED,r=12);center(d,698,msg,25,INK,True)
    return contact

def scoreboard(im,s,t):
    d=ImageDraw.Draw(im)
    n=s.get('ball',0);contact=s.get('contact',s['duration']*.49)
    reveal=t>s.get('reveal',contact+1.15)
    completed=(n if reveal else n-1) if n else (len(SIM['results']) if s['kind']=='end' else 0)
    done_results=SIM['results'][:max(0,completed)]
    score=score_of(done_results);wickets=int(is_wicket(done_results))
    rr(d,(30,955,690,1095),CREAM,r=20)
    tx(d,(50,969),BAT['short'],20,INK,True)
    tx(d,(50,996),f'{score}/{wickets}',62,INK,True)
    tx(d,(285,972),'BALLS',15,'#51606c',True)
    for j in range(6):
        x=303+j*59;done=j<completed
        rr(d,(x-22,1006,x+22,1050),INK if done else '#d6dcd7',r=22)
        label=str(SIM['results'][j]) if done else '·'
        center(d,1015,label,22,LIME if done and SIM['results'][j]==4 else (CREAM if done else '#667681'),True,x=x)
    need=max(0,TARGET-score);left=6-max(0,completed)
    msg=BAT['short']+' WINS' if score>=TARGET else (BOWL['short']+' WINS' if wickets else (f'NEED {need} FROM {left}' if left else BOWL['short']+' DEFENDS'))
    center(d,1068,msg,16,INK,True,x=485)

def bottom(im,s):
    d=ImageDraw.Draw(im)
    tx(d,(32,1120),'PLAYER FACTS / '+CONFIG['format'],14,BLUE,True)
    for i,fact in enumerate(CONFIG['facts'][:2]):
        tx(d,(32,1150+i*35),fact,19,CREAM,True)
    tx(d,(32,1240),'Data: '+CONFIG['source']+' / '+CONFIG['snapshot'],12,MUTED)

def stats(im,s,t):
    d=ImageDraw.Draw(im)
    rr(d,(30,657,690,940),CREAM,r=20)
    if not SUMMARY.get('balls_faced_excluding_wides'):
        center(d,686,'NO DIRECT H2H IN THIS DATASET',23,INK,True)
        for i,fact in enumerate(CONFIG['facts'][:2]):
            for j,line in enumerate(wrap(d,fact,21,585)):
                center(d,752+i*75+j*29,line,21,INK,True)
        center(d,898,'Separate player samples / imagined matchup',17,INK,True)
        scoreboard(im,s,t);bottom(im,s);return
    tx(d,(53,674),'REAL '+CONFIG['format']+' HEAD-TO-HEAD',21,INK,True)
    cols=[(140,str(SUMMARY['runs']),'RUNS'),(360,str(SUMMARY['balls_faced_excluding_wides']),'BALLS'),(580,str(SUMMARY['bowler_credited_dismissals']),'OUTS')]
    for j,(x,num,lab) in enumerate(cols):
        p=ease((t-.3-j*.35)/.8)
        center(d,735,int(int(num)*p).__str__(),73,INK,True,x=x)
        center(d,827,lab,18,'#4d626d',True,x=x)
    center(d,888,f"SR {SUMMARY['strike_rate']} / {SUMMARY['matchup_match_count']} matches in dataset",19,INK,True)
    scoreboard(im,s,t);bottom(im,s)

def intro(im,s,t):
    d=ImageDraw.Draw(im)
    rr(d,(30,658,690,937),LIME,r=20)
    center(d,685,'6 BALLS',83,INK,True)
    center(d,785,f'{TARGET} TO WIN',70,INK,True)
    center(d,884,'CAN THE BATTER FINISH THE CHASE?',19,INK,True)
    scoreboard(im,s,t);bottom(im,s)

def end(im,s,t):
    d=ImageDraw.Draw(im)
    rr(d,(30,658,690,937),LIME,r=20)
    center(d,677,'THIS WHAT-IF CHALLENGE',20,INK,True)
    won=score_of(SIM['results'])>=TARGET
    center(d,719,BAT['short'] if won else BOWL['short'],60,INK,True)
    center(d,818,f'CHASES {TARGET}' if won else f'DEFENDS {TARGET}',48,INK,True)
    center(d,891,f"{score_of(SIM['results'])}/{int(is_wicket(SIM['results']))} from {len(SIM['results'])} balls",21,INK,True)
    scoreboard(im,s,t);bottom(im,s)

def credits(im,s,t):
    d=ImageDraw.Draw(im)
    center(d,276,'REAL DATA / ORIGINAL ANIMATION',25,LIME,True)
    center(d,345,'DATA',18,BLUE,True)
    center(d,380,CONFIG['source'],25,CREAM,True)
    center(d,422,'Snapshot: '+CONFIG['snapshot'],17,MUTED)
    center(d,454,'Coverage: '+CONFIG['format'],17,MUTED)
    center(d,536,'ARTWORK',18,BLUE,True)
    center(d,578,'Matching AI portraits + cricket action art',22,CREAM,True)
    center(d,624,'Illustrations, not historical match photographs',19,MUTED)
    center(d,674,'Original schematic ball paths',18,MUTED)
    center(d,760,'STORY',18,BLUE,True)
    center(d,802,'Illustrated what-if cricket challenge',22,CREAM,True)
    center(d,849,'Historical statistics remain unchanged.',18,MUTED)
    center(d,899,'No measured speed, length or shot data claimed.',17,MUTED)
    center(d,942,'Hinglish narration / original sound effects',19,BLUE,True)
    center(d,991,'WHAT-IF CRICKET CHALLENGE',25,LIME,True)
    center(d,1050,'Full sources and method in companion notes.',17,MUTED)

def frame(global_t):
    s=SCENES[-1]
    for v in SCENES:
        if v['start']<=global_t<v['start']+v['duration']:s=v;break
    t=global_t-s['start'];im=BG.copy();header(im,s,t)
    if s['kind']=='credits':credits(im,s,t)
    else:
        player_panels(im,s,t)
        if s['kind']=='intro':intro(im,s,t)
        elif s['kind']=='stats':stats(im,s,t)
        elif s['kind']=='end':end(im,s,t)
        else:delivery(im,s,t);scoreboard(im,s,t);bottom(im,s)
        caption(im,s,t)
        if s['kind']=='ball':
            d=ImageDraw.Draw(im);rr(d,(46,245,187,278),LIME,r=15);center(d,251,f"BALL {s['ball']} / 6",16,INK,True,x=116)
    d=ImageDraw.Draw(im);d.rectangle((0,H-6,int(W*global_t/TOTAL),H),fill=LIME)
    # Quick graphic transition, without obscuring the rest of each scene.
    if t<.12:
        white=Image.new('RGB',(W,H),'#d9ff63');im=Image.blend(im,white,.17*(1-t/.12))
    return im

def audio():
    parts=[]
    for i,s in enumerate(SCENES[:-1]):
        p=A/f'audio_{i:02}.wav';parts.append(p)
        subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(A/f'voice_{i:02}.mp3'),'-af',f"apad,atrim=duration={s['duration']}",'-ar','48000','-ac','1',str(p)],check=True)
    p=A/'credit_silence.wav';parts.append(p)
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','lavfi','-i','anullsrc=r=48000:cl=mono','-t','4',str(p)],check=True)
    (A/'audio_concat.txt').write_text(''.join(f"file '{p}'\n" for p in parts))
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(A/'audio_concat.txt'),'-c','copy',str(A/'narration.wav')],check=True)
    sr=48000;n=int((TOTAL+.2)*sr);sfx=np.zeros(n,dtype=np.float64);rng=np.random.default_rng(73)
    def add(at,sig,vol):
        lo=int(at*sr);hi=min(n,lo+len(sig));sfx[lo:hi]+=sig[:hi-lo]*vol
    # Original synthesized impacts / swishes; no borrowed music or broadcast sound.
    for s in SCENES:
        ts=np.arange(int(.18*sr))/sr
        add(s['start'],np.sin(2*np.pi*(90*ts-110*ts*ts))*np.exp(-25*ts),.08)
        if s['kind']=='ball':
            contact=s['start']+s.get('contact',s['duration']*.49)
            tt=np.arange(int(.14*sr))/sr
            noise=rng.standard_normal(len(tt));sig=(np.sin(2*np.pi*320*tt)*.5+noise*.3)*np.exp(-42*tt)
            add(contact,sig,.18 if s['result'] else .07)
            if s['result']==4:
                tt=np.arange(int(.55*sr))/sr
                add(contact+.55,(np.sin(2*np.pi*660*tt)+np.sin(2*np.pi*880*tt))*.5*np.exp(-5*tt),.035)
    sfx=np.clip(sfx,-.7,.7)
    with wave.open(str(A/'sfx.wav'),'w') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes((sfx*32767).astype('<i2').tobytes())
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(A/'narration.wav'),'-i',str(A/'sfx.wav'),'-filter_complex','[0:a][1:a]amix=inputs=2:normalize=0,alimiter=limit=0.95[a]','-map','[a]','-t',str(TOTAL),str(A/'mix.wav')],check=True)

def finish(master):
    final=O/('CK001_Kohli_vs_Bumrah_Private_Preview.mp4' if not (A/'template.json').exists() else SIM['episode_id']+'_Private_Preview.mp4')
    speed=CONFIG.get('playback_speed',1.22)
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(master),'-vf',f'setpts=PTS/{speed}','-af',f'atempo={speed}','-r',str(FPS),'-c:v','libx264','-threads','2','-preset','fast','-crf','20','-c:a','aac','-b:a','160k','-movflags','+faststart',str(final)],check=True)
    print(final,flush=True)

if __name__=='__main__':
    if '--finish' in sys.argv:finish(A/'master.mp4');sys.exit(0)
    for sec in [1,10,21,31,45,62,TOTAL-2]:
        if sec<TOTAL:frame(sec).save(A/f'qa_{int(sec)}.jpg')
    if '--stills' in sys.argv:print(TOTAL);sys.exit(0)
    audio()
    path=A/'master.mp4'
    cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-i',str(A/'mix.wav'),'-c:v','libx264','-threads','2','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-t',str(TOTAL),'-movflags','+faststart',str(path)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    for k in range(math.ceil(TOTAL*FPS)):
        proc.stdin.write(frame(k/FPS).tobytes())
        if k%(FPS*10)==0:print('rendered',k//FPS,'seconds',flush=True)
    proc.stdin.close();code=proc.wait()
    if code:raise RuntimeError(f'ffmpeg failed: {code}')
    finish(path)
