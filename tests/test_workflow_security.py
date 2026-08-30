from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
WORKFLOW = (ROOT / ".github/workflows/build-image.yml").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_canary_tests_current_source_without_publishing():
    assert "pytest" in WORKFLOW
    assert "push: false" in WORKFLOW
    assert "platforms: linux/amd64" in WORKFLOW
    assert "pip install ." in WORKFLOW


def test_default_build_publishes_only_shaoyou11_ghcr():
    assert "ghcr.io/shaoyou11/efb-wechat-comwechat-slave:latest" in WORKFLOW
    assert "docker.io" not in WORKFLOW
    assert "0honus0/efb-wechat-comwechat-slave" not in WORKFLOW


def test_actions_are_pinned_to_commit_sha():
    refs = re.findall(
        r"(?m)^[ \t]*(?:-[ \t]+)?uses:[ \t]+([^\s#]+)", WORKFLOW
    )
    assert refs
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref) for ref in refs)


def test_image_installs_checkout_instead_of_upstream_self_repo():
    assert "COPY . /src" in DOCKERFILE
    assert "pip3 install /src" in DOCKERFILE
    assert "github.com/0honus0/efb-wechat-comwechat-slave" not in DOCKERFILE
