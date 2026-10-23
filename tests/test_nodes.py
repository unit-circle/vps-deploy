import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('nodes', Path(__file__).parents[1] / 'scripts/vps-nodes.py')
nodes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nodes)


def snapshot(host='203.0.113.10'):
    return {'proxies':[
        {'name':'VPS-VLESS','type':'vless','server':host,'port':443,'uuid':'test-uuid',
         'tls':True,'reality-opts':{'public-key':'fixture-public','short-id':'abcd'}},
        {'name':'VPS-HY2','type':'hysteria2','server':host,'port':443,'password':'fixture-password','fingerprint':'f'*64}]}


class NodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.pub = self.root / 'published.yaml'
        self.base = {**snapshot(), 'proxy-groups':[{'name':'PROXY','type':'select','proxies':['DIRECT']}], 'rules':['MATCH,PROXY']}
        (self.state / 'clash.yaml').write_bytes(nodes.encode(self.base))
        (self.state / 'local-nodes.json').write_bytes(nodes.encode(snapshot()))
        (self.state / 'subscription.txt').write_text('http://example.invalid/private-token/clash.yaml\n')
        self.pub.write_bytes(nodes.encode(self.base))
        self.pub.chmod(0o640)
        self.patchers = [patch.object(nodes,'STATE',self.state),patch.object(nodes,'PUBLISHED',self.pub),patch.object(os,'geteuid',return_value=0)]
        for p in self.patchers:p.start()

    def tearDown(self):
        for p in reversed(self.patchers):p.stop()
        self.tmp.cleanup()

    def run_command(self, *args):
        nodes.run(nodes.parser().parse_args(args))

    def test_import_replace_remove_and_native_export(self):
        remote = self.root / 'remote.json'
        remote.write_bytes(nodes.encode(snapshot('198.51.100.20')))
        self.run_command('import','tokyo',str(remote))
        first = json.loads(self.pub.read_text())
        self.assertEqual(len(first['proxies']),4)
        self.assertTrue(first['proxies'][2]['name'].startswith('[tokyo]'))
        self.assertEqual(stat.S_IMODE(self.pub.stat().st_mode),0o640)
        self.assertEqual(first['rules'],self.base['rules'])
        self.assertEqual(first['proxy-groups'][0]['proxies'][-1],'DIRECT')
        self.run_command('import','tokyo',str(remote))
        self.assertEqual(len(json.loads(self.pub.read_text())['proxies']),4)
        exp = self.root / 'export.json'
        self.run_command('export',str(exp))
        self.assertEqual(len(json.loads(exp.read_text())['proxies']),2)
        self.assertEqual(stat.S_IMODE(exp.stat().st_mode),0o600)
        self.run_command('remove','tokyo')
        self.assertEqual(len(json.loads(self.pub.read_text())['proxies']),2)
        self.assertIn('private-token',(self.state / 'subscription.txt').read_text())

    def test_bad_import_does_not_modify_published_file(self):
        before = self.pub.read_bytes()
        bad = self.root / 'bad.json'
        bad.write_text('{"proxies": [{"name":"bad"}]}')
        with self.assertRaises(ValueError):self.run_command('import','tokyo',str(bad))
        self.assertEqual(before,self.pub.read_bytes())

    def test_source_path_traversal_rejected(self):
        with self.assertRaises(ValueError):self.run_command('import','../outside',str(self.pub))

    def test_duplicate_names_rejected(self):
        doc = snapshot()
        doc['proxies'][1]['name']=doc['proxies'][0]['name']
        with self.assertRaises(ValueError):nodes.validate(doc)

    def test_foreign_rules_are_ignored(self):
        doc = snapshot()
        doc['rules']=['MATCH,DIRECT']
        self.assertEqual(set(nodes.validate(doc)),{'proxies'})

    def test_export_cannot_overwrite_configs(self):
        before=self.pub.read_bytes()
        with self.assertRaises(ValueError):self.run_command('export',str(self.pub))
        self.assertEqual(before,self.pub.read_bytes())

    def test_transaction_rolls_back_partial_publish(self):
        one=self.state/'one';two=self.state/'two'
        one.write_bytes(b'old-one');two.write_bytes(b'old-two')
        original=os.replace
        calls=0
        def flaky(a,b):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('simulated write failure')
            return original(a,b)
        with patch.object(os,'replace',side_effect=flaky):
            with self.assertRaises(OSError):nodes.transaction({one:b'new-one',two:b'new-two'})
        self.assertEqual(one.read_bytes(),b'old-one')
        self.assertEqual(two.read_bytes(),b'old-two')


if __name__ == '__main__':unittest.main()
