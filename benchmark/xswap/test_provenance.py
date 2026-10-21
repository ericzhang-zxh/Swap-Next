# SPDX-License-Identifier: GPL-2.0-only
import copy,json,os,pathlib,tempfile,unittest
from evidence import parse
from evaluate_kernel import verify_run,digest
BASE=pathlib.Path(__file__).resolve().parent
class EvidenceGates(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  fixture=os.environ.get("XSWAP_EVIDENCE_FIXTURE")
  if not fixture:raise unittest.SkipTest("Set XSWAP_EVIDENCE_FIXTURE to a real disk-run result.json; no bundled guest evidence")
  cls.fixture=json.loads(pathlib.Path(fixture).read_text())
  cls.expected={k:cls.fixture[k] for k in ["source_commit","image_sha256","config_sha256","instrument_sha256","initrd_sha256"]}
 def test_real_completed_guest(self):
  verify_run(copy.deepcopy(self.fixture),self.expected,"disk",set())
 def test_every_input_identity_is_pinned(self):
  for key in self.expected:
   with self.subTest(key=key):
    d=copy.deepcopy(self.fixture);d[key]="wrong"
    with self.assertRaises(ValueError):verify_run(d,self.expected,"disk",set())
 def test_duplicate_boot_rejected(self):
  with self.assertRaises(ValueError):verify_run(self.fixture,self.expected,"disk",{self.fixture["boot_id"]})
 def test_backend_not_used_rejected(self):
  d=copy.deepcopy(self.fixture);d["backend"]="zswap"
  with self.assertRaises(ValueError):verify_run(d,self.expected,"zswap",set())
 def test_raw_evidence_tampering_rejected(self):
  d=copy.deepcopy(self.fixture);d["serial_sha256"]="0"*64
  with self.assertRaises(ValueError):verify_run(d,self.expected,"disk",set())
 def test_missing_or_nonfinite_metrics_rejected(self):
  for value in [None,True,float("nan"),float("inf"),0,-1]:
   d=copy.deepcopy(self.fixture);d["metrics"]["swapped_first_access_p99_us"]=value
   with self.assertRaises(ValueError):verify_run(d,self.expected,"disk",set())
 def test_metric_edit_with_original_raw_is_rejected(self):
  d=copy.deepcopy(self.fixture);d["metrics"]["mapped_clusters_after_settle"]+=1
  with self.assertRaises(ValueError):verify_run(d,self.expected,"disk",set())
 def test_raw_parser_detects_warnings_and_truncation(self):
  raw=(pathlib.Path(self.fixture["run"])/"serial.log").read_text()
  self.assertTrue(all(parse(raw)["gates"].values()))
  self.assertFalse(parse(raw+"\nWARNING: injected validation fixture\n")["gates"]["no_kernel_warnings"])
  self.assertFalse(parse(raw.replace("LATENCY_NS ","BROKEN_NS "))["gates"]["sample_count"])
  self.assertFalse(parse(raw.replace("SWAPOFF_LIVE_PASS","MISSING"))["gates"]["swapoff_live_data"])
  self.assertFalse(parse(raw.replace("XSWAP_PASS","MISSING"))["gates"]["completed"])
if __name__=="__main__":unittest.main()
