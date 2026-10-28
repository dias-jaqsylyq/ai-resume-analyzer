import resume_analyzer


def test_package_exposes_version() -> None:
    assert resume_analyzer.__version__ == "0.1.0"
