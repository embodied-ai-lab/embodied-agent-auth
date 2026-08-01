from __future__ import annotations


def test_container_definitions_include_documented_endpoint_tools(repo_root):
    for relative in ("containers/Apptainer.def", "containers/Dockerfile"):
        text = (repo_root / relative).read_text(encoding="utf-8")
        assert "curl" in text
        assert "ca-certificates" in text


def test_setup_documents_an_in_container_endpoint_check(repo_root):
    documentation = (repo_root / "docs/SETUP.md").read_text(encoding="utf-8")
    assert 'lab() { apptainer exec --pwd "$PWD" "$SIF" "$@"; }' in documentation
    assert 'lab curl "${OLLAMA_HOST%/}/api/version"' in documentation
    assert "curl" in (repo_root / "containers/Apptainer.def").read_text()


def test_setup_and_readme_agree_on_the_container_helper(repo_root):
    setup = (repo_root / "docs/SETUP.md").read_text(encoding="utf-8")
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    helper = 'lab() { apptainer exec --pwd "$PWD" "$SIF" "$@"; }'
    assert helper in setup
    assert helper in readme
    for variable in (
        "APPTAINERENV_OLLAMA_HOST",
        "APPTAINERENV_VLM_MODEL",
        "APPTAINERENV_ROS_DOMAIN_ID",
    ):
        assert variable in setup
        assert variable in readme


def test_setup_forbids_login_node_work(repo_root):
    setup = (repo_root / "docs/SETUP.md").read_text(encoding="utf-8")
    assert "What must never run on a login node" in setup
    assert "apptainer build" in setup
    assert "iscps_refuse_login_node" in (repo_root / "scripts/lib.sh").read_text()
