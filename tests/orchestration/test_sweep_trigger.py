from pathlib import Path
from unittest.mock import patch

import pytest

from app.orchestration.sweep_trigger import trigger_sweep_job


@pytest.fixture
def mock_azure_env(monkeypatch):
    monkeypatch.setenv("ACA_RESOURCE_GROUP", "test-rg")
    monkeypatch.setenv("ACA_JOB_NAME", "test-job")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "DefaultEndpointsProtocol=https;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;")


def test_trigger_sweep_job_dry_run(mock_azure_env, tmp_path):
    config = tmp_path / "sweep.yaml"
    config.write_text("strategy: breakout")

    result = trigger_sweep_job(config, dry_run=True)
    
    assert result["status"] == "dry-run"
    assert "blob_url" in result
    assert "dryrun.blob" in result["blob_url"]


@patch("app.orchestration.sweep_trigger.BlobStorageClient")
@patch("app.orchestration.sweep_trigger._run_az_command")
def test_trigger_sweep_job_success(mock_run_az, mock_blob_client, mock_azure_env, tmp_path):
    config = tmp_path / "sweep.yaml"
    config.write_text("strategy: breakout")

    # Mock blob client
    mock_client_instance = mock_blob_client.return_value
    mock_client_instance.upload_text.return_value = "https://blob.url/config.yaml"

    # Mock az command output
    mock_run_az.return_value = "Job started"

    result = trigger_sweep_job(config, dry_run=False)

    assert result["status"] == "triggered"
    assert result["blob_url"] == "https://blob.url/config.yaml"
    
    # Verify az command arguments
    args, _ = mock_run_az.call_args
    cmd_list = args[0]
    assert "containerapp" in cmd_list
    assert "job" in cmd_list
    assert "--env-vars" in cmd_list
    
    # Check env vars passed to az
    env_vars_idx = cmd_list.index("--env-vars") + 1
    assert any("SWEEP_CONFIG_BLOB=https://blob.url/config.yaml" in arg for arg in cmd_list[env_vars_idx:])


def test_trigger_sweep_job_missing_config():
    with pytest.raises(FileNotFoundError):
        trigger_sweep_job(Path("nonexistent.yaml"))
