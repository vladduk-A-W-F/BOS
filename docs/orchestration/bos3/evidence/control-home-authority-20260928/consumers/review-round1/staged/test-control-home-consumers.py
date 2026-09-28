"""Prepared synthetic consumer ordering checks; run only after source review."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


STAGED = Path(__file__).resolve().parent
CORE = STAGED.parents[1] / "source" / "staged"
sys.path.insert(0, str(CORE))
import bos_dev


def staged_module(name):
    spec = importlib.util.spec_from_file_location(name, STAGED / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


local_flow = staged_module("local_flow")
repo_health = staged_module("repo_health")
sys.modules["local_flow"] = local_flow
bos_flow = staged_module("bos_flow")


class ConsumerAuthorityTests(unittest.TestCase):
    def test_fixed_provider_and_default_home(self):
        expected = Path("D:/3/BOSDev/control-home")
        self.assertEqual(local_flow.DEFAULT_HOME, expected)
        self.assertEqual(repo_health.DEFAULT_HOME, expected)
        self.assertEqual(local_flow.TOOLS, expected / "tools")
        self.assertEqual(repo_health.TOOLS, expected / "tools")
        self.assertEqual(bos_flow.TOOLS, expected / "tools")

    def test_local_flow_refuses_before_state_or_git(self):
        with patch.object(local_flow, "resolve_control_home", side_effect=bos_dev.ControlHomeError("refused")):
            with patch.object(local_flow, "load") as state_read:
                with patch.object(local_flow, "repo_state") as git_read:
                    with self.assertRaises(bos_dev.ControlHomeError):
                        local_flow.collect(Path("C:/Users/user/AppData/Local/BOSDev"), Path("D:/3/BOSDev"))
        state_read.assert_not_called()
        git_read.assert_not_called()

    def test_repo_health_refuses_before_snapshot_reads(self):
        with patch.object(repo_health, "resolve_control_home", side_effect=bos_dev.ControlHomeError("refused")):
            with patch.object(repo_health, "read_json_once") as state_read:
                with self.assertRaises(bos_dev.ControlHomeError):
                    repo_health.collect(Path("C:/Users/user/AppData/Local/BOSDev"),
                                        Path("D:/3/BOSDev"), Path("D:/3/BOSDev/synthetic.json"))
        state_read.assert_not_called()

    def test_flow_refuses_before_transport(self):
        with patch.object(bos_flow, "resolve_control_home", side_effect=bos_dev.ControlHomeError("refused")):
            with patch.object(bos_flow.channel, "AppTools") as transport:
                with self.assertRaises(bos_dev.ControlHomeError):
                    bos_flow.refresh(home=Path("C:/Users/user/AppData/Local/BOSDev"))
        transport.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
