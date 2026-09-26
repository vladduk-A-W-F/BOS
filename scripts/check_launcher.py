"""Bounded launcher regression tests, no network, installs, browser or server."""
import importlib.util,sys,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('launcher',Path(__file__).with_name('start_local.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.version_ok((3,12)) and m.version_ok((3,14)) and not m.version_ok((3,11))
with tempfile.TemporaryDirectory() as folder:
 root=Path(folder);venv=root/'.venv';python=venv/'bin/python';python.parent.mkdir(parents=True);python.touch()
 req=root/'requirements.txt';req.write_text('demo-package==1')
 stamp=venv/'bos-requirements.sha256'
 with patch.multiple(m,ROOT=root,LOG=root/'BOS_STARTUP.log',VENV=venv,STAMP=stamp),patch.object(m,'venv_python',return_value=python),patch.object(sys,'argv',['start_local.py','--check-only']),patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
  with patch.object(m,'run') as run:
   m.main();assert any('pip' in call.args[0] for call in run.call_args_list);assert stamp.exists()
  with patch.object(m,'run') as run:
   m.main();assert not any('pip' in call.args[0] for call in run.call_args_list)
  stamp.unlink()
  with patch.object(m,'run',side_effect=RuntimeError('installation failed')):
   try:m.main()
   except RuntimeError:pass
   else:raise AssertionError('failure not propagated')
   assert not stamp.exists()
  with patch.object(m,'run') as run:
   m.main();assert any('pip' in call.args[0] for call in run.call_args_list)
print('5 launcher checks passed; no network or server.')
