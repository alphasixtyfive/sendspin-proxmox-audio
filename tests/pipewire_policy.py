"""Isolated PipeWire routing and virtual-output recovery checks.

Linux CT invocation (no installation):
  python3 tests/pipewire_policy.py --expected-hostname ACTUAL_CT --public-root . \
      --output /var/tmp/sendspin-policy-results-UNIQUE

Creates only disposable files/processes. Every audio/bus/tool child drops to
nobody with NO supplementary groups, a private 0700 runtime/home/config and a
private session bus. It refuses execution if that user can access any /dev/snd
entry. The private server has no ALSA SPA mapping/module/device, and only null
sinks. No systemctl, real MA/Sendspin connection, production socket or manual
pw-link is used. Linux parent-death signals and bounded process-group cleanup
apply only to children started by this fixture.

Coverage: actual stock pw-cat playback streams exercise the exact public
Sendspin stream-rule predicates and AUTOCONNECT API, with exact public loopback
configuration tested separately. This is NOT actual Sendspin-binary recovery,
hardware/USB recovery, samples/audibility, permissions against an administrator
forcing pw-link, or proof for arbitrary applications. Policy must create the
links automatically; manual links are never counted as policy success.

Primary API/source references:
https://docs.pipewire.org/page_man_pw-cat_1.html
https://raw.githubusercontent.com/PipeWire/pipewire/1.4.2/src/tools/pw-cat.c
https://pipewire.pages.freedesktop.org/wireplumber/daemon/locations.html
https://github.com/Sendspin/sendspin-cpp-cli/blob/45ff8b00e72ad1572a39e6e8ce21891748ab7d9e/src/pipewire_sink.cpp#L710
"""
from __future__ import annotations
import argparse,ctypes,hashlib,json,os,pwd,re,shutil,signal,socket,subprocess,sys,tempfile,time
from pathlib import Path

PINS={
 'client.conf.d/55-sendspin-room-targets.conf':'c96044a2eb6bbc5e04233bbb5cdb376cb58aaba51669ec6136a2680b7270d266',
 'pipewire.conf.d/60-zones.conf':'1f3c6db64ff92292f9fa1506bc47a644019469bfba8b72688ad77a13922e6ca4',
 'wireplumber.conf.d/51-manual-ca7.conf':'790d44c27d6be5166b16cb2b22fe0a026990af2cfa2b0c48104b3e95bb888608'}
PAIRS={}
LIMIT=150

def require(ok,message):
    if not ok:raise RuntimeError(message)
def write(path,data):
    path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
def props(obj):
    # Node/port/client info uses nested props; Metadata exports root-level props.
    return {**(obj.get('props') or {}),**((obj.get('info') or {}).get('props') or {})}
def named(graph,name):
    rows=[r for r in graph if r.get('type')=='PipeWire:Interface:Node' and props(r).get('node.name')==name]
    require(len(rows)<=1,'Duplicate private node name')
    return rows[0] if rows else None
def outputs(graph,name):
    node=named(graph,name)
    if node is None:return []
    rows={r['id']:r for r in graph};result=[]
    for row in graph:
        if row.get('type')!='PipeWire:Interface:Link':continue
        info=row.get('info') or {}
        if info.get('output-node-id')!=node['id']:continue
        dest=rows.get(info.get('input-node-id'),{})
        result.append({'target':props(dest).get('node.name'),'state':info.get('state'),
          'out_channel':props(rows.get(info.get('output-port-id'),{})).get('audio.channel'),
          'in_channel':props(rows.get(info.get('input-port-id'),{})).get('audio.channel')})
    return result
def exact(graph,source,target,channels=('FL','FR')):
    links=outputs(graph,source)
    return len(links)==2 and all(l['target']==target and l['state']=='active' for l in links) and sorted((l['out_channel'],l['in_channel']) for l in links)==sorted((c,c) for c in channels)
def merge(a,b):
    if not isinstance(a,dict) or not isinstance(b,dict):return b
    c=dict(a)
    for k,v in b.items():c[k]=merge(c[k],v) if k in c else v
    return c

class Runtime:
    def __init__(self,kind,source,out,uid,gid):
        self.kind,self.source,self.out,self.uid,self.gid=kind,source,out,uid,gid
        self.children=[];self.checks=[];self.parent=os.getpid();self.monitor=None
        self.phase='construct';self.command=None
        self.tmp=tempfile.TemporaryDirectory(prefix='sendspin-policy-')
        self.root=Path(self.tmp.name);self.remote='policy-'+self.root.name.rsplit('-',1)[-1]
        self.out.mkdir();self.logs=self.out/'logs';self.logs.mkdir()
        for name in ['run','home','config/pipewire/client.conf.d','config/pipewire/pipewire.conf.d',
                     'config/wireplumber/wireplumber.conf.d','state','cache','data','empty']:
            (self.root/name).mkdir(parents=True,exist_ok=True)
        pw=self.root/'config/pipewire';wp=self.root/'config/wireplumber'
        # Explicit config-dir environment ignores production config lookup locations.
        shutil.copyfile('/usr/share/pipewire/client.conf',pw/'client.conf')
        shutil.copyfile(self.source/'client.conf.d/55-sendspin-room-targets.conf',pw/'client.conf.d/55-sendspin-room-targets.conf')
        shutil.copyfile('/usr/share/wireplumber/wireplumber.conf',wp/'wireplumber.conf')
        shutil.copyfile(self.source/'wireplumber.conf.d/51-manual-ca7.conf',wp/'wireplumber.conf.d/51-manual-ca7.conf')
        (wp/'wireplumber.conf.d/99-isolated-no-hardware.conf').write_text('''wireplumber.profiles = {
 main = { monitor.alsa = disabled monitor.bluez = disabled monitor.bluez-midi = disabled
          monitor.v4l2 = disabled monitor.libcamera = disabled }
}
''')
        if kind=='loopbacks':shutil.copyfile(self.source/'pipewire.conf.d/60-zones.conf',pw/'pipewire.conf.d/60-zones.conf')
        (pw/'pipewire.conf').write_text('''context.properties = {
 core.daemon = true core.name = "%s" default.clock.rate = 48000
 default.clock.quantum = 512 default.clock.min-quantum = 512
}
context.spa-libs = { audio.convert.* = audioconvert/libspa-audioconvert support.* = support/libspa-support }
context.modules = [
 { name = libpipewire-module-protocol-native args = { sockets = [ { name = "%s" } ] } }
 { name = libpipewire-module-access args = { access.socket = { "%s" = "unrestricted" } } }
 { name = libpipewire-module-metadata }
 { name = libpipewire-module-spa-node-factory }
 { name = libpipewire-module-client-node }
 { name = libpipewire-module-adapter }
 { name = libpipewire-module-link-factory }
 { name = libpipewire-module-session-manager }
]
context.objects = [
 { factory = spa-node-factory args = { factory.name = support.node.driver node.name = Policy-Dummy-Driver priority.driver = 20000 } }
]
'''%(self.remote,self.remote,self.remote))
        bus=self.root/'run/bus'
        (self.root/'bus.conf').write_text('''<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN" "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig><type>session</type><listen>unix:path=%s</listen><auth>EXTERNAL</auth>
<policy context="default"><allow own="*"/><allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>
'''%bus)
        for p in [self.root,*self.root.rglob('*')]:
            os.chown(p,uid,gid);p.chmod(0o700 if p.is_dir() else 0o600)
        self.env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8',
          'HOME':str(self.root/'home'),'XDG_RUNTIME_DIR':str(self.root/'run'),
          'PIPEWIRE_RUNTIME_DIR':str(self.root/'run'),'PIPEWIRE_REMOTE':self.remote,
          'PIPEWIRE_CONFIG_DIR':str(pw),'WIREPLUMBER_CONFIG_DIR':str(wp),
          'XDG_CONFIG_HOME':str(self.root/'config'),'XDG_CONFIG_DIRS':str(self.root/'empty'),
          'XDG_STATE_HOME':str(self.root/'state'),'XDG_CACHE_HOME':str(self.root/'cache'),
          'XDG_DATA_HOME':str(self.root/'data'),'XDG_DATA_DIRS':'/usr/share',
          'DBUS_SESSION_BUS_ADDRESS':'unix:path='+str(bus),
          'DBUS_SYSTEM_BUS_ADDRESS':'unix:path='+str(bus)}

    def drop(self):
        os.setgroups([]);os.setgid(self.gid);os.setuid(self.uid)
        libc=ctypes.CDLL(None,use_errno=True)
        require(libc.prctl(38,1,0,0,0)==0,'Could not set no-new-privileges')
        # Set after UID/GID changes, which otherwise clear the parent-death setting.
        require(libc.prctl(1,signal.SIGKILL,0,0,0)==0,'Could not set parent-death signal')
        require(os.getppid()==self.parent,'Fixture parent exited before child setup')

    def launch(self,args,*,capture=False,name=None,raw_zero=False):
        require(self.root.exists() and self.env['PIPEWIRE_REMOTE']==self.remote,'Private context lost')
        if capture:dest=subprocess.PIPE
        else:
            dest=(self.logs/(name+'.log')).open('wb')
        source=open("/dev/zero","rb") if raw_zero else None
        try:p=subprocess.Popen(args,env=self.env,cwd=self.root,stdin=source if source is not None else subprocess.DEVNULL,
            stdout=dest,stderr=subprocess.PIPE if capture else subprocess.STDOUT,
            preexec_fn=self.drop,start_new_session=True)
        finally:
            if not capture:dest.close()
            if source is not None:source.close()
        self.children.append(p);return p

    def run(self,args,timeout=8):
        program=Path(args[0]).name
        operation=args[3] if program=='pw-cli' and len(args)>3 and args[3] in ['create-node','destroy'] else 'execute'
        self.command=program+':'+operation
        event={'phase':self.phase,'command':program,'operation':operation,'started_monotonic':time.monotonic()}
        def record():
            with (self.logs/'tool-events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
        p=self.launch(args,capture=True)
        try:out,err=p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.stop(p);out,err=p.communicate()
            event.update(status='timed_out',returncode=p.returncode,stdout_bytes=len(out),stderr_bytes=len(err));record()
            if out:(self.logs/'timed-out-tool-stdout.log').write_bytes(out)
            if err:(self.logs/'timed-out-tool-stderr.log').write_bytes(err)
            raise RuntimeError('Private stock-tool timed out: '+self.command) from None
        event.update(status='completed',returncode=p.returncode,stdout_bytes=len(out),stderr_bytes=len(err));record()
        if err:
            with (self.logs/'tools-stderr.log').open('ab') as f:f.write(err)
        require(p.returncode==0,'Private stock-tool command failed; inspect fixture logs')
        return out.decode('utf-8')

    def stop(self,p):
        if p.poll() is not None:return
        try:os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError:return
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait(timeout=3)

    def graph(self):
        data=json.loads(self.run(['pw-dump','-r',self.remote]))
        require(isinstance(data,list),'Private graph dump malformed')
        allowed={'policy_wrong_a','policy_wrong_b','ca7_card_a','ca7_card_b'}|{'sendspin_zone-'+str(n) for n in PAIRS}
        for row in data:
            pr=props(row)
            require(pr.get('device.api')!='alsa' and 'api.alsa.path' not in pr,'Hardware appeared in isolated graph')
            if row.get('type')=='PipeWire:Interface:Node' and pr.get('media.class')=='Audio/Sink':
                require(pr.get('node.name') in allowed,'Unexpected sink in private graph')
        return data

    def wait(self,label,predicate,seconds=7):
        self.phase=label
        until=time.monotonic()+seconds;last=[]
        while time.monotonic()<until:
            last=self.graph()
            if predicate(last):
                write(self.out/(label+'.json'),last);self.checks.append({'check':label,'ok':True});return last
            time.sleep(.12)
        write(self.out/(label+'-FAILED.json'),last)
        raise RuntimeError('Timed out: '+label)

    def hold(self,label,predicate,seconds=1.5):
        self.phase=label
        until=time.monotonic()+seconds;count=0;last=[]
        while time.monotonic()<until:
            last=self.graph();require(predicate(last),'Invariant failed: '+label);count+=1;time.sleep(.12)
        require(count>=3,'Too few independent graph observations')
        write(self.out/(label+'.json'),last);self.checks.append({'check':label,'ok':True,'samples':count})

    def setup(self):
        self.phase='setup-sound-device-access-check'
        # Run this check with the exact credentials used for every audio process.
        self.run([sys.executable,'-I','-c',"import os,pathlib,stat; assert os.getuid()==65534 and os.getgid()==65534 and os.getgroups()==[]; assert all(not os.access(p,os.R_OK) and not os.access(p,os.W_OK) for p in pathlib.Path('/dev/snd').glob('*') if stat.S_ISCHR(p.stat().st_mode))"])
        self.checks.append({'check':'nobody_has_no_sound_device_access','ok':True})
        self.phase='setup-private-bus-server-manager'
        self.bus=self.launch(['dbus-daemon','--nofork','--nopidfile','--config-file='+str(self.root/'bus.conf')],name='private-bus')
        until=time.monotonic()+5
        while not (self.root/'run/bus').is_socket() and time.monotonic()<until:time.sleep(.05)
        require((self.root/'run/bus').is_socket(),'Private bus failed to start')
        self.server=self.launch(['pipewire','-c','pipewire.conf'],name='private-pipewire')
        until=time.monotonic()+5
        while not (self.root/'run'/self.remote).is_socket() and time.monotonic()<until:time.sleep(.05)
        require((self.root/'run'/self.remote).is_socket(),'Private PipeWire failed to start')
        self.manager=self.launch(['wireplumber'],name='private-wireplumber')
        self.monitor=self.launch(['pw-dump','-r',self.remote,'--monitor'],name='graph-events')
        self.null('policy_wrong_a');self.null('policy_wrong_b')
        self.wait('manager-present',lambda g:any(props(r).get('application.name')=='WirePlumber' for r in g))

    def null(self,name,channels=2):
        positions=['FL','FR'] if channels==2 else ['FL','FR','FC','LFE','RL','RR','SL','SR']
        values={'factory.name':'support.null-audio-sink','node.name':name,'node.description':name,
          'media.class':'Audio/Sink','audio.channels':channels,'audio.position':positions,
          'audio.rate':48000,'node.pause-on-idle':False,'object.linger':True,
          'adapter.auto-port-config':{'mode':'dsp','monitor':False,'position':'preserve'}}
        self.run(['pw-cli','-r',self.remote,'create-node','adapter',json.dumps(values)])
        return self.wait('created-'+name,lambda g:named(g,name) is not None)

    def destroy(self,name):
        node=named(self.graph(),name);require(node is not None,'Private deletion target absent')
        serial=props(node).get('object.serial');require(serial is not None,'Private deletion target has no object serial')
        self.run(['pw-cli','-r',self.remote,'destroy',str(node['id'])])
        self.wait('removed-'+name,lambda g:named(g,name) is None)
        return serial

    def default(self,name):
        node=named(self.graph(),name);require(node is not None,'Default-test null sink absent')
        self.run(['wpctl','set-default',str(node['id'])])
        def matches(g):
            for row in g:
                if props(row).get('metadata.name')!='default':continue
                for val in row.get('metadata') or []:
                    if val.get('key')=='default.audio.sink':
                        actual=val.get('value')
                        if isinstance(actual,str):
                            try:actual=json.loads(actual)
                            except ValueError:return False
                        return isinstance(actual,dict) and actual.get('name')==name
            return False
        self.wait('default-'+name,matches)

    def player(self,name,target=None,match=True,expect_missing=False):
        values={'application.name':'sendspin-cli' if match else 'policy-control','node.name':name}
        cmd=['pw-cat','-R',self.remote,'--playback','--raw','--rate','48000','--channels','2','--format','s16','--properties',json.dumps(values)]
        if target:cmd+=['--target',target]
        cmd+=['-']
        p=self.launch(cmd,name=name,raw_zero=True)
        if expect_missing:
            self.phase='missing-target-client-rejection'
            deadline=time.monotonic()+4
            while p.poll() is None and time.monotonic()<deadline:time.sleep(.1)
            require(p.poll() is not None,'Missing-target pw-cat did not exit as observed')
            require('defined target not found' in (self.logs/(name+'.log')).read_text(),'Missing target was not the rejection reason')
            require(not outputs(self.graph(),name),'Rejected client retained an output link')
            self.checks.append({'check':'missing-target-rejected-without-fallback','ok':True,'client_exited':True})
            return p
        g=self.wait('stream-'+name,lambda g:named(g,name) is not None)
        if match:
            pr=props(named(g,name));require(pr.get('node.dont-fallback') in [True,'true'] and pr.get('node.dont-move') in [True,'true'],'Exact public client rule did not apply')
            require(pr.get('target.object')==target,'Stream target property changed')
        return p

    def audit_events(self):
        require(self.monitor is not None and self.monitor.poll() is None,'Private graph event monitor stopped early')
        self.stop(self.monitor)
        text=(self.logs/'graph-events.log').read_text();decoder=json.JSONDecoder();pos=0;objects={};batches=0;link_checks=0
        while pos<len(text):
            while pos<len(text) and text[pos].isspace():pos+=1
            if pos==len(text):break
            batch,pos=decoder.raw_decode(text,pos);require(isinstance(batch,list),'Invalid graph event batch')
            for obj in batch:
                if obj.get('info','present') is None:objects.pop(obj['id'],None)
                else:objects[obj['id']]=merge(objects.get(obj['id'],{}),obj)
            # Link auditing needs only current node/port/link identities and props.
            # Metadata updates contain partial key lists; their replacement here is
            # deliberately not used to infer defaults or policy decisions. The live
            # default assertion reads a fresh full snapshot in default(), above.
            graph=list(objects.values());batches+=1
            for row in graph:
                if row.get('type')!='PipeWire:Interface:Node':continue
                name=props(row).get('node.name','')
                if name=='policy.play':target='sendspin_zone-1'
                elif name.startswith('policy.zone-'):target='sendspin_zone-'+name.rsplit('-',1)[-1]
                elif name.startswith('playback.sendspin_zone-'):
                    n=int(name.rsplit('-',1)[-1]);target=PAIRS[n][0]
                else:continue
                for link in outputs(graph,name):
                    # If an endpoint was removed in this batch, no resolved destination
                    # remains to classify. Never treat an unknown endpoint as success.
                    if link['target'] is None:continue
                    require(link['target']==target,'Automatic wrong-target link appeared in event history');link_checks+=1
        require(batches>=5 and link_checks>=4,'Insufficient event history for policy claim')
        self.checks.append({'check':'no_automatic_wrong_target_in_full_event_history','ok':True,'event_batches':batches,'link_observations':link_checks})

    def close(self):
        for p in reversed(self.children):self.stop(p)
        root=self.root.resolve();require(root.parent==Path(tempfile.gettempdir()).resolve() and root.name.startswith('sendspin-policy-'),'Temporary cleanup scope guard')
        self.tmp.cleanup()

def client_case(r):
    r.setup();r.default('policy_wrong_a')
    control=r.player('policy.control-a',match=False)
    r.wait('positive-default-a',lambda g:exact(g,'policy.control-a','policy_wrong_a'))
    r.hold('positive-control-sustained-input',lambda g:control.poll() is None and exact(g,'policy.control-a','policy_wrong_a'))
    rejected=r.player('policy.play','sendspin_zone-1',expect_missing=True)
    r.hold('missing-room-no-fallback',lambda g:not outputs(g,'policy.play'))
    r.default('policy_wrong_b');r.player('policy.control-b',match=False)
    r.wait('positive-default-b',lambda g:exact(g,'policy.control-b','policy_wrong_b'))
    r.hold('missing-room-default-changed-still-no-fallback',lambda g:not outputs(g,'policy.play'))
    r.null('sendspin_zone-1')
    p=r.player('policy.play','sendspin_zone-1')
    require(p.pid!=rejected.pid,'Client retry did not create a new process')
    r.wait('explicit-new-stream-after-target-appears',lambda g:exact(g,'policy.play','sendspin_zone-1'))
    r.default('policy_wrong_a')
    r.hold('present-room-default-change-does-not-move',lambda g:p.poll() is None and exact(g,'policy.play','sendspin_zone-1'))
    previous=r.destroy('sendspin_zone-1')
    r.hold('removed-room-no-fallback',lambda g:not outputs(g,'policy.play'))
    r.null('sendspin_zone-1')
    if p.poll() is not None:
        p=r.player('policy.play','sendspin_zone-1')
        label='explicit-new-stream-after-target-returns'
    else:label='existing-stream-auto-reconnect-exact'
    g=r.wait(label,lambda g:exact(g,'policy.play','sendspin_zone-1'))
    require(props(named(g,'sendspin_zone-1')).get('object.serial')!=previous,'Returned target did not have a fresh object serial')
    r.checks.append({'check':'client-recovery-boundary-recorded','ok':True,'initial_missing_target':'pw-cat rejects; explicit new client after target exists','removed_target_recovery':label,'actual_Sendspin_recovery_tested':False})
    r.audit_events()


def loopback_case(r):
    r.setup();r.null('ca7_card_a',8);r.null('ca7_card_b',8);r.default('policy_wrong_a')
    players=[]
    for n in PAIRS:players.append(r.player('policy.zone-'+str(n),'sendspin_zone-'+str(n)))
    def all_routes(g):return all(exact(g,'policy.zone-'+str(n),'sendspin_zone-'+str(n)) and exact(g,'playback.sendspin_zone-'+str(n),target,(left,right)) for n,(target,left,right) in PAIRS.items())
    r.wait('all-seven-automatic-stereo-pairs',all_routes)
    r.default('policy_wrong_b');r.hold('all-seven-ignore-wrong-default',all_routes)
    old_id=r.destroy('ca7_card_a')
    def missing_a(g):
        return all(p.poll() is None for p in players) and all(not outputs(g,'playback.sendspin_zone-'+str(n)) if target=='ca7_card_a' else exact(g,'playback.sendspin_zone-'+str(n),target,(left,right)) for n,(target,left,right) in PAIRS.items())
    r.wait('missing-card-a-no-wrong-sink-links',missing_a);r.hold('missing-card-a-stays-fail-closed',missing_a)
    r.default('policy_wrong_a');r.hold('missing-card-a-default-change-stays-fail-closed',missing_a)
    r.null('ca7_card_a',8)
    g=r.wait('returned-card-a-all-exact-pairs-restored',all_routes)
    require(props(named(g,'ca7_card_a')).get('object.serial')!=old_id,'Returned card surrogate did not have a fresh object serial')
    r.audit_events()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--expected-hostname',required=True)
    ap.add_argument('--public-root',required=True,type=Path);ap.add_argument('--output',required=True,type=Path)
    a=ap.parse_args();result={'status':'failed','scope':'stock-PipeWire-policy-only','cases':{},'limits':[
      'Uses actual pw-cat streams matching Sendspin properties, not Sendspin binary/server playback',
      'Null sinks only; no physical/USB/audio-quality proof',
      'No manual pw-link. pw-cat rejection uses an explicit new client after target returns; this is not Sendspin automatic recovery.']}
    active=None;output_owned=False
    try:
        require(sys.platform.startswith('linux') and os.geteuid()==0,'Run only as root in the dedicated audio CT')
        require(socket.gethostname()==a.expected_hostname,'Unexpected CT hostname')
        require(subprocess.check_output(['systemd-detect-virt','--container'],text=True).strip()=='lxc','Not an LXC container')
        require(not a.output.exists(),'Fresh output directory required')
        account=pwd.getpwnam('nobody');require(account.pw_uid==65534 and account.pw_gid==65534,'Unexpected nobody UID/GID')
        for command in ['pipewire','wireplumber','pw-cli','pw-cat','pw-dump','wpctl','dbus-daemon']:require(shutil.which(command),'Missing stock test prerequisite')
        versions={cmd:subprocess.check_output([cmd,'--version'],text=True,stderr=subprocess.STDOUT).strip() for cmd in ['pipewire','wireplumber']}
        require('1.4.2' in versions['pipewire'] and '0.5.8' in versions['wireplumber'],'Reviewed production PW/WP baseline differs')
        result['versions']=versions;source=a.public_root/'examples/two-ca7-seven-zones'
        for rel,digest in PINS.items():require(hashlib.sha256((source/rel).read_bytes()).hexdigest()==digest,'Reviewed public configuration hash mismatch')
        result['source_sha256']=PINS
        # The installed routing file owns target/channel assignments; don't duplicate them.
        blocks=re.findall(r'playback[.]props\s*=\s*[{]([^{}]+)[}]',(source/'pipewire.conf.d/60-zones.conf').read_text())
        for block in blocks:
            number=re.search(r'node[.]name\s*=\s*"playback[.]sendspin_zone-(\d+)"',block)
            target=re.search(r'target[.]object\s*=\s*"(ca7_card_[ab])"',block)
            channels=re.search(r'audio[.]position\s*=\s*\[\s*([A-Z]+)\s+([A-Z]+)\s*\]',block)
            require(number is not None and target is not None and channels is not None,'Unsupported pinned route syntax')
            n=int(number.group(1));require(n not in PAIRS,'Duplicate configured zone')
            PAIRS[n]=(target.group(1),channels.group(1),channels.group(2))
        require(set(PAIRS)==set(range(1,8)) and len(set(PAIRS.values()))==7,'Pinned seven-zone route inventory differs')
        result['configured_routes']={str(k):v for k,v in PAIRS.items()}
        a.output.mkdir(mode=0o700);output_owned=True
        def interrupted(_signum,_frame):raise RuntimeError('Bounded fixture interrupted')
        signal.signal(signal.SIGALRM,interrupted);signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted);signal.alarm(LIMIT)
        for name,test in [('client-policy',client_case),('loopbacks',loopback_case)]:
            active=Runtime(name,source,a.output/name,account.pw_uid,account.pw_gid)
            try:test(active);result['cases'][name]={'status':'passed','checks':active.checks}
            except BaseException:
                result['cases'][name]={'status':'failed','checks':active.checks,'phase':active.phase,'command':active.command}
                raise
            finally:active.close();active=None
        signal.alarm(0);result['status']='passed'
    except BaseException as exc:
        result['error_type']=type(exc).__name__
        if isinstance(exc,RuntimeError):result['guard']=str(exc)
        if active is not None:result['partial_checks']=active.checks
    finally:
        signal.alarm(0)
        if active is not None:active.close()
        if output_owned:write(a.output/'result.json',result)
    print(json.dumps({'status':result['status'],'cases':{k:v['status'] for k,v in result['cases'].items()},'guard':result.get('guard'),'output':str(a.output)}))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':sys.exit(main())
