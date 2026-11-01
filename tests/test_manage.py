"""Maintenance tests use isolated fixtures; never touch a live VPS or download binaries."""
import copy
from contextlib import ExitStack, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('manage', Path(__file__).parents[1]/'scripts/vps-manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


def fixtures():
    return ({'log':{'loglevel':'warning'}, 'inbounds':[{'port':443}],
             'outbounds':[{'protocol':'freedom','tag':'direct','settings':{},
                 'streamSettings':{'sockopt':{'tcpKeepAliveIdle':300}}},
                 {'protocol':'blackhole','tag':'blocked'}]},
            {'listen':'0.0.0.0:443', 'tls':{'cert':'fixture.crt','key':'fixture.key'},
             'auth':{'type':'password','password':'fixture-password'}})


class PureTests(unittest.TestCase):
    def test_ipv4_update_preserves_all_other_fields(self):
        original_x, original_h = fixtures()
        old_x, old_h = copy.deepcopy(original_x), copy.deepcopy(original_h)
        x, h = manage.ipv4_configs(original_x, original_h)
        self.assertEqual(x['outbounds'][0]['streamSettings']['sockopt'].pop('domainStrategy'), 'ForceIPv4')
        self.assertEqual(h.pop('outbounds'), [{'name':'direct','type':'direct','direct':{'mode':'4'}}])
        self.assertEqual((x,h), (old_x,old_h))
        self.assertEqual((original_x,original_h), (old_x,old_h))

    def test_ipv4_update_is_idempotent_and_retains_direct_binding(self):
        x, h = fixtures()
        h['outbounds']=[{'name':'default','type':'direct','direct':{'mode':'auto','bindIPv4':'192.0.2.1'}}]
        first=manage.ipv4_configs(x,h)
        self.assertEqual(manage.ipv4_configs(*first), first)
        self.assertEqual(first[1]['outbounds'][0]['direct']['bindIPv4'],'192.0.2.1')

    def test_custom_acl_or_proxy_not_silently_rewritten(self):
        for custom in [{'acl':{'inline':['reject(all)']}},
                       {'outbounds':[{'type':'socks5'}]},
                       {'outbounds':[{'type':'direct'},{'type':'direct'}]}]:
            x,h=fixtures(); h.update(custom)
            with self.subTest(custom=custom), self.assertRaises(ValueError):
                manage.ipv4_configs(x,h)

    def test_missing_or_ambiguous_direct_is_rejected(self):
        x,h=fixtures()
        x['outbounds']=[]
        with self.assertRaises(ValueError):manage.ipv4_configs(x,h)
        x['outbounds']=[{'protocol':'freedom','tag':'direct'}]*2
        with self.assertRaises(ValueError):manage.ipv4_configs(x,h)

    def test_network_plan_only_raises_maxima_and_requires_available_bbr(self):
        current=dict(zip(manage.NETWORK_KEYS,['33554432','212992','cubic']))
        self.assertEqual(manage.network_plan(current,'cubic reno'),
            {'net.core.rmem_max':'33554432','net.core.wmem_max':'16777216'})
        self.assertEqual(manage.network_plan(current,'cubic bbr',True)[manage.NETWORK_KEYS[2]],'bbr')
        with self.assertRaises(ValueError):manage.network_plan(current,'cubic',True)

    def test_https_config_avoids_node_ports_and_does_not_embed_credentials(self):
        config=manage.caddy_config('SUB.EXAMPLE.COM','admin@example.com').decode()
        self.assertIn('https://sub.example.com:8443',config)
        self.assertIn('disable_tlsalpn_challenge',config)
        self.assertIn('reverse_proxy 127.0.0.1:8080',config)
        self.assertIn('protocols h1 h2',config)
        self.assertNotIn('fixture-password',config)
        self.assertNotIn('tls internal',config)

    def test_https_config_rejects_injection_and_ip_address(self):
        for domain,email in [('1.2.3.4','admin@example.com'), ('x.com\nrespond 200','a@b.com'),
                             ('https://example.com','a@b.com'), ('example.com','a@b.com\nadmin off')]:
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                manage.caddy_config(domain,email)

    def test_release_asset_arch_and_explicit_version(self):
        self.assertEqual(manage.release_asset('xray','v26.3.27','x86_64')[1],'Xray-linux-64.zip')
        self.assertEqual(manage.release_asset('hysteria','v2.13.0','aarch64')[1],'hysteria-linux-arm64')
        self.assertEqual(manage.release_asset('caddy','v2.10.2','x86_64')[1],'caddy_2.10.2_linux_amd64.tar.gz')
        for version,arch in [('latest','x86_64'),('v2.1.0-beta','x86_64'),('v2.1.0','mips')]:
            with self.assertRaises(ValueError):manage.release_asset('xray',version,arch)

    def test_snapshot_path_allowlist(self):
        for name in ['/etc/shadow','/etc/hysteria/../../shadow','/etc//hysteria/config.yaml',
                     'etc/hysteria/config.yaml','/etc/hysteria\\config.yaml']:
            self.assertFalse(manage.allowed(name))
        self.assertTrue(manage.allowed('/etc/hysteria/server.key'))

    def test_apply_is_never_implied_by_argument_parser(self):
        for args in [['update'],['network'],['https','--domain','a.example.com','--email','a@b.com'],
                     ['upgrade','xray','--version','v26.3.27'],['restore','/root/vps-backups/example']]:
            self.assertFalse(manage.parser().parse_args(args).apply)


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.root=Path(self.temporary.name).resolve()
        self.stack=ExitStack()
        self.stack.enter_context(patch.object(manage,'ROOT',self.root))
        self.stack.enter_context(patch.object(manage,'states',return_value={s:False for s in manage.SERVICES}))
        self.stack.enter_context(patch.object(manage,'enabled',return_value=False))
        self.stack.enter_context(patch.object(manage,'sysctl',return_value='212992'))
        self.reset=self.stack.enter_context(patch.object(manage,'reset_services'))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        if os.name != 'posix':
            # Exercise actual writes/renames/rollback, without claiming POSIX ownership coverage.
            self.stack.enter_context(patch.object(os,'fchmod',create=True))
            self.stack.enter_context(patch.object(os,'fchown',create=True))
        x,h=fixtures()
        for name,obj in [(manage.XRAY,x),(manage.HY2,h),(manage.SETTINGS,{'token':'fixture-token'}),
                         ('/root/vps-nodes/local-nodes.json',{'proxies':[{'server':'203.0.113.10'}]})]:
            p=manage.path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(manage.encode(obj))
        manage.path('/root/vps-nodes/.deploy-complete').touch()

    def tearDown(self):
        self.stack.close()
        self.temporary.cleanup()

    def test_backup_captures_private_files_and_checksum(self):
        destination=manage.backup()
        manifest=json.loads((destination/'manifest.json').read_text())
        entry=manifest['files'][manage.HY2]
        copied=(destination/'files'/manage.HY2.lstrip('/')).read_bytes()
        self.assertEqual(hashlib.sha256(copied).hexdigest(),entry['sha256'])
        self.assertIn('fixture-password',copied.decode())
        self.assertFalse(manifest['network_file_present'])

    @unittest.skipUnless(os.name=='posix','POSIX permission coverage requires Linux')
    def test_backup_and_atomic_permissions(self):
        destination=manage.backup()
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((destination/'manifest.json').stat().st_mode),0o600)
        os.chmod(manage.path(manage.XRAY),0o640)
        manage.atomic(manage.XRAY,b'{}')
        self.assertEqual(stat.S_IMODE(manage.path(manage.XRAY).stat().st_mode),0o640)

    def test_transaction_restores_originals_and_removes_new_files(self):
        original=manage.path(manage.XRAY).read_bytes()
        added='/etc/vps-sub-https/Caddyfile'
        with self.assertRaisesRegex(ValueError,'simulated'):
            manage.transactional({manage.XRAY:b'changed',added:b'new'},
                lambda:(_ for _ in ()).throw(ValueError('simulated failure')))
        self.assertEqual(manage.path(manage.XRAY).read_bytes(),original)
        self.assertFalse(manage.path(added).exists())
        self.reset.assert_called_once()

    def test_transaction_runs_runtime_rollback(self):
        rollback=Mock()
        with self.assertRaises(ValueError):
            manage.transactional({manage.XRAY:b'changed'},
                lambda:(_ for _ in ()).throw(ValueError('failure')),rollback_runtime=rollback)
        rollback.assert_called_once()

    def test_network_failure_restores_runtime_and_removes_new_persistent_file(self):
        calls=[]
        def run(args, **kwargs):
            calls.append(args)
            if args == ['sysctl','-w','net.core.wmem_max=16777216']:
                raise ValueError('simulated kernel rejection')
            return ''
        values=dict(zip(manage.NETWORK_KEYS,['212992','212992','cubic']))
        values['net.ipv4.tcp_available_congestion_control']='cubic'
        with patch.object(manage,'sysctl',side_effect=lambda key:values[key]), \
             patch.object(manage,'command',side_effect=run), self.assertRaises(ValueError):
            manage.network(True)
        self.assertFalse(manage.path(manage.NETWORK_FILE).exists())
        self.assertIn(['sysctl','-w','net.core.rmem_max=212992'],calls)
        self.assertIn(['sysctl','-w','net.core.wmem_max=212992'],calls)

    def test_update_preview_does_not_write_or_restart(self):
        backend=manage.path('/opt/vps-sub/server.py');backend.parent.mkdir(parents=True)
        backend.write_text("ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()")
        before=manage.path(manage.XRAY).read_bytes()
        with patch.object(manage,'transactional') as transaction:
            manage.update()
        transaction.assert_not_called()
        self.assertEqual(manage.path(manage.XRAY).read_bytes(),before)

    def test_legacy_backend_bind_migration_does_not_change_default_address(self):
        backend=manage.path('/opt/vps-sub/server.py');backend.parent.mkdir(parents=True)
        backend.write_text("ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()")
        with patch.object(manage,'transactional') as transaction, patch.object(manage,'active',return_value=True):
            manage.update(True)
        changed=transaction.call_args.args[0]['/opt/vps-sub/server.py'].decode()
        self.assertIn("settings.get('listen','0.0.0.0')",changed)

    def test_restore_refuses_tampered_and_traversal_snapshot(self):
        snapshot=manage.backup()
        data=snapshot/'files'/manage.XRAY.lstrip('/')
        data.write_bytes(b'tampered')
        with patch.object(manage,'transactional') as transaction, self.assertRaisesRegex(ValueError,'checksum'):
            manage.restore(snapshot,True)
        transaction.assert_not_called()
        manifest=json.loads((snapshot/'manifest.json').read_text())
        manifest['files']={'/etc/shadow':next(iter(manifest['files'].values()))}
        (snapshot/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'outside managed'):
            manage.restore(snapshot)

    def test_network_plan_preserves_larger_buffers_and_previews(self):
        with patch.object(manage,'sysctl',side_effect=['33554432','33554432','cubic','reno cubic']), \
             patch.object(manage,'transactional') as transaction:
            manage.network()
        transaction.assert_not_called()

    def test_https_legacy_backend_and_missing_caddy_fail_before_writing(self):
        with self.assertRaisesRegex(ValueError,'Install Caddy'):
            manage.https('sub.example.com','admin@example.com',True)
        self.assertFalse(manage.path('/etc/vps-sub-https/Caddyfile').exists())

    def https_fixture(self):
        binary=manage.path('/usr/local/bin/caddy');binary.parent.mkdir(parents=True);binary.write_bytes(b'fixture')
        backend=manage.path('/opt/vps-sub/server.py');backend.parent.mkdir(parents=True)
        backend.write_text("settings.get('listen','0.0.0.0')")
        url=manage.path('/root/vps-nodes/subscription.txt');url.write_text('http://fixture.invalid/old\n')
        def resolve(host, port, family, socktype):
            if family == manage.socket.AF_INET6:
                raise manage.socket.gaierror('no AAAA fixture')
            return [(family,socktype,0,'',('203.0.113.10',port))]
        self.stack.enter_context(patch.object(manage.socket,'getaddrinfo',side_effect=resolve))
        self.stack.enter_context(patch.object(manage.socket,'socket'))
        self.stack.enter_context(patch.object(manage,'command',return_value=''))
        self.stack.enter_context(patch.object(manage,'subscription_test'))
        self.stack.enter_context(patch.object(manage,'wait_services'))
        self.stack.enter_context(patch.object(manage.time,'sleep'))

    def test_https_success_restricts_backend_and_publishes_verified_url(self):
        self.https_fixture()
        with patch.object(manage,'https_test') as verify:
            manage.https('sub.example.com','admin@example.com',True)
        verify.assert_called_once_with('sub.example.com')
        self.assertEqual(manage.load(manage.SETTINGS)['listen'],'127.0.0.1')
        self.assertTrue(manage.path('/root/vps-nodes/subscription.txt').read_text().startswith('https://sub.example.com:8443/'))

    def test_https_certificate_failure_restores_http_and_settings(self):
        self.https_fixture()
        before=manage.path(manage.SETTINGS).read_bytes()
        with patch.object(manage,'https_test',side_effect=OSError('untrusted certificate')), \
             self.assertRaisesRegex(ValueError,'Trusted HTTPS'):
            manage.https('sub.example.com','admin@example.com',True)
        self.assertEqual(manage.path(manage.SETTINGS).read_bytes(),before)
        self.assertEqual(manage.path('/root/vps-nodes/subscription.txt').read_text(),'http://fixture.invalid/old\n')
        self.assertFalse(manage.path('/etc/vps-sub-https/Caddyfile').exists())

    def test_upgrade_missing_digest_refuses_download(self):
        release={'assets':[{'name':'hysteria-linux-amd64','browser_download_url':
            'https://github.com/apernet/hysteria/releases/download/v2.13.0/hysteria-linux-amd64'}]}
        with patch.object(manage.platform,'machine',return_value='x86_64'), \
             patch.object(manage,'fetch_json',return_value=release), \
             patch.object(manage.urllib.request,'urlopen') as download, self.assertRaisesRegex(ValueError,'no SHA256'):
            manage.upgrade('hysteria','v2.13.0',True)
        download.assert_not_called()

    def test_upgrade_bad_checksum_never_writes_binary(self):
        release={'assets':[{'name':'hysteria-linux-amd64','digest':'sha256:'+'a'*64,
            'browser_download_url':'https://github.com/apernet/hysteria/releases/download/v2.13.0/hysteria-linux-amd64'}]}
        binary=manage.path('/usr/local/bin/hysteria');binary.parent.mkdir(parents=True);binary.write_bytes(b'original')
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock()
        response.read.return_value=b'incorrect-download'
        with patch.object(manage.platform,'machine',return_value='x86_64'), \
             patch.object(manage,'fetch_json',return_value=release), \
             patch.object(manage.urllib.request,'urlopen',return_value=response), self.assertRaisesRegex(ValueError,'checksum'):
            manage.upgrade('hysteria','v2.13.0',True)
        self.assertEqual(binary.read_bytes(),b'original')

    def test_verified_upgrade_version_failure_restores_original_binary(self):
        payload=b'fixture-new-executable'
        release={'assets':[{'name':'hysteria-linux-amd64','digest':'sha256:'+hashlib.sha256(payload).hexdigest(),
            'browser_download_url':'https://github.com/apernet/hysteria/releases/download/v2.13.0/hysteria-linux-amd64'}]}
        binary=manage.path('/usr/local/bin/hysteria');binary.parent.mkdir(parents=True);binary.write_bytes(b'original')
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock();response.read.return_value=payload
        with patch.object(manage.platform,'machine',return_value='x86_64'), \
             patch.object(manage,'fetch_json',return_value=release), \
             patch.object(manage.urllib.request,'urlopen',return_value=response), \
             patch.object(manage,'active',return_value=False), \
             patch.object(manage,'command',return_value='v2.12.0'), self.assertRaisesRegex(ValueError,'requested version'):
            manage.upgrade('hysteria','v2.13.0',True)
        self.assertEqual(binary.read_bytes(),b'original')

    def test_restore_reverts_file_and_pre_tuning_network_state(self):
        original=manage.path(manage.XRAY).read_bytes()
        snapshot=manage.backup()
        manage.path(manage.XRAY).write_bytes(b'newer configuration')
        tune=manage.path(manage.NETWORK_FILE);tune.parent.mkdir(parents=True)
        tune.write_text('# Managed by vps-deploy\nnet.core.rmem_max=16777216\n')
        with patch.object(manage,'xray_test'), patch.object(manage,'apply_sysctl') as apply_network, \
             patch.object(manage,'wait_services'):
            manage.restore(snapshot,True)
        self.assertEqual(manage.path(manage.XRAY).read_bytes(),original)
        self.assertFalse(tune.exists())
        apply_network.assert_called_once()

    def test_unmanaged_deployment_is_rejected(self):
        manage.path('/root/vps-nodes/.deploy-complete').unlink()
        with self.assertRaisesRegex(ValueError,'No completed'):
            manage.managed()


if __name__=='__main__':
    unittest.main()
