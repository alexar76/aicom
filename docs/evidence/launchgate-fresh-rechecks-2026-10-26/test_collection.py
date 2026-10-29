"""Regression: failed transfers may never delete the sole model-evidence copy."""
import hashlib,io,json,subprocess,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_linux

class CollectionSafety(unittest.TestCase):
 def archive(self,name='out/example.json'):
  data=b'{"preserved": true}'
  b=io.BytesIO()
  with tarfile.open(fileobj=b,mode='w:gz') as t:
   for n,v in [(name,data),('output-manifest.json',json.dumps({name:hashlib.sha256(data).hexdigest()}).encode())]:
    m=tarfile.TarInfo(n);m.size=len(v);t.addfile(m,io.BytesIO(v))
  return b.getvalue()
 def test_failed_archive_connection_does_not_cleanup(self):
  with tempfile.TemporaryDirectory() as d,patch.object(run_linux,'remote',side_effect=subprocess.CalledProcessError(255,'ssh')) as remote:
   with self.assertRaises(subprocess.CalledProcessError):run_linux.collect('/tmp/warden-fresh-rechecks-test',Path(d),{'collectionVerified':False})
   self.assertEqual(remote.call_count,1);self.assertNotIn('shutil.rmtree',remote.call_args[0][0])
 def test_failed_scp_does_not_cleanup(self):
  raw=self.archive();expected=json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}).encode()
  with tempfile.TemporaryDirectory() as d,patch.object(run_linux,'remote',return_value=expected) as remote,patch.object(run_linux.subprocess,'run',side_effect=subprocess.CalledProcessError(255,'scp')):
   with self.assertRaises(subprocess.CalledProcessError):run_linux.collect('/tmp/warden-fresh-rechecks-test',Path(d),{'collectionVerified':False})
   self.assertEqual(remote.call_count,1)
 def test_bad_download_hash_does_not_cleanup(self):
  raw=self.archive();expected=json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}).encode()
  with tempfile.TemporaryDirectory() as d,patch.object(run_linux,'remote',return_value=expected) as remote:
   def copy(*a,**k):(Path(d)/'outputs.tar.gz').write_bytes(b'broken')
   with patch.object(run_linux.subprocess,'run',side_effect=copy):
    with self.assertRaises(AssertionError):run_linux.collect('/tmp/warden-fresh-rechecks-test',Path(d),{'collectionVerified':False})
   self.assertEqual(remote.call_count,1)
 def test_cleanup_only_after_verified_archive_and_extracted_hashes(self):
  raw=self.archive();expected=json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}).encode()
  with tempfile.TemporaryDirectory() as d:
   state=Path(d);calls=[]
   def remote(code):
    calls.append(code)
    if 'shutil.rmtree' in code:
     self.assertTrue(json.loads((state/'execution-local.json').read_text())['collectionVerified'])
     self.assertTrue((state/'out/example.json').is_file())
     return b'{"absent":true}'
    return expected
   def copy(*a,**k):(state/'outputs.tar.gz').write_bytes(raw)
   with patch.object(run_linux,'remote',side_effect=remote),patch.object(run_linux.subprocess,'run',side_effect=copy):
    receipt={'collectionVerified':False};run_linux.collect('/tmp/warden-fresh-rechecks-test',state,receipt)
   self.assertTrue(receipt['cleanup']['absent']);self.assertEqual(len(calls),2)
 def test_unsafe_member_is_not_extracted_or_cleaned_up(self):
  raw=self.archive('../escape');expected=json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}).encode()
  with tempfile.TemporaryDirectory() as d,patch.object(run_linux,'remote',return_value=expected) as remote:
   def copy(*a,**k):(Path(d)/'outputs.tar.gz').write_bytes(raw)
   with patch.object(run_linux.subprocess,'run',side_effect=copy):
    with self.assertRaises(AssertionError):run_linux.collect('/tmp/warden-fresh-rechecks-test',Path(d),{'collectionVerified':False})
   self.assertEqual(remote.call_count,1)

if __name__=='__main__':unittest.main()
