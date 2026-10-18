from turtlefw.cli import main


class TestCli:
    def test_version(self, capsys):
        assert main(["version"]) == 0
        assert "turtle-framework" in capsys.readouterr().out

    def test_demo_runs_without_token(self, capsys):
        assert main(["analyze", "600887", "--demo"]) == 0
        out = capsys.readouterr().out
        assert "穿透回报率" in out
        assert "门槛 II" in out
    def test_invalid_code_fails_cleanly(self, capsys):
        assert main(["analyze", "@@@"]) == 2
        assert "错误" in capsys.readouterr().err

    def test_help_when_no_command(self):
        try:
            main([])
        except SystemExit as exc:  # argparse exits 2 on missing command
            assert exc.code == 2
