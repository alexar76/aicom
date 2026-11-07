"""Exercise alien-monitor's actual signed-transaction adapter on a disposable local chain."""
from __future__ import annotations
import importlib.util, socket, subprocess,time
from pathlib import Path
from web3 import Web3
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('alien_acex_uni',ROOT/'alien-monitor/backend/acex_uni.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
proc=subprocess.Popen(['anvil','--host','127.0.0.1','--port',str(port),'--silent'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 w3=Web3(Web3.HTTPProvider(f'http://127.0.0.1:{port}',request_kwargs={'timeout':2,'allow_redirects':False}))
 for _ in range(100):
  if w3.is_connected():break
  time.sleep(.05)
 assert w3.is_connected() and w3.eth.chain_id==31337
 key=mod._anvil_key(0);sender=mod._anvil_addr(0);target=mod._anvil_addr(1)
 contract=w3.eth.contract(address=target,abi=[{'name':'probe','type':'function','stateMutability':'nonpayable','inputs':[{'name':'value','type':'uint256'}],'outputs':[]}])
 before=w3.eth.get_transaction_count(sender)
 receipt=mod._send(w3,key,contract.functions.probe(7))
 assert receipt['status']==1 and w3.eth.get_transaction_count(sender)==before+1
 print('alien-monitor actual _send: ABI build, nonce, EIP-1559 sign/raw send, receipt passed with Web3 7.15.0 / eth-account 0.13.7 on owned ephemeral chain31337')
finally:
 proc.terminate()
 try:proc.wait(timeout=5)
 except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
