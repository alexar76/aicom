from web.backend.services.sandbox_file_policy import sandbox_file_path_allowed


def test_blocks_env_and_git():
    assert sandbox_file_path_allowed("index.html") is True
    assert sandbox_file_path_allowed(".env") is False
    assert sandbox_file_path_allowed(".git/config") is False
    assert sandbox_file_path_allowed("secrets/id_rsa") is False
    assert sandbox_file_path_allowed("certs/server.pem") is False
