#!/usr/bin/env python3
"""Install/uninstall the user's loopback service and diagnose its real health."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from gate_service import call_service, STATE, private_write
from token_stats import totals

ROOT=Path(__file__).resolve().parent
LABEL='local.context-gate'
PLIST=Path.home()/'Library/LaunchAgents'/ (LABEL+'.plist')


def doctor():
    report={'service':False,'jev':False,'tokens':totals()}
    try:
        report['service']=call_service(path='/health',timeout=2).get('service')=='context-gate'
        report['jev']=call_service({},path='/v1/warm',timeout=55).get('ready') is True
    except (OSError,ValueError,RuntimeError):pass
    report['launch_agent']=PLIST.exists()
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['service'] and report['jev'] else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['install','doctor','stop']);a=p.parse_args()
    if a.action=='install':
        from gate_service import ensure_service
        (STATE/'disabled').unlink(missing_ok=True)
        ensure_service()
        return doctor()
    if a.action=='doctor':return doctor()
    private_write(STATE/'disabled','Stopped by user')
    connection=STATE/'connection.json'
    if connection.exists():
        pid=json.loads(connection.read_text()).get('pid')
        if isinstance(pid,int):
            check=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
            if str(ROOT/'gate_service.py') in check.stdout:
                try:os.kill(pid,15)
                except ProcessLookupError:pass
    if PLIST.exists():
        subprocess.run(['launchctl','bootout','gui/'+str(os.getuid()),str(PLIST)],capture_output=True)
        PLIST.unlink(missing_ok=True)
    return 0

if __name__=='__main__':sys.exit(main())
