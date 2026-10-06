from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def load(name):
    d = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
    d["on"] = d.pop(True, d.get("on"))  # YAML 1.1 parses the bare key `on` as True
    return d


def bundle_step(job):
    return next(s for s in job["steps"] if s.get("name") == "Bundle site with latest data")


def test_both_deploys_bundle_discover_data():
    for name in ("analyze.yml", "discover.yml"):
        deploy = load(name)["jobs"]["deploy"]
        assert deploy["concurrency"]["group"] == "pages", name
        assert "discover-data" in bundle_step(deploy)["run"], name
        assert "site/data/discover" in bundle_step(deploy)["run"], name


def test_deploy_copy_is_conditional():
    run = bundle_step(load("analyze.yml")["jobs"]["deploy"])["run"]
    assert "git ls-remote --exit-code origin discover-data" in run


def test_discover_schedule_and_concurrency():
    d = load("discover.yml")
    assert d["on"]["schedule"][0]["cron"] == "0 6 * * 6"
    assert "workflow_dispatch" in d["on"]
    assert d["concurrency"]["group"] == "discover"
    scan = d["jobs"]["scan"]
    assert any("engine.discover" in s.get("run", "") for s in scan["steps"])
    assert any("push -f" in s.get("run", "") and "discover-data" in s.get("run", "") for s in scan["steps"])
    assert not any("GMAIL" in str(s.get("env", {})) for s in scan["steps"])
