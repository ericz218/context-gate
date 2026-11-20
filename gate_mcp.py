#!/usr/bin/env python3
"""Portable stdio MCP client bridge; every platform shares one local engine."""
import json
import sys
from gate_service import call_service

TOOL = {'name': 'context_pack', 'description':
        'Before reading broad project context, create a task-specific Context Pack. Core project memory is preserved. Each agent must pass its OWN current task and identifiers. If blocked, do not proceed with missing context. Reviewers are advisory, not evidence.',
        'inputSchema': {'type': 'object', 'additionalProperties': False,
            'required': ['root','request','memory','agent_id','session_id','task_id'],
            'properties': {
                'root': {'type':'string'}, 'request': {'type':'string'},
                'memory': {'type':'array','items':{'type':'string'},'minItems':1},
                'agent_id':{'type':'string'}, 'session_id':{'type':'string'},'task_id':{'type':'string'},
                'platform':{'type':'string','enum':['generic','zcode','claude','codex','gpt','openai','anthropic']},
                'terms':{'type':'array','items':{'type':'string'}}, 'force_gate':{'type':'boolean'}}},
        'annotations':{'readOnlyHint':True,'destructiveHint':False,'openWorldHint':True}}


def dispatch(method, params):
    if method == 'initialize':
        return {'protocolVersion':'2025-06-18','capabilities':{'tools':{}},
                'serverInfo':{'name':'context-gate','version':'2.0.0'},
                'instructions':'Use context_pack for each agent task. Pass only its task, never entire sibling histories. Read current source if the pack requests it.'}
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools':[TOOL]}
    if method == 'tools/call':
        if params.get('name') != 'context_pack':
            raise ValueError('Unknown tool')
        r=call_service(params.get('arguments',{}))
        if not r['ready_to_send']:
            return {'isError':True,'content':[{'type':'text','text':'Context blocked: ' + '\n'.join(r['risks'])}]}
        # Do not expose gate internals, candidates, numeric audits or identities to the model.
        return {'content':[{'type':'text','text':r['prompt']}]}
    raise ValueError('Unknown method')


def main():
    for line in sys.stdin:
        msg=None
        try:
            msg=json.loads(line)
            if 'id' not in msg:
                continue
            result=dispatch(msg.get('method'),msg.get('params') or {})
            response={'jsonrpc':'2.0','id':msg['id'],'result':result}
        except Exception as exc:
            if isinstance(msg,dict) and 'id' in msg:
                response={'jsonrpc':'2.0','id':msg['id'],'error':{'code':-32603,'message':'Context Gate failed: '+type(exc).__name__}}
            else:
                continue
        sys.stdout.write(json.dumps(response,ensure_ascii=False)+'\n')
        sys.stdout.flush()


if __name__ == '__main__':
    main()
