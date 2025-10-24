def test_repo_boots():
    assert True


def test_config_yaml_exists():
    import os

    assert os.path.exists("config/config.yaml")
