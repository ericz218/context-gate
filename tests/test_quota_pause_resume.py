"""Owned quota pauses and automatic continuation: ACCEPTANCE.md A1-A8, C1-C7, R1-R8, S1-S3.

Everything runs in temporary directories with a fake clock, a fake worker spawner and launch=False
(or a patched start_worker). No signals, sockets, native CLIs or production consoles are touched.
Test names carry the acceptance number they cover.
"""
import fcntl
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import console_quota as cq
import console_quota_stop as cqs
import group_chat
from control_center import Center, write_json
from group_chat import Groups, QUOTA_CONTINUE


class Clock:
    def __init__(self):self.now=1000.0
    def __call__(self):return self.now
    def tick(self,seconds):self.now+=seconds


def window(remaining=60,resets=2000,bucket='default',window='five_hour'):
    return {'bucket':bucket,'window':window,'remaining':remaining,'resets_at':resets}


def state(account,status,updated,windows,checked_at=None):
    # A real check stamps checked_at at the same moment; checked_at=None models the
    # restart-restored display state, which must never satisfy resume by itself.
    return {'account':account,'status':status,'updated_at':updated,'windows':windows,
            'checked_at':updated if checked_at is None else checked_at}


def healthy(now,codex=60,claude=80,resets=2000,claude_account='acct-B'):
    return {'codex':state('acct-A','ok',now,[window(remaining=codex,resets=resets)]),
            'claude':state(claude_account,'ok',now,[window(remaining=claude)])}


def prefs(resume_codex=True,claude_enabled=False,resume_claude=False):
    return {'codex':dict(cq.DEFAULT,enabled=True,stop_all=True,resume_paused=resume_codex),
            'claude':dict(cq.DEFAULT,enabled=claude_enabled,stop_all=claude_enabled,resume_paused=resume_claude and claude_enabled)}


def low_payload(platform='codex',observed=1000.0,account=None,auto=True,accounts=None):
    account=account or {'codex':'acct-A','claude':'acct-B'}[platform]
    return {'platform':platform,'auto_resume':auto,'accounts':accounts or {'codex':'acct-A','claude':'acct-B'},
            'blockers':[{'platform':platform,'account':account,'bucket':'default','window':'five_hour','threshold':10,'reset':1500,'observed_at':observed}]}


def lock_held(path):
    """True when another open file description already holds an exclusive flock on path."""
    with Path(path).open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        fcntl.flock(handle,fcntl.LOCK_UN)
        return False


def lock_free_elsewhere(lock):
    """An RLock is reentrant for its owner, so probe from another thread."""
    result=[]
    def attempt():
        if lock.acquire(timeout=1):
            result.append(True);lock.release()
        else:result.append(False)
    thread=threading.Thread(target=attempt);thread.start();thread.join()
    return result[0]


class QuotaCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        self.root=base/'project';self.root.mkdir()
        self.root2=base/'project-two';self.root2.mkdir()
        self.state=base/'state';self.state.mkdir()
        self.clock=Clock();self.spawned=[]
        self.center,self.groups=self.build()
        self.gid=self.groups.create({'root':str(self.root),'name':'team'})['id']
        self.alpha=self.groups.add({'group':self.gid,'slug':'alpha','platform':'codex','model':'gpt-6-sol'})['id']
        self.beta=self.groups.add({'group':self.gid,'slug':'beta','platform':'claude','model':'sonnet'})['id']
        self.protection=self.protect()

    def build(self):
        center=Center(self.state,[self.root,self.root2])
        center._spawn=self.spawn
        return center,Groups(self.state,center,launch=False)

    def spawn(self,tid,bundle):
        self.spawned.append(tid)
        return SimpleNamespace(pid=50000+len(self.spawned),wait=lambda:0)

    def protect(self,external=None):
        return cqs.Protection(self.state,self.center,self.groups,None,external=external,clock=self.clock,timeout=0)

    def restart(self):
        """Fresh objects over the same state directory, as after a service restart."""
        self.center,self.groups=self.build()
        self.protection=self.protect()
        return self.protection

    # ---- fixtures ----
    def task(self,root=None,platform='codex',status='running',**fields):
        tid=self.center.create({'root':str(root or self.root),'platform':platform,'goal':'finish module'},launch=False)['task_id']
        if status=='running':
            fields.setdefault('pid',4242);fields.setdefault('session_id','session-'+tid[:8])
        self.put(tid,status=status,**fields)
        return tid

    def put(self,tid,**fields):
        path=self.center.path(tid);data=json.loads(path.read_text());data.update(fields);write_json(path,data)

    def queued(self,member,text='work'):
        return self.groups.send({'group':self.gid,'text':text,'members':[member]})['jobs'][0]

    def job(self,jid):
        with self.groups.connect() as db:return dict(db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())

    def set_job(self,jid,**fields):
        with self.groups.connect() as db:
            for key,value in fields.items():db.execute('UPDATE jobs SET %s=? WHERE id=?'%key,(value,jid))

    def set_member(self,mid,**fields):
        with self.groups.connect() as db:
            for key,value in fields.items():db.execute('UPDATE members SET %s=? WHERE id=?'%key,(value,mid))

    def run_job(self,jid,member,session):
        self.set_job(jid,status='running');self.set_member(member,session=session)

    def qp(self,jid):
        return json.loads(self.job(jid)['quota_pause'] or 'null')

    def job_count(self,member=None):
        with self.groups.connect() as db:
            if member is None:return db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
            return db.execute('SELECT COUNT(*) FROM jobs WHERE member=?',(member,)).fetchone()[0]

    def queued_count(self,member):
        with self.groups.connect() as db:
            return db.execute("SELECT COUNT(*) FROM jobs WHERE member=? AND status='queued'",(member,)).fetchone()[0]

    def journal(self):
        return json.loads((self.state/'quota-pauses.json').read_text())

    def targets(self):
        return [t for c in self.journal()['cycles'] for t in c['targets']]

    def target(self,ident):
        return next(t for t in self.targets() if t['id']==ident)

    def children(self,parent=None):
        out=[]
        for path in self.center.folder.glob('*/task.json'):
            data=json.loads(path.read_text());link=data.get('quota_resume')
            if link and (parent is None or link['parent']==parent):out.append(data)
        return out

    def pause_codex(self):
        return self.protection.pause(low_payload('codex',observed=self.clock.now))


class A_ScopeAndRestoreTests(QuotaCase):
    def test_A1_only_this_pauses_captured_work_resumes_and_history_never(self):
        historic_task=self.task(status='stopped')
        historic_job=self.queued(self.alpha,'old instruction')
        self.groups.stop({'group':self.gid,'members':[self.alpha]})
        captured=self.task()
        self.pause_codex()
        self.put(captured,status='stopped')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual([c['parent'] for c in self.children()],[captured])
        self.assertNotIn(historic_task,[t['id'] for t in self.targets()])  # history is never even captured
        self.assertIsNone(self.center.quota_claim(historic_task))
        self.assertEqual(self.center.get(historic_task)['status'],'stopped')
        self.assertEqual(self.job(historic_job)['status'],'stopped')
        self.assertIsNone(self.job(historic_job)['quota_pause'])
        self.assertEqual(self.queued_count(self.alpha),0)

    def test_A1_restart_restored_display_never_resumes_without_a_real_check(self):
        # A backend restart restores the last snapshot for display (status ok, checked_at None).
        # Even with every other resume condition satisfied, that display must not auto-resume:
        # the blockers require one real post-restart check.
        captured=self.task()
        self.pause_codex()
        self.put(captured,status='stopped')  # the worker honours the stop request
        restored={'codex':{'account':'acct-A','status':'ok','updated_at':self.clock.now+60,'checked_at':None,
                           'windows':[window(remaining=90)]},
                  'claude':{'account':'acct-B','status':'ok','updated_at':self.clock.now+60,'checked_at':None,
                            'windows':[window(remaining=90)]}}
        self.protection.reconcile(restored,prefs())
        self.assertEqual(self.children(),[])
        real={'codex':dict(restored['codex'],checked_at=self.clock.now+60),
              'claude':dict(restored['claude'],checked_at=self.clock.now+60)}
        self.clock.tick(60)
        self.protection.reconcile(real,prefs())
        self.assertEqual(len(self.children()),1)  # the first real check releases the pause

    def test_A2_manual_stop_after_claim_revokes_centre_and_group_claims(self):
        centre=self.task()
        job=self.queued(self.alpha,'work')
        self.pause_codex()
        self.put(centre,status='stopped')
        self.assertEqual(self.center.quota_claim(centre)['state'],'pending')
        self.center.stop(centre)  # manual stop of an already-stopped task
        self.assertEqual(self.center.quota_claim(centre)['state'],'revoked')
        self.groups.stop({'group':self.gid,'members':[self.alpha]})
        self.assertEqual(self.qp(job)['state'],'revoked')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.children(),[])
        self.assertEqual(self.job(job)['status'],'stopped')
        self.assertEqual(self.queued_count(self.alpha),0)
        self.assertEqual({t['status'] for t in self.targets()},{'revoked'})

    def test_A3_queued_job_resumes_same_id_once_and_running_gets_deterministic_continuation(self):
        queued=self.queued(self.alpha,'queued instruction')
        running=self.queued(self.beta,'running instruction')
        self.run_job(running,self.beta,session='beta-native-session')
        self.pause_codex()
        self.assertEqual(self.job(queued)['status'],'stopped')
        self.assertEqual(self.job(running)['status'],'stopping')
        self.set_job(running,status='stopped')  # worker interrupted the native turn
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs(claude_enabled=True))
        restored=self.job(queued)
        self.assertEqual((restored['id'],restored['status'],restored['stop']),(queued,'queued',0))
        self.assertEqual(self.qp(queued)['state'],'dispatched')
        continuation=str(uuid.uuid5(uuid.NAMESPACE_URL,'context-gate-quota-resume:'+self.target(running)['claim_id']))
        cont=self.job(continuation)
        self.assertEqual((cont['status'],cont['member'],cont['depth'],cont['text']),('queued',self.beta,self.job(running)['depth'],QUOTA_CONTINUE))
        self.assertEqual(self.job(running)['status'],'stopped')
        self.assertEqual(self.job(running)['text'],'running instruction')
        self.assertEqual(self.qp(running)['state'],'consumed')
        count=self.job_count()
        self.protection.reconcile(healthy(self.clock.now),prefs(claude_enabled=True))
        self.assertEqual(self.job_count(),count)  # restored once, continued once

    def test_A4_repeated_reconcile_restart_and_relow_never_double_dispatch(self):
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60);now=self.clock.now
        self.protection.reconcile(healthy(now),prefs())
        self.protection.reconcile(healthy(now),prefs())
        self.restart().reconcile(healthy(now),prefs())
        self.assertEqual(len(self.children(tid)),1)
        self.assertEqual(len(self.spawned),1)
        # Low again: the running continuation is captured under a new claim; the consumed parent claim is never reused.
        self.protection.pause(low_payload('codex',observed=now+30))
        self.protection.reconcile(healthy(now+90),prefs())
        self.assertEqual(len(self.children(tid)),1)
        self.assertEqual(len(self.spawned),1)
        self.assertEqual(self.center.quota_claim(tid)['state'],'consumed')

    def test_A5_codex_recovered_while_claude_low_unknown_error_or_switched_holds_whole_set(self):
        codex_task=self.task()
        claude_task=self.task(root=self.root2,platform='claude')
        self.pause_codex()
        self.put(codex_task,status='stopped');self.put(claude_task,status='stopped')
        self.clock.tick(30)
        self.protection.pause(low_payload('claude',observed=self.clock.now))  # Claude becomes a second blocker
        cycles=self.journal()['cycles']
        self.assertEqual(len(cycles),1);self.assertEqual(len(cycles[0]['blockers']),2)
        t=self.clock.now;on=prefs(claude_enabled=True,resume_claude=True)
        cases={'low':healthy(t+1,claude=1),
               'error':{**healthy(t+2),'claude':state('acct-B','error',t+2,[window(remaining=80)])},
               'unknown':{**healthy(t+3),'claude':state(None,'ok',t+3,[window(remaining=80)])},
               'switched':{**healthy(t+4),'claude':state('acct-C','ok',t+4,[window(remaining=80)])}}
        for name,states in cases.items():
            with self.subTest(claude=name):
                self.protection.reconcile(states,on)
                self.assertEqual(self.children(),[],name)
        self.protection.reconcile(healthy(t+10,claude=60),on)
        self.assertEqual(sorted(c['parent'] for c in self.children()),sorted([codex_task,claude_task]))

    def test_A6_changed_session_refuses_automatic_continuation(self):
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped',session_id='replacement-session')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.children(),[])
        self.assertEqual((self.target(tid)['status'],self.target(tid)['reason']),('attention','fingerprint_changed'))

    def test_A6_changed_model_refuses_automatic_continuation(self):
        tid=self.task(root=self.root2,platform='claude')
        self.protection.pause(low_payload('codex',observed=self.clock.now))
        self.put(tid,status='stopped',model='opus')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs(claude_enabled=True))
        self.assertEqual(self.children(),[])
        self.assertEqual(self.target(tid)['reason'],'fingerprint_changed')

    def test_A6_changed_project_root_refuses_automatic_continuation(self):
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped',root=str(self.root.parent/'elsewhere'))
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.children(),[])
        self.assertEqual(self.target(tid)['reason'],'fingerprint_changed')

    def test_A6_new_active_work_in_same_project_waits_then_resumes(self):
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped')
        newer=self.task()  # a new running task in the same project
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.children(),[])
        self.assertEqual((self.target(tid)['status'],self.target(tid)['reason']),('paused','project_busy'))
        self.put(newer,status='stopped')
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual([c['parent'] for c in self.children()],[tid])

    def test_A6_parent_not_stopped_is_waiting_then_refused(self):
        tid=self.task()
        self.pause_codex()
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())  # still running: stop not confirmed
        self.assertEqual((self.target(tid)['status'],self.target(tid)['reason']),('paused','stop_unconfirmed'))
        self.put(tid,status='pending_review')
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.children(),[])
        self.assertEqual((self.target(tid)['status'],self.target(tid)['reason']),('attention','not_stopped'))

    def test_A7_resume_defaults_off_legacy_settings_load_and_dependencies_are_validated(self):
        self.assertIs(cq.DEFAULT['resume_paused'],False)
        legacy={p:{k:v for k,v in cq.DEFAULT.items() if k!='resume_paused'} for p in cq.PLATFORMS}
        (self.state/'quota-settings.json').write_text(json.dumps(legacy))
        self.assertIs(cq.Quotas(self.state).settings()['codex']['resume_paused'],False)
        for enabled,stop_all in ((False,True),(True,False)):
            bad={p:dict(cq.DEFAULT,resume_paused=True,enabled=enabled,stop_all=stop_all) for p in cq.PLATFORMS}
            with self.assertRaises(ValueError):cq.Quotas.validate(bad)
        good={p:dict(cq.DEFAULT,resume_paused=True,enabled=True,stop_all=True) for p in cq.PLATFORMS}
        self.assertIs(cq.Quotas.validate(good)['claude']['resume_paused'],True)

    def test_A8_external_desktop_has_no_resume_and_partial_is_not_failed(self):
        external=lambda:{'enabled':True,'platforms':[
            {'provider':'codex','covered':True,'discovery_complete':True,'errors':[],'sessions':[{'thread':'desk-1','state':'active','cancel_sent':True,'verified':True}]},
            {'provider':'claude','covered':True,'discovery_complete':True,'sessions':[]}]}
        protection=self.protect(external=external)
        self.task()
        result=protection.pause(low_payload('codex',observed=self.clock.now,auto=False))
        self.assertEqual(result['coverage_status'],'partial')
        self.assertFalse(result['all_local_sessions_stopped'])
        self.assertEqual(result['summary']['verified'],1)
        self.assertFalse(any('resume' in str(x).lower() for p in result['platforms'] if p['provider']=='codex' for x in p['sessions']))
        self.assertFalse(protection.snapshot()['codex']['external_resume_supported'])
        def refused():raise RuntimeError('ipc refused')
        with patch.object(self.center,'list',return_value=[]):
            failing=self.protect(external=refused)
            self.assertEqual(failing.pause(low_payload('codex',observed=self.clock.now,auto=False))['coverage_status'],'failed')
        quiet=self.protect(external=lambda:{'platforms':[{'provider':'codex','covered':True,'discovery_complete':True,'sessions':[]},
                                                        {'provider':'claude','covered':True,'discovery_complete':True,'sessions':[]}]})
        with patch.object(self.center,'list',return_value=[]):
            idle=quiet.pause(low_payload('codex',observed=self.clock.now,auto=False))
        self.assertEqual(idle['coverage_status'],'idle')
        self.assertTrue(idle['all_local_sessions_stopped'])


class C_EdgeTests(QuotaCase):
    def test_C1_claude_success_before_claim_then_unknown_blocks_resume(self):
        claude_task=self.task(root=self.root2,platform='claude')
        codex_task=self.task()
        t0=self.clock.now
        self.pause_codex()
        self.put(claude_task,status='stopped');self.put(codex_task,status='stopped')
        self.clock.tick(60);now=self.clock.now
        stale={**healthy(now),'claude':state('acct-B','ok',t0-5,[window(remaining=90)])}
        self.protection.reconcile(stale,prefs(claude_enabled=True))
        self.assertEqual(self.children(),[])  # a success from before the claim is not fresh
        unknown={**healthy(now),'claude':state(None,'ok',now,[window(remaining=90)])}
        self.protection.reconcile(unknown,prefs(claude_enabled=True))
        self.assertEqual(self.children(),[])
        self.protection.reconcile(healthy(now),prefs(claude_enabled=True))
        self.assertEqual(sorted(c['parent'] for c in self.children()),sorted([claude_task,codex_task]))

    def test_C1_reset_change_alone_does_not_block_resume(self):
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now,resets=9999),prefs())
        self.assertEqual([c['parent'] for c in self.children()],[tid])

    def test_C1_disabled_unrelated_platform_never_blocks(self):
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60);now=self.clock.now
        broken={**healthy(now),'claude':state(None,'error',now,[])}
        self.protection.reconcile(broken,prefs(claude_enabled=False))
        self.assertEqual([c['parent'] for c in self.children()],[tid])

    def test_C2_repeat_pause_reuses_cycle_merges_blockers_and_never_recontinues(self):
        tid=self.task()
        self.pause_codex()
        cycle_id=self.journal()['cycles'][0]['id']
        self.put(tid,status='stopped')
        self.clock.tick(30)
        self.pause_codex()  # same low window again, 30 seconds later
        cycles=self.journal()['cycles']
        self.assertEqual([c['id'] for c in cycles],[cycle_id])
        self.assertEqual(len(cycles[0]['targets']),1)
        self.assertEqual(cycles[0]['blockers'][0]['observed_at'],self.clock.now)
        self.protection.pause(low_payload('claude',observed=self.clock.now))  # Claude goes low later
        cycles=self.journal()['cycles']
        self.assertEqual([c['id'] for c in cycles],[cycle_id]);self.assertEqual(len(cycles[0]['blockers']),2)
        on=prefs(claude_enabled=True,resume_claude=True)
        self.clock.tick(30)
        self.protection.reconcile(healthy(self.clock.now,claude=1),on)
        self.assertEqual(self.children(),[])  # Codex recovered, Claude still low
        self.clock.tick(30)
        self.protection.reconcile(healthy(self.clock.now),on)
        self.assertEqual([c['parent'] for c in self.children()],[tid])
        self.protection.reconcile(healthy(self.clock.now+60),on)
        self.assertEqual(len(self.children(tid)),1)

    def test_C3_manual_revoke_between_read_and_commit_refuses_dispatch_for_centre_and_group(self):
        tid=self.task()
        job=self.queued(self.alpha,'work')
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60);now=self.clock.now
        self.center._before_commit=lambda:self.center._revoke_claim(tid)
        self.groups._before_commit=lambda db:self.groups._revoke_member_claims(db,self.alpha)
        self.protection.reconcile(healthy(now),prefs(claude_enabled=True))
        self.assertEqual(self.children(),[])
        self.assertEqual(self.job(job)['status'],'stopped')
        self.assertEqual(self.qp(job)['state'],'revoked')
        self.assertEqual({t['status'] for t in self.targets()},{'revoked'})

    def test_C4_persisted_continuation_without_worker_is_uncertain_not_redispatched(self):
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60);now=self.clock.now
        def crash(child,bundle):raise SystemExit('process ended after the continuation was persisted')
        self.center._spawn=crash
        with self.assertRaises(SystemExit):self.protection.reconcile(healthy(now),prefs())
        persisted=self.children(tid)
        self.assertEqual(len(persisted),1);self.assertIsNone(persisted[0].get('worker_pid'))
        self.assertEqual(self.center.quota_claim(tid)['state'],'consumed')
        self.center._spawn=self.spawn
        self.protection.reconcile(healthy(now),prefs())
        self.protection.reconcile(healthy(now),prefs())
        self.assertEqual(self.spawned,[])
        self.assertEqual(len(self.children(tid)),1)
        self.assertEqual(self.target(tid)['status'],'uncertain')
        self.assertEqual(self.children(tid)[0]['status'],'uncertain')

    def test_C5_resumed_queued_job_claim_is_consumed_and_new_low_event_uses_new_claim(self):
        job=self.queued(self.alpha,'work')
        self.pause_codex()
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        first_claim=self.target(job)['claim_id']
        self.assertEqual(self.target(job)['status'],'resumed')
        self.pause_codex()  # restored job is still queued when the next low event arrives
        second_claim=[t for t in self.targets() if t['id']==job and t['status']=='paused'][0]['claim_id']
        self.assertNotEqual(first_claim,second_claim)
        self.assertEqual(self.job(job)['status'],'stopped')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.job(job)['status'],'queued')
        self.assertEqual(self.qp(job)['claim_id'],second_claim)
        restarted=self.restart()
        count=self.job_count()
        restarted.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.job_count(),count)
        self.assertEqual(self.queued_count(self.alpha),1)
        first_cycle=next(t for c in self.journal()['cycles'] for t in c['targets'] if t['claim_id']==first_claim)
        cycle_of_first=next(c['id'] for c in self.journal()['cycles'] if first_cycle in c['targets'])
        replay=restarted.groups.resume_quota(job,{'claim_id':first_claim,'cycle_id':cycle_of_first})
        self.assertEqual(replay['status'],'attention')  # the consumed first claim cannot be replayed
        self.assertEqual(self.qp(job)['claim_id'],second_claim)

    def test_C6_new_member_queue_waits_until_it_finishes(self):
        job=self.queued(self.alpha,'work')
        self.pause_codex()
        self.clock.tick(60)
        newer=self.queued(self.alpha,'newer instruction')  # a new unclaimed queued job for the member
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.job(job)['status'],'stopped')
        self.assertEqual((self.target(job)['status'],self.target(job)['reason']),('paused','member_busy'))
        self.set_job(newer,status='done')
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.job(job)['status'],'queued')

    def test_C6_finished_group_parent_is_refused(self):
        job=self.queued(self.alpha,'work')
        self.pause_codex()
        self.set_job(job,status='done')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.job(job)['status'],'done')
        self.assertEqual((self.target(job)['status'],self.target(job)['reason']),('attention','not_stopped'))

    def test_C6_replaced_group_session_refuses_continuation(self):
        job=self.queued(self.alpha,'work')
        self.pause_codex()
        self.clock.tick(60)
        self.set_member(self.alpha,session='replacement-native-session')
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.job(job)['status'],'stopped')
        self.assertEqual(self.target(job)['reason'],'fingerprint_changed')

    def test_C7_journal_and_task_claims_must_match_reverse_never_resumes_and_corruption_is_safe(self):
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60);now=self.clock.now
        (self.center.path(tid).parent/'quota-claim.json').unlink()
        self.protection.reconcile(healthy(now),prefs())
        self.assertEqual((self.target(tid)['status'],self.target(tid)['reason']),('attention','ledger_mismatch'))
        self.assertEqual(self.children(),[])
        orphan=self.task(root=self.root2,platform='claude')
        self.center._write_claim(orphan,{'claim_id':str(uuid.uuid4()),'cycle_id':str(uuid.uuid4()),'state':'pending','fingerprint':{}})
        self.put(orphan,status='stopped')
        self.protection.reconcile(healthy(now),prefs(claude_enabled=True))
        self.assertEqual(self.children(orphan),[])  # a claim the journal does not know is never resumed
        (self.state/'quota-pauses.json').write_text('{not json')
        self.assertEqual(self.protection.snapshot()['codex']['status'],'attention')
        self.assertEqual(self.protection.snapshot()['claude']['status'],'attention')
        quotas=cq.Quotas(self.state,protection=self.protection,clock=self.clock,account_readers={'codex':lambda:None,'claude':lambda:None})
        self.assertEqual(quotas.snapshot()['platforms']['codex']['protection']['status'],'attention')
        self.assertIsNone(self.protection.reconcile(healthy(now),prefs()))
        self.assertEqual(self.children(),[])  # no continuation from a broken ledger
        self.assertEqual(self.spawned,[])


class ExtraTests(QuotaCase):
    def test_E2E_quotas_refresh_pauses_then_resumes_through_real_protection(self):
        readings={'value':[window(remaining=1)]}
        quotas=cq.Quotas(self.state,readers={'codex':lambda:readings['value']},clock=self.clock,notifier=lambda p:True,
                         account_readers={'codex':lambda:'acct-A','claude':lambda:'acct-B'},protection=self.protection)
        quotas.settings(prefs(resume_codex=True))
        tid=self.task()
        quotas.refresh('codex')  # low reading: Quotas hands its blockers to the real Protection
        self.assertEqual(self.target(tid)['status'],'paused')
        self.assertEqual(self.center.quota_claim(tid)['state'],'pending')
        self.put(tid,status='stopped')
        self.clock.tick(60)
        readings['value']=[window(remaining=60)]
        quotas.refresh('codex')  # fresh high reading after the pause: owned continuation dispatched
        self.assertEqual([c['parent'] for c in self.children()],[tid])
        self.assertEqual(self.target(tid)['status'],'resumed')
        self.assertEqual(quotas.snapshot()['platforms']['codex']['protection']['resumed_count'],1)

    def test_A6_task_stopped_before_launch_is_redispatched_fresh_not_guessed(self):
        tid=self.task(status='starting')  # no pid, no session: the model never started
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        children=self.children(tid)
        self.assertEqual(len(children),1)
        self.assertIsNone(children[0]['session_id'])
        self.assertEqual(children[0]['goal'],'finish module')  # no continuation note: nothing was started

    def test_C7_corrupt_ledger_still_stops_managed_work_but_writes_no_claims(self):
        tid=self.task()
        (self.state/'quota-pauses.json').write_text('{not json')
        result=self.protection.pause(low_payload('codex',observed=self.clock.now))
        self.assertIsNone(self.center.quota_claim(tid))
        self.assertTrue((self.center.path(tid).parent/'stop').exists())  # still stopped (D11)
        self.assertNotEqual(result['coverage_status'],'idle')


class R_RuntimeTests(QuotaCase):
    def test_R1_zcode_centre_task_is_attention_never_redispatched(self):
        tid=self.task(platform='zcode')
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.children(),[])
        self.assertEqual((self.target(tid)['status'],self.target(tid)['reason']),('attention','zcode_unsupported'))

    def test_R2_queued_continuation_refuses_when_session_changes_before_worker(self):
        job=self.queued(self.alpha,'queued work')
        self.pause_codex()
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(self.job(job)['status'],'queued')
        self.set_member(self.alpha,session='replaced-before-worker')
        with patch.object(group_chat,'run_codex') as run:
            group_chat.worker(str(self.state),self.alpha)
        run.assert_not_called()
        self.assertEqual(self.job(job)['status'],'attention')

    def test_R2_control_unchanged_continuation_runs_once_with_original_text(self):
        job=self.queued(self.alpha,'queued work')
        self.pause_codex()
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        with patch.object(group_chat,'run_codex',return_value=('done','ok')) as run:
            group_chat.worker(str(self.state),self.alpha)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[2]['text'],'queued work')
        self.assertEqual(self.job(job)['status'],'done')

    def test_R2_session_created_by_the_paused_run_still_continues(self):
        running=self.queued(self.alpha,'first ever job')
        self.set_job(running,status='running')  # the member had no native session when the job was captured
        self.pause_codex()
        self.assertIsNone(self.qp(running)['fingerprint']['session'])
        self.set_member(self.alpha,session='session-made-by-this-run');self.set_job(running,status='stopped')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        continuation=str(uuid.uuid5(uuid.NAMESPACE_URL,'context-gate-quota-resume:'+self.target(running)['claim_id']))
        with patch.object(group_chat,'run_codex',return_value=('done','ok')) as run:
            group_chat.worker(str(self.state),self.alpha)
        run.assert_called_once()
        self.assertEqual(self.job(continuation)['status'],'done')

    def test_C4_child_already_taken_over_by_its_worker_is_not_relabelled(self):
        parent=self.task()
        self.pause_codex();self.put(parent,status='stopped')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs())
        child=self.children(parent)[0]['task_id']
        self.put(child,status='running',worker_pid=None)  # crash before the pid was recorded, worker already running
        claim={'claim_id':self.target(parent)['claim_id'],'cycle_id':self.journal()['cycles'][0]['id']}
        self.assertEqual(self.center.resume_quota(parent,claim),{'status':'resumed','resume_ref':child})
        self.assertEqual(json.loads(self.center.path(child).read_text())['status'],'running')
        self.assertEqual(len(self.spawned),1)

    def test_R2_continuation_text_references_the_original_job(self):
        running=self.queued(self.beta,'original running text')
        self.run_job(running,self.beta,session='beta-session')
        self.pause_codex()
        self.set_job(running,status='stopped')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs(claude_enabled=True))
        continuation=str(uuid.uuid5(uuid.NAMESPACE_URL,'context-gate-quota-resume:'+self.target(running)['claim_id']))
        with self.groups.connect() as db:
            text=group_chat.quota_text(db,dict(self.job(continuation)))
        self.assertTrue(text.startswith(QUOTA_CONTINUE));self.assertIn('original running text',text)

    def test_R3_group_resume_holds_submission_lock_during_check_and_flip(self):
        job=self.queued(self.alpha,'work')
        self.pause_codex()
        self.clock.tick(60)
        lock_path=self.state/'submission.lock';probes=[]
        real_list=self.center.list
        self.center.list=lambda:(probes.append(('check',lock_held(lock_path))),real_list())[1]
        self.groups.launch=True
        self.groups.start_worker=lambda member:probes.append(('start',lock_held(lock_path)))
        self.protection.reconcile(healthy(self.clock.now),prefs())
        self.assertEqual(probes,[('check',True),('start',True)])
        self.assertEqual(self.job(job)['status'],'queued')

    def test_R4_codex_trigger_checks_claude_member_only_while_claude_enabled(self):
        job=self.queued(self.beta,'claude work')
        self.run_job(job,self.beta,session='beta-session')
        self.pause_codex()
        self.set_job(job,status='stopped')
        self.clock.tick(60);now=self.clock.now
        low_claude=healthy(now,claude=1)
        self.protection.reconcile(low_claude,prefs(claude_enabled=True))
        self.assertEqual(self.job_count(self.beta),1)
        self.assertEqual(self.target(job)['status'],'paused')
        self.protection.reconcile(low_claude,prefs(claude_enabled=False))
        self.assertEqual(self.job_count(self.beta),2)
        self.assertEqual(self.target(job)['status'],'resumed')

    def test_R5_recovery_read_before_a_later_blocker_does_not_count(self):
        tid=self.task()
        t0=self.clock.now
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(20)
        self.protection.pause(low_payload('claude',observed=self.clock.now))  # Claude appended at t0+20
        self.clock.tick(10)
        on=prefs(claude_enabled=True,resume_claude=True)
        before_append={'codex':state('acct-A','ok',t0+30,[window(remaining=60)]),'claude':state('acct-B','ok',t0+10,[window(remaining=80)])}
        self.protection.reconcile(before_append,on)
        self.assertEqual(self.children(),[])
        reasons=self.protection.snapshot(before_append,on)['codex']['blocked_by']
        self.assertIn({'platform':'claude','account':'acct-B','reason':'not_checked_after_pause'},reasons)
        after_append={'codex':state('acct-A','ok',t0+30,[window(remaining=60)]),'claude':state('acct-B','ok',t0+40,[window(remaining=80)])}
        self.protection.reconcile(after_append,on)
        self.assertEqual([c['parent'] for c in self.children()],[tid])

    def test_R6_switching_resume_off_then_on_never_revives_old_targets(self):
        tid=self.task()
        quotas=cq.Quotas(self.state,protection=self.protection,clock=self.clock,account_readers={'codex':lambda:None,'claude':lambda:None})
        quotas.settings(prefs(resume_codex=True))
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60)
        quotas.settings(prefs(resume_codex=False))
        self.assertEqual((self.target(tid)['status'],self.target(tid)['reason']),('attention','resume_disabled'))
        quotas.settings(prefs(resume_codex=True))
        self.protection.reconcile(healthy(self.clock.now),prefs(resume_codex=True))
        self.assertEqual(self.children(),[])

    def test_R6_live_switch_off_blocks_without_dispatch_until_it_is_revoked(self):
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60)
        self.protection.reconcile(healthy(self.clock.now),prefs(resume_codex=False))
        self.assertEqual(self.children(),[])
        self.assertEqual(self.target(tid)['status'],'paused')
        reasons=self.protection.snapshot(healthy(self.clock.now),prefs(resume_codex=False))['codex']['blocked_by']
        self.assertEqual(reasons,[{'platform':'codex','account':'acct-A','reason':'resume_disabled'}])

    def test_R7_snapshot_is_read_only_and_creates_no_files(self):
        missing=Path(self.temp.name)/'never-created'
        self.assertEqual(cqs.Protection(missing,self.center,self.groups,None,clock=self.clock).snapshot()['codex']['status'],'idle')
        self.assertFalse(missing.exists())
        tid=self.task()
        self.pause_codex()
        self.put(tid,status='stopped')
        path=self.state/'quota-pauses.json'
        before=(path.stat().st_mtime_ns,path.read_bytes())
        for _ in range(3):self.protection.snapshot(healthy(self.clock.now),prefs())
        self.assertEqual(before,(path.stat().st_mtime_ns,path.read_bytes()))

    def test_R8_start_failure_is_uncertain_and_never_executable_or_retried(self):
        tid=self.task()
        job=self.queued(self.alpha,'work')
        self.pause_codex()
        self.put(tid,status='stopped')
        self.clock.tick(60);now=self.clock.now
        self.center._spawn=Mock(side_effect=RuntimeError('spawn failed'))
        self.groups.launch=True
        self.groups.start_worker=Mock(side_effect=RuntimeError('start failed'))
        self.protection.reconcile(healthy(now),prefs(claude_enabled=True))
        self.assertEqual(self.job(job)['status'],'uncertain')
        self.assertEqual(self.qp(job)['state'],'uncertain')
        self.assertEqual(self.target(job)['status'],'uncertain')
        self.assertEqual(self.target(tid)['status'],'uncertain')
        self.assertEqual(self.children(tid)[0]['status'],'uncertain')
        self.center._spawn.reset_mock();self.groups.start_worker.reset_mock()
        self.protection.reconcile(healthy(now),prefs(claude_enabled=True))
        self.center._spawn.assert_not_called();self.groups.start_worker.assert_not_called()


class S_BoundaryTests(QuotaCase):
    def test_S1_quotas_calls_pause_reconcile_and_external_stop_without_its_lock(self):
        seen=[];holder={}
        idle={'status':'idle','paused_count':0,'resumed_count':0,'attention_count':0,'blocked_by':[],'external_resume_supported':False}
        class Recorder:
            def pause(self_,payload):
                seen.append(('pause',lock_free_elsewhere(holder['q'].lock)));return {'coverage_status':'partial','platforms':[]}
            def snapshot(self_,states=None,prefs=None):return {'codex':dict(idle),'claude':dict(idle)}
            def reconcile(self_,states,prefs,live=None):seen.append(('reconcile',lock_free_elsewhere(holder['q'].lock)))
        low=[window(remaining=1)]
        q=cq.Quotas(self.state,readers={'codex':lambda:low},clock=self.clock,notifier=lambda p:True,
                    account_readers={'codex':lambda:'acct-A','claude':lambda:'acct-B'},protection=Recorder())
        holder['q']=q
        q.settings(prefs(resume_codex=False))
        q.refresh('codex')
        self.assertIn(('pause',True),seen);self.assertIn(('reconcile',True),seen)
        stops=[];second=self.state/'legacy-stop-path';second.mkdir()
        holder2={}
        q2=cq.Quotas(second,readers={'codex':lambda:low},clock=self.clock,notifier=lambda p:True,
                     account_readers={'codex':lambda:'acct-A','claude':lambda:'acct-B'},
                     stop_handler=lambda p:stops.append(lock_free_elsewhere(holder2['q'].lock)) or {'ok':False,'error':'probe'})
        holder2['q']=q2
        q2.settings(prefs(resume_codex=False))
        q2.refresh('codex')
        self.assertEqual(stops,[True])

    def test_S2_default_protection_never_calls_the_real_stop_all_local(self):
        bare=cqs.Protection(self.state,self.center,self.groups)
        with patch.object(cqs,'stop_all_local') as real:
            manual=bare.pause(low_payload('codex',observed=self.clock.now,auto=False))
            owned=bare.pause(low_payload('codex',observed=self.clock.now,auto=True))
        real.assert_not_called()
        self.assertNotEqual(manual['coverage_status'],'idle')
        self.assertNotEqual(owned['coverage_status'],'idle')

    def test_S3_settings_post_without_resume_field_is_accepted_and_saved_as_off(self):
        legacy={p:{k:v for k,v in dict(cq.DEFAULT,enabled=True,stop_all=True).items() if k!='resume_paused'} for p in cq.PLATFORMS}
        saved=cq.Quotas(self.state).settings(legacy)
        self.assertIs(saved['codex']['resume_paused'],False)
        self.assertIs(json.loads((self.state/'quota-settings.json').read_text())['codex']['resume_paused'],False)


if __name__=='__main__':unittest.main()
