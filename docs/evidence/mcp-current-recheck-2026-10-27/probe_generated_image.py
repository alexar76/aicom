"""Run only initialize and tools/list against our generated image in gVisor."""
import json
import subprocess
import threading

command = ["docker", "run", "--rm", "-i", "--runtime=runsc", "--network=none",
           "--memory=512m", "--memory-swap=512m", "--cpus=1", "--pids-limit=128",
           "--cap-drop=ALL", "--security-opt=no-new-privileges", "--read-only",
           "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m", "histor-generated-mcp-audit:20261027"]
proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True)
timer = threading.Timer(30, proc.kill)
timer.start()
wire = []
try:
    def send(message):
        assert message['method'] in {'initialize', 'notifications/initialized', 'tools/list'}
        wire.append({'sent': message})
        proc.stdin.write(json.dumps(message) + '\n')
        proc.stdin.flush()

    def reply():
        value = json.loads(proc.stdout.readline())
        wire.append({'received': value})
        assert 'result' in value, value
        return value['result']

    send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-06-18', 'capabilities': {},
        'clientInfo': {'name': 'alexar76-generated-audit', 'version': '1'}}})
    initialized = reply()
    send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
    tools = reply()['tools']
    assert len(tools) == 1 and tools[0]['name'] == 'echo-v1'
    proc.stdin.close()
    proc.wait(timeout=10)
    assert proc.returncode == 0
    image_id = subprocess.check_output(['docker', 'image', 'inspect',
                                        '--format={{.Id}}', 'histor-generated-mcp-audit:20261027'], text=True).strip()
    print(json.dumps({'status': 'ok', 'imageId': image_id, 'runNetwork': 'none',
                      'runtime': 'runsc', 'serverInfo': initialized['serverInfo'],
                      'tools': tools, 'wire': wire, 'toolCalls': 0}))
finally:
    timer.cancel()
    if proc.poll() is None:
        proc.kill()
        proc.wait()
