import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "descargar"


class TestDescargarGuards(unittest.TestCase):
    def run_descargar(self, number, extra_env=None):
        env = os.environ.copy()
        env["TODUS_SENDER"] = "58799457"
        env["TDS_GH_TOKEN_FILE"] = "/nonexistent/todus-gh-token"
        env.pop("GH_TOKEN", None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", str(SCRIPT)],
            input=f"https://example.com/video.mp4\n480\n{number}\n",
            text=True,
            capture_output=True,
            env=env,
            timeout=10,
        )

    def test_self_destination_is_rejected(self):
        result = self.run_descargar("58799457")
        self.assertEqual(result.returncode, 1)
        self.assertIn("mismo numero que el emisor", result.stdout)

    def test_invalid_destination_is_rejected(self):
        result = self.run_descargar("no-es-un-numero")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Numero de destino invalido", result.stdout)


class TestDescargarMultiToken(unittest.TestCase):
    def test_multi_token_falls_back_and_configures_cookies(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            home = tmp / "home"
            tokens = home / ".config" / "todus-lite" / "tokens"
            tokens.mkdir(parents=True)
            (tokens / "a.token").write_text("tokenA")
            (tokens / "b.token").write_text("tokenB")
            cookies = home / ".config" / "todus-lite" / "cookies.txt"
            cookies.write_text("# Netscape HTTP Cookie File\n")
            fakebin = tmp / "bin"
            fakebin.mkdir()
            gh = fakebin / "gh"
            gh.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = "api" ]; then\n'
                '  if [ "$2" = "user" ]; then\n'
                '    if [ "$GH_TOKEN" = "tokenA" ]; then echo accountA; else echo accountB; fi\n'
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                'if [ "$1 $2" = "codespace list" ]; then\n'
                '  if [ "$GH_TOKEN" = "tokenA" ]; then echo "[]"; '
                'else echo \'[{"name":"csB","state":"Available","repository":"Michel30006/todus-lite"}]\'; fi\n'
                "  exit 0\n"
                "fi\n"
                'if [ "$1 $2" = "codespace create" ]; then\n'
                '  echo "gh: billing issue (HTTP 402)" >&2\n'
                "  exit 1\n"
                "fi\n"
                "exit 0\n"
            )
            gh.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "HOME": str(home),
                "PATH": f"{fakebin}:{env['PATH']}",
                "TDS_GH_TOKEN_DIR": str(tokens),
                "TDS_COOKIES_FILE": str(cookies),
                "TDS_STALL_SECONDS": "3",
                "TODUS_SENDER": "58799457",
            })
            env.pop("GH_TOKEN", None)
            env.pop("TDS_GH_TOKEN_FILE", None)
            result = subprocess.run(
                ["bash", str(SCRIPT), "--remoto"],
                input="https://example.com/video.mp4\n360\n58548838\n",
                text=True,
                capture_output=True,
                env=env,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Cuenta GitHub: accountA", result.stdout)
            self.assertIn("no puede crear Codespaces por facturacion/cuota", result.stdout)
            self.assertIn("Cuenta GitHub: accountB", result.stdout)
            self.assertIn("Codespace listo: csB (accountB)", result.stdout)
            self.assertIn("Cookies y entorno remoto configurados.", result.stdout)
            self.assertIn("Borrando el video del Codespace...", result.stdout)
            self.assertIn("Parando el Codespace...", result.stdout)


if __name__ == "__main__":
    unittest.main()
