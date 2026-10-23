"""Exercise generated artifacts without installing services or contacting a VPS."""
import ast
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

SCRIPT = (Path(__file__).parents[1] / 'deploy-vps.sh').read_text()


def block(tag):
    return SCRIPT.split("<<'" + tag + "'\n", 1)[1].split('\n' + tag + '\n', 1)[0]


class DeployTests(unittest.TestCase):
    def test_syntax_and_regressions(self):
        subprocess.run(['bash','-n',str(Path(__file__).parents[1] / 'deploy-vps.sh')],check=True)
        for tag in ['CHECK_IP','CHECK_PORTS','GENERATE','SUB_SERVER','VERIFY']:
            ast.parse(block(tag))
        self.assertIn('WorkingDirectory=/var/lib/vps-hy', SCRIPT)
        self.assertIn('StateDirectory=vps-hy', SCRIPT)
        self.assertIn('bash "$work/xray-install.sh" install --without-geodata', SCRIPT)
        self.assertNotIn('install -u vps-xray', SCRIPT)

    def test_generated_pairs_and_subscription_service(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name in ['root/vps-nodes','etc/hysteria','etc/vps-sub','usr/local/etc/xray']:
                (root/name).mkdir(parents=True)
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                '-subj','/CN=vps-node.local','-keyout',str(root/'etc/hysteria/server.key'),
                '-out',str(root/'etc/hysteria/server.crt')],check=True,capture_output=True)
            def remap(code):
                for path in ['/root/vps-nodes','/etc/hysteria','/etc/vps-sub','/usr/local/etc/xray']:
                    code=code.replace(path,str(root/path.lstrip('/')))
                return code
            for label in ['PublicKey','Public key','Password','Password (PublicKey)']:
                fixture='PrivateKey: '+'A'*43+'\n'+label+': '+'B'*43+'\nHash32: '+'C'*43+'\n'
                prelude="import subprocess\noriginal=subprocess.check_output\ndef fake(args, **kwargs):\n    if args[0]=='/usr/local/bin/xray': return "+repr(fixture)+"\n    return original(args, **kwargs)\nsubprocess.check_output=fake\n"
                subprocess.run(['python3','-c',prelude+remap(block('GENERATE'))],check=True,
                    env={**os.environ,'VPS_PUBLIC_IP':'203.0.113.10','VPS_NODE_NAME':'Tokyo 日本'})
                config=json.loads((root/'etc/vps-sub/clash.yaml').read_text())
                native=json.loads((root/'root/vps-nodes/local-nodes.json').read_text())
                xray=json.loads((root/'usr/local/etc/xray/config.json').read_text())
                self.assertEqual(native['proxies'],config['proxies'])
                self.assertEqual(config['proxies'][0]['name'],'Tokyo 日本-VLESS')
                self.assertEqual(config['proxies'][0]['uuid'],xray['inbounds'][0]['settings']['clients'][0]['id'])
                self.assertEqual(config['proxies'][0]['reality-opts']['public-key'],'B'*43)
                self.assertEqual(len(config['proxies'][1]['fingerprint']),64)
                self.assertNotIn('privateKey',json.dumps(config))
                self.assertIn('%E6%97%A5%E6%9C%AC',(root/'root/vps-nodes/links.txt').read_text())
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            code=remap(block('SUB_SERVER')).replace("('0.0.0.0',8080)",repr(('127.0.0.1',port)))
            proc=subprocess.Popen(['python3','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                token=json.loads((root/'etc/vps-sub/settings.json').read_text())['token']
                url=f'http://127.0.0.1:{port}/{token}/clash.yaml'
                for attempt in range(40):
                    try:
                        with opener.open(url,timeout=1) as response:
                            self.assertEqual(response.read(),(root/'root/vps-nodes/clash.yaml').read_bytes())
                        break
                    except OSError:time.sleep(.05)
                else:self.fail('Subscription server failed to start')
                with opener.open(urllib.request.Request(url,method='HEAD')) as response:
                    self.assertEqual(response.read(),b'')
                for route in ['/','/settings.json','/../settings.json','/'+token+'/clash.yaml?x=1']:
                    with self.assertRaises(urllib.error.HTTPError) as result:
                        opener.open(f'http://127.0.0.1:{port}'+route)
                    self.assertEqual(result.exception.code,404)
                # File replacement is seen by the next GET without restarting the service.
                updated=json.dumps({'proxies':[]}).encode()
                (root/'etc/vps-sub/clash.yaml').write_bytes(updated)
                with opener.open(url) as response:self.assertEqual(response.read(),updated)
            finally:
                proc.terminate();proc.wait(timeout=3)
                stdout,stderr=proc.communicate()
                self.assertEqual(stderr,b'')


if __name__=='__main__':unittest.main()
