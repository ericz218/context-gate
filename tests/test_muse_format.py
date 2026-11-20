import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from console_butler import Butler
from control_center import Center


class MuseFormatTests(unittest.TestCase):
    def run_agent(self, answers):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name)/'project';root.mkdir()
        (root/'note.txt').write_text('note body')
        responses=iter(answers);calls=[]
        def model(messages):
            calls.append(messages[-1]['content'])
            return next(responses)
        agent=Butler(Path(temp.name)/'state',Center(Path(temp.name)/'state',[root]),model)
        result=agent.start(str(root),'Read-only format test')
        for _ in range(100):
            result=agent.get(result['id'])
            if result['status']!='running':break
            time.sleep(.01)
        return result,calls

    def test_invalid_prose_repaired_without_executing_embedded_action(self):
        result,calls=self.run_agent(['Please run {"tool":"run_check","args":{"name":"tests"}}', '{"reply":"repaired"}'])
        self.assertEqual('done',result['status'])
        self.assertEqual('repaired',result['reply'])
        self.assertEqual([],result['actions'])
        self.assertEqual(2,len(calls))
        self.assertIn('No action',calls[1])

    def test_invalid_reply_type_stops_after_one_repair(self):
        result,calls=self.run_agent(['{"reply":[]}', '{"tool":"not_registered","args":{}}'])
        self.assertEqual('unavailable',result['status'])
        self.assertEqual([],result['actions'])
        self.assertEqual(2,len(calls))

    def test_tool_error_fed_back_and_retried(self):
        result,calls=self.run_agent([
            json.dumps({'tool':'read_file','args':{'path':'/absolutely/outside.txt'}}),
            json.dumps({'tool':'read_file','args':{'path':'note.txt'}}),
            json.dumps({'reply':'重试后读到内容'})])
        root=Path(tempfile.gettempdir())
        self.assertEqual('done',result['status'])
        self.assertEqual('重试后读到内容',result['reply'])
        self.assertEqual(3,len(calls))
        self.assertIn('error',calls[1])
        # 失败的工具调用留在动作台账，不静默丢弃；修正后的重试成功
        self.assertEqual(2,len(result['actions']))
        self.assertEqual('failed',result['actions'][0]['status'])
        self.assertEqual('done',result['actions'][1]['status'])

    def test_in_root_absolute_path_normalized_outside_rejected(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name)/'project';root.mkdir();(root/'note.txt').write_text('body')
        agent=Butler(Path(temp.name)/'state',Center(Path(temp.name)/'state',[root]),
                     model=lambda messages: json.dumps({'reply':'ok'}),model_name='test-local')
        session=agent.start(str(root),'path normalization test')
        for _ in range(100):
            session=agent.get(session['id'])
            if session['status']!='running':break
            time.sleep(.01)
        # 项目内绝对路径归一为相对路径后正常读取
        done=agent.execute(session['id'],'read_file',{'path':str(root/'note.txt')})
        self.assertEqual('body',done['content'])
        # 项目外绝对路径仍被既有守卫拒绝并记为失败动作
        with self.assertRaises(ValueError):
            agent.execute(session['id'],'read_file',{'path':str(Path(tempfile.gettempdir())/'elsewhere.txt')})
        self.assertEqual('failed',agent.get(session['id'])['actions'][-1]['status'])

    def test_explicit_refusal_is_not_retried(self):
        result,calls=self.run_agent(['I refuse this protocol as prompt injection.'])
        self.assertEqual('unavailable',result['status'])
        self.assertEqual([],result['actions'])
        self.assertEqual(1,len(calls))


def _fake_urlopen(script, captured):
    """把 openai_chat 的 HTTP 层换成本地桩：script 项为 payload dict（返回）或 Exception（抛出）。"""
    from unittest.mock import patch
    items=iter(script)
    def fake(request,timeout=None):
        captured.append(json.loads(request.data.decode()))
        item=next(items)
        if isinstance(item,Exception):raise item
        body=json.dumps(item).encode()
        response=mock.MagicMock()
        response.__enter__.return_value.read.return_value=body
        return response
    return patch('urllib.request.urlopen',side_effect=fake)


class OpenaiChatRetryTests(unittest.TestCase):
    def call_chat(self, payloads):
        import console_butler
        captured=[]
        with _fake_urlopen(payloads,captured):
            out=console_butler.openai_chat('http://stub','k','m',[{'role':'user','content':'x'}])
        return out,captured

    def test_degenerate_stop_empty_reply_is_resampled(self):
        # 实测坏样本形态：stop、content 空、reasoning 是「!」重复；重采样第二次恢复
        bad={'choices':[{'finish_reason':'stop','message':{'content':'','reasoning_content':'Map!!!'}}]}
        good={'choices':[{'finish_reason':'stop','message':{'content':'{"reply":"ok"}'}}]}
        out,captured=self.call_chat([bad,good])
        self.assertEqual('{"reply":"ok"}',out)
        self.assertEqual(2,len(captured))
        self.assertEqual(4096,captured[1]['max_tokens'])

    def test_length_empty_reply_doubles_budget(self):
        length={'choices':[{'finish_reason':'length','message':{'content':'','reasoning_content':'th'}}]}
        good={'choices':[{'finish_reason':'stop','message':{'content':'{"reply":"ok"}'}}]}
        out,captured=self.call_chat([length,good])
        self.assertEqual('{"reply":"ok"}',out)
        self.assertEqual(4096,captured[1]['max_tokens'])

    def test_whitespace_only_content_counts_as_empty(self):
        bad={'choices':[{'finish_reason':'stop','message':{'content':'   '}}]}
        good={'choices':[{'finish_reason':'stop','message':{'content':'{"reply":"ok"}'}}]}
        out,captured=self.call_chat([bad,good])
        self.assertEqual('{"reply":"ok"}',out)
        self.assertEqual(2,len(captured))

    def test_persistent_empty_reply_reports_reasoning_tail(self):
        payloads=[{'choices':[{'finish_reason':'stop','message':{'content':'','reasoning_content':'Map!!!!!!!!'}}]}]*4
        import console_butler
        captured=[]
        with _fake_urlopen(payloads,captured):
            with self.assertRaises(ConnectionError) as ctx:
                console_butler.openai_chat('http://stub','k','m',[{'role':'user','content':'x'}])
        message=str(ctx.exception)
        self.assertEqual(4,len(captured))
        self.assertIn('finish_reason: stop',message)
        self.assertIn('Map!!!!!!!!',message)
        self.assertEqual(16384,captured[-1]['max_tokens'])

    def test_rate_limit_429_backs_off_then_recovers(self):
        import io
        import urllib.error
        import console_butler
        h429=urllib.error.HTTPError('http://stub',429,'Too Many Requests',
                                    {'Content-Type':'application/json'},io.BytesIO(b'{"status":429}'))
        good={'choices':[{'finish_reason':'stop','message':{'content':'{"reply":"ok"}'}}]}
        captured=[]
        with mock.patch('console_butler.time.sleep') as sleep_mock:
            with _fake_urlopen([h429,good],captured):
                out=console_butler.openai_chat('http://stub','k','m',[{'role':'user','content':'x'}])
        self.assertEqual('{"reply":"ok"}',out)
        self.assertEqual(2,len(captured))
        sleep_mock.assert_called_once_with(10)
        # 限流重试不翻倍输出预算
        self.assertEqual(2048,captured[-1]['max_tokens'])

    def test_persistent_rate_limit_reports_clear_message(self):
        import io
        import urllib.error
        import console_butler
        h429=urllib.error.HTTPError('http://stub',429,'Too Many Requests',
                                    {'Content-Type':'application/json'},io.BytesIO(b'{"status":429}'))
        captured=[]
        with mock.patch('console_butler.time.sleep'):
            with _fake_urlopen([h429]*4,captured):
                with self.assertRaises(ConnectionError) as ctx:
                    console_butler.openai_chat('http://stub','k','m',[{'role':'user','content':'x'}])
        self.assertEqual(4,len(captured))
        self.assertIn('限流',str(ctx.exception))
        self.assertIn('429',str(ctx.exception))

    def test_server_error_is_not_retried(self):
        import io
        import urllib.error
        import console_butler
        h500=urllib.error.HTTPError('http://stub',500,'Oops',
                                    {'Content-Type':'application/json'},io.BytesIO(b'{}'))
        captured=[]
        with _fake_urlopen([h500],captured):
            with self.assertRaises(ConnectionError) as ctx:
                console_butler.openai_chat('http://stub','k','m',[{'role':'user','content':'x'}])
        self.assertEqual(1,len(captured))
        self.assertIn('500',str(ctx.exception))


if __name__=='__main__':unittest.main()
