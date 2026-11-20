import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import patch

from console_schedule import Schedules
from control_center import Center


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'project';self.root.mkdir()
        self.center=Center(Path(self.temp.name)/'state',[self.root]);self.scheduler=Schedules(self.center,launch=False)
        self.body={'at':time.time()+3600,'task':{'root':str(self.root),'platform':'claude','goal':'scheduled test'}}

    def test_due_dispatch_once_and_durable_task_association(self):
        item=self.scheduler.create(self.body)
        self.scheduler.tick(item['at']-1,launch_tasks=False);self.assertEqual([],self.center.list())
        self.scheduler.tick(item['at'],launch_tasks=False);self.scheduler.tick(item['at']+1,launch_tasks=False)
        self.assertEqual(1,len(self.center.list()))
        self.assertEqual(item['id'],self.center.list()[0]['schedule_id'])
        self.assertEqual('dispatched',self.scheduler.list()[0]['status'])
        self.assertEqual(0o600,self.scheduler.path(item['id']).stat().st_mode&0o777)

    def test_simultaneous_due_claim_dispatches_only_once(self):
        from concurrent.futures import ThreadPoolExecutor
        item=self.scheduler.create(self.body)
        with patch.object(self.center,'create',wraps=self.center.create) as create:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(self.scheduler.tick,item['at'],False) for _ in range(2)]
                for future in futures:future.result()
            create.assert_called_once()
        self.assertEqual(1,len(self.center.list()))

    def test_cancel_missed_and_invalid_booking_never_create_task(self):
        item=self.scheduler.create(self.body);self.scheduler.cancel({'id':item['id']})
        self.scheduler.tick(item['at'],launch_tasks=False)
        other=self.scheduler.create(self.body);self.scheduler.tick(other['at']+601,launch_tasks=False)
        self.assertEqual({'cancelled','missed'},{x['status'] for x in self.scheduler.list()})
        self.assertEqual([],self.center.list())
        for at in (True,'tomorrow',float('nan'),time.time()-1):
            with self.assertRaises(ValueError):self.scheduler.create({**self.body,'at':at})

    def test_crash_after_task_creation_recover_without_replay(self):
        item=self.scheduler.create(self.body);create=self.center.create
        def interrupted(*args,**kwargs):create(*args,**kwargs);raise SystemExit('simulated process death')
        with patch.object(self.center,'create',side_effect=interrupted) as call:
            with self.assertRaises(SystemExit):self.scheduler.tick(item['at'],launch_tasks=False)
            call.assert_called_once()
        restarted=Schedules(self.center,launch=False);restarted.recover();restarted.tick(item['at'],launch_tasks=False)
        self.assertEqual(1,len(self.center.list()));self.assertEqual('dispatched',restarted.list()[0]['status'])

    def test_crash_before_task_creation_and_project_busy_do_not_retry(self):
        item=self.scheduler.create(self.body)
        with patch.object(self.center,'create',side_effect=SystemExit('process death')):
            with self.assertRaises(SystemExit):self.scheduler.tick(item['at'],launch_tasks=False)
        self.scheduler.recover();self.scheduler.tick(item['at'],launch_tasks=False)
        self.assertEqual('uncertain',self.scheduler.list()[0]['status']);self.assertEqual([],self.center.list())
        self.center.create(self.body['task'],launch=False)
        busy=self.scheduler.create(self.body);self.scheduler.tick(busy['at'],launch_tasks=False)
        self.assertEqual('failed',next(x for x in self.scheduler.list() if x['id']==busy['id'])['status'])
        self.assertEqual(1,len(self.center.list()))


if __name__=='__main__':unittest.main()
