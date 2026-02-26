from senior_cpp_agent.tools import _is_command_allowed


def test_policy_allows_expected_commands():
    assert _is_command_allowed("ctest -V")
    assert _is_command_allowed("g++ main.cpp")
    assert _is_command_allowed("clang-tidy src/main.cpp")


def test_policy_blocks_unexpected_commands():
    assert not _is_command_allowed("rm -rf /")
    assert not _is_command_allowed("")
