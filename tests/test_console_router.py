import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from console_router import RouterManager


class RouterAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.connection = Path(self.tmp.name) / 'console-bridge.json'
        self.router = RouterManager(self.connection)

    def publish(self, **values):
        self.connection.write_text(json.dumps({'version': 1, 'port': 18000, 'token': 'a' * 48, **values}))
        self.connection.chmod(0o600)

    def test_disconnected_snapshot_is_explicit(self):
        data = self.router.snapshot()
        self.assertFalse(data['connected'])
        self.assertNotIn('token', data)
        self.assertNotIn('result', data)

    def test_snapshot_forwards_valid_filters_and_rejects_invalid_values(self):
        with patch.object(self.router, 'call', return_value={'filters': {'period': 'all'}}) as call:
            data = self.router.snapshot('all', 'AMD TokenFactory 2')
        self.assertTrue(data['connected'])
        call.assert_called_once_with('snapshot', {'period': 'all', 'provider': 'AMD TokenFactory 2'})
        with patch.object(self.router, 'call') as call:
            for period, provider in (('year', 'all'), ('today;DROP', 'all'), ('today', ''), ('today', 'x' * 201), ('today', '供' * 68), ('today', None)):
                with self.assertRaises(ValueError):
                    self.router.snapshot(period, provider)
            call.assert_not_called()
        with patch.object(self.router, 'call', return_value={}) as call:
            self.router.snapshot()
        call.assert_called_once_with('snapshot', {'period': 'all', 'provider': None})

    def test_connection_rejects_permissions_symlink_and_bad_port(self):
        self.publish()
        self.connection.chmod(0o644)
        with self.assertRaises(ValueError):
            self.router._connection()
        self.connection.unlink()
        target = Path(self.tmp.name) / 'other'
        target.write_text('{}')
        self.connection.symlink_to(target)
        with self.assertRaises(OSError):
            self.router._connection()
        self.connection.unlink()
        for port in ('18000', True, 0, 65536):
            self.publish(port=port)
            with self.assertRaises(ValueError):
                self.router._connection()

    def test_unknown_commands_and_nonobject_args_fail_before_connection(self):
        for command in ('../secret', 'serve', 'execute', None, [], {}):
            with self.assertRaises(ValueError):
                self.router.call(command)
        with self.assertRaises(ValueError):
            self.router.call('snapshot', ['invalid'])

    def test_loopback_authenticated_roundtrip_and_error(self):
        recorded = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                recorded.append((self.path, self.headers['Authorization'], json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                body = {'result': {'ok': True}} if recorded[-1][2]['command'] == 'snapshot' else {'error': 'Invalid id'}
                payload = json.dumps(body).encode()
                self.send_response(200 if 'result' in body else 400)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.publish(port=server.server_port)
        self.assertEqual({'ok': True}, self.router.call('snapshot'))
        self.assertEqual('/call', recorded[0][0])
        self.assertEqual('Bearer ' + 'a' * 48, recorded[0][1])
        self.assertEqual({}, recorded[0][2]['args'])
        with self.assertRaisesRegex(ValueError, 'Invalid id'):
            self.router.call('delete_model', {'id': -1})

    def test_connection_refuses_overlong_file_and_token(self):
        self.publish(token='a' * 129)
        with self.assertRaises(ValueError):
            self.router._connection()
        self.connection.write_text(' ' * 4097)
        with self.assertRaises(ValueError):
            self.router._connection()

    def test_nonobject_connection_and_test_key_args_are_rejected(self):
        for value in ([], None, 42, 'text'):
            self.connection.write_text(json.dumps(value));self.connection.chmod(0o600)
            self.assertFalse(self.router.snapshot()['connected'])
        for value in ([], 1, 'text', None):
            with self.assertRaises(ValueError):
                self.router.action({'command':'test_keys','args':value})

    def test_redirect_never_forwards_authorization(self):
        import urllib.request
        import urllib.error
        seen=[]
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                seen.append(self.path)
                if self.path=='/start':
                    self.send_response(302);self.send_header('Location','/target')
                else:self.send_response(200)
                self.send_header('Content-Length','0');self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Redirect)
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/start',
                                       headers={'Authorization':'Bearer synthetic-test'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.router.http.open(request,timeout=5)
        self.assertEqual(error.exception.code,302)
        self.assertEqual(seen,['/start'])

    def test_configured_discovery_path_does_not_resolve_request_paths(self):
        self.publish()
        result = self.router._connection()
        self.assertEqual(18000, result[0])
        self.assertEqual(48, len(result[1]))
        self.assertEqual(self.connection, self.router.connection_path)

    def test_kiro_base_quota_commands_pass_through(self):
        for command, args in (
            ('set_provider_base_quota_only', {'providerId': 14, 'enabled': True}),
            ('check_kiro_quotas', {'providerId': 14, 'includeDisabled': True}),
        ):
            with patch.object(self.router, 'call', return_value={'ok': True}) as call:
                result = self.router.action({'command': command, 'args': args})
            self.assertEqual(result, {'result': {'ok': True}})
            call.assert_called_once_with(command, args)


if __name__ == '__main__':
    unittest.main()

    def test_bedrock_registry_commands_pass_through(self):
        for command in ('bedrock_sync_models', 'bedrock_sync_pricing', 'bedrock_sync_status',
                        'list_bedrock_models', 'set_bedrock_model_enabled'):
            with patch.object(self.router, 'call', return_value={'ok': True}) as call:
                result = self.router.action({'command': command, 'args': {'input': {'providerId': 6}}})
            self.assertEqual(result, {'result': {'ok': True}})
            call.assert_called_once_with(command, {'input': {'providerId': 6}})
