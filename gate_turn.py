"""Per-model-call integration. Replace only authenticated, explicitly managed context.
Conversation, reasoning items, images and tool call/result objects are untouched.
"""
import copy
import hashlib
import hmac
import json
from pathlib import Path
from gate_service import STATE, call_service
from context_gate import estimate

PREFIX = '[CONTEXT_GATE_MANAGED '
END = '\n[/CONTEXT_GATE_MANAGED]'


def scope(job):
    return json.dumps({k: job[k] for k in ('root','agent_id','session_id')}, sort_keys=True, separators=(',',':'))


def key():
    return (STATE/'access-token').read_bytes().strip()


def managed_context(text, job, secret=None):
    secret = key() if secret is None else secret
    signature = hmac.new(secret, (scope(job)+'\n'+text).encode(), hashlib.sha256).hexdigest()
    return PREFIX+signature+']\n'+text+END


def owned(text, job, secret):
    if not isinstance(text,str) or not text.startswith(PREFIX) or not text.endswith(END):
        return False
    header, sep, body=text.partition(']\n')
    if not sep:
        return False
    text_body=body[:-len(END)]
    signature=header[len(PREFIX):]
    expected=hmac.new(secret,(scope(job)+'\n'+text_body).encode(),hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature,expected)


def prepare_turn(payload, protocol, job, packer=call_service, secret=None):
    """Call BEFORE EACH model request, including calls after tool completion."""
    if not isinstance(payload,dict):raise ValueError('Payload must be a JSON object')
    if protocol not in ('responses','chat','anthropic'):
        raise ValueError('Unsupported protocol')
    if protocol == 'responses' and (payload.get('previous_response_id') or payload.get('conversation')):
        raise ValueError('服务器保留的历史不能由本地裁剪；请使用完整显式 input 的无状态模式')
    secret=key() if secret is None else secret
    result=packer(job)
    if not result['ready_to_send']:
        raise RuntimeError('Context blocked; model call must not proceed')
    outgoing=copy.deepcopy(payload)
    field='input' if protocol == 'responses' else 'messages'
    items=outgoing.get(field)
    if isinstance(items,str) and protocol == 'responses':
        items=[{'role':'user','content':items}]
    if not isinstance(items,list):
        raise ValueError('Expected explicit message/item list')
    removed=0
    for item in items:
        if not isinstance(item,dict) or item.get('role') != 'user':
            continue
        content=item.get('content')
        if owned(content,job,secret):
            removed += estimate(content)
            item['content']='[Previous managed project context replaced by current pack.]'
        elif isinstance(content,list):
            retained=[]
            for block in content:
                if (isinstance(block,dict) and block.get('type') in ('text','input_text')
                        and owned(block.get('text'),job,secret)):
                    removed += estimate(block['text'])
                else:
                    retained.append(block)
            item['content']=retained or [{'type':'input_text' if protocol=='responses' else 'text',
                                         'text':'[Previous managed project context replaced by current pack.]'}]
    block=managed_context(result['prompt'],job,secret)
    block_type='input_text' if protocol=='responses' else 'text'
    # Anthropic native clients can finish with a mid-conversation system directive.
    # Keep it last: appending a user after it violates the provider's ordering rule.
    insertion=len(items)
    if protocol=='anthropic':
        while insertion and isinstance(items[insertion-1],dict) and items[insertion-1].get('role')=='system':
            insertion-=1
    previous=items[insertion-1] if insertion else None
    if isinstance(previous,dict) and previous.get('role')=='user':
        c=previous.get('content')
        if isinstance(c,str):previous['content']=[{'type':block_type,'text':c},{'type':block_type,'text':block}]
        elif isinstance(c,list):c.append({'type':block_type,'text':block})
        else:raise ValueError('Unsupported final user content')
    else:
        items.insert(insertion,{'role':'user','content':[{'type':block_type,'text':block}]})
    outgoing[field]=items
    return outgoing, {'managed_tokens_removed_estimated':removed,
                      'request_before_tokens_estimated':estimate(json.dumps(payload,ensure_ascii=False)),
                      'request_after_tokens_estimated':estimate(json.dumps(outgoing,ensure_ascii=False)),
                      'gate_metrics':result['metrics'], 'accounting_id':result.get('accounting_id')}
