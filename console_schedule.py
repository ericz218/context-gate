"""Durable one-shot bookings. Claim before dispatch; uncertain jobs never replay."""
import argparse
import fcntl
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid

from control_center import Center,PROJECT,write_json,audit
from console_search import public


class Schedules:
    def __init__(self,center,launch=True):
        self.center=center;self.launch=launch;self.folder=center.state/'schedules'
        self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)

    def path(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9-]{36}',identifier):raise ValueError('预约编号无效')
        return self.folder/(identifier+'.json')

    def list(self):
        items=[]
        for path in self.folder.glob('*.json'):
            try:
                item=json.loads(path.read_text())
                if item.get('task_id'):
                    try:item['task_status']=self.center.get(item['task_id'])['status']
                    except (ValueError,OSError):item['task_status']='unavailable'
                items.append(item)
            except (ValueError,OSError,KeyError):continue
        return sorted(items,key=lambda x:x['at'])

    def create(self,body):
        at=body.get('at');now=time.time()
        if type(at) not in (int,float) or not math.isfinite(at) or not now<at<=now+366*86400:raise ValueError('请选择未来一年内的预约时间')
        request=self.center.validate_request(body.get('task'))
        identifier=str(uuid.uuid4());item={'id':identifier,'at':at,'created_at':now,'status':'waiting','task':request}
        with (self.folder/'data.lock').open('a') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX);write_json(self.path(identifier),item)
        audit(self.center.state,'schedule_task',{'id':identifier,**request},schedule_id=identifier,at=at)
        self.start();return item

    def cancel(self,body):
        path=self.path(body.get('id'))
        with (self.folder/'data.lock').open('a') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX);item=json.loads(path.read_text())
            if item['status']!='waiting':raise ValueError('预约已派发或结束；正在执行的任务请使用停止按钮')
            item['status']='cancelled';write_json(path,item)
        audit(self.center.state,'cancel_schedule',{'id':item['id'],**item['task']},schedule_id=item['id'])
        return item

    def start(self):
        if not self.launch or not any(x['status'] in ('waiting','dispatching') for x in self.list()):return
        with (self.folder/'worker.lock').open('a') as guard:
            try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return
        with (self.folder/'worker.log').open('ab') as log:
            proc=subprocess.Popen([sys.executable,str(PROJECT/'console_schedule.py'),'--state',str(self.center.state)],
                                  stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)
        threading.Thread(target=proc.wait,daemon=True).start()

    def recover(self):
        # Called only by the owner of worker.lock. A durable dispatch claim is never retried.
        tasks=self.center.list()
        with (self.folder/'data.lock').open('a') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX)
            for item in self.list():
                if item['status']!='dispatching':continue
                found=[x for x in tasks if x.get('schedule_id')==item['id']]
                if len(found)==1:item.update(status='dispatched',task_id=found[0]['task_id'])
                else:item.update(status='uncertain',error='派发进程中断，未自动重派；请核对任务记录后再处理')
                write_json(self.path(item['id']),item)

    def tick(self,now=None,launch_tasks=True):
        now=time.time() if now is None else now
        for candidate in self.list():
            if candidate['status']!='waiting' or candidate['at']>now:continue
            path=self.path(candidate['id'])
            with (self.folder/'data.lock').open('a') as guard:
                fcntl.flock(guard,fcntl.LOCK_EX);item=json.loads(path.read_text())
                if item['status']!='waiting':continue
                if now-item['at']>600:
                    item.update(status='missed',error='超过预约时间10分钟，未派发；需要时可手动派发')
                    write_json(path,item);continue
                item['status']='dispatching';write_json(path,item)
            try:
                task=self.center.create(item['task'],launch=launch_tasks,schedule_id=item['id'])
                item.update(status='dispatched',task_id=task['task_id'])
            except Exception as error:item.update(status='failed',error=public(str(error)) if isinstance(error,ValueError) else type(error).__name__)
            write_json(path,item)
            audit(self.center.state,'schedule_dispatch',{'id':item['id'],**item['task']},schedule_id=item['id'],status=item['status'])


def run(state):
    os.umask(0o077);scheduler=Schedules(Center(state),launch=False)
    with (scheduler.folder/'worker.lock').open('a') as guard:
        try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        scheduler.recover()
        while True:
            scheduler.tick()
            with (scheduler.folder/'data.lock').open('a') as data_guard:
                fcntl.flock(data_guard,fcntl.LOCK_EX)
                if not any(x['status']=='waiting' for x in scheduler.list()):
                    # Release ownership before a creator can publish another booking.
                    fcntl.flock(guard,fcntl.LOCK_UN);return
            time.sleep(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state',required=True)
    run(parser.parse_args().state)
