import json
import os.path
import re
import signal
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from saarctf_commons.config import config


class ScriptRunner:
    @classmethod
    def run_script(cls, file: str, args: list[str], check: bool = True,
                   timeout: int = 10) -> subprocess.CompletedProcess:
        cmd: list[str] = [sys.executable, file] + args
        cwd = str(Path(__file__).absolute().parent.parent.parent)
        env = {k: v for k, v in os.environ.items()}
        env['METRICS_LOGFILE'] = '-'
        with TemporaryDirectory() as config_dir:
            (Path(config_dir) / 'config.json').write_text(json.dumps(config.to_dict()))
            env['SAARCTF_CONFIG'] = os.path.join(config_dir, 'config.json')
            process = subprocess.run(cmd, cwd=cwd, env=env, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                                     timeout=timeout)
            if check and process.returncode != 0:
                print(process.stdout.decode('utf-8'))
                print(process.stderr.decode('utf-8'))
                raise Exception(f'Process terminated with return code {process.returncode}')
            return process

    @classmethod
    def run_script_for_time(cls, file: str, args: list[str], duration: int = 3, check: bool = True,
                            timeout: int = 10) -> subprocess.CompletedProcess:
        cmd: list[str] = [sys.executable, file] + args
        cwd = str(Path(__file__).absolute().parent.parent.parent)
        env = {k: v for k, v in os.environ.items()}
        with TemporaryDirectory() as config_dir:
            (Path(config_dir) / 'config.json').write_text(json.dumps(config.to_dict()))
            env['SAARCTF_CONFIG'] = os.path.join(config_dir, 'config.json')
            with subprocess.Popen(cmd, cwd=cwd, env=env, stderr=subprocess.PIPE, stdout=subprocess.PIPE) as process:
                try:
                    stdout, stderr = process.communicate(timeout=duration)
                except subprocess.TimeoutExpired:
                    process.send_signal(signal.SIGINT)
                    try:
                        stdout, stderr = process.communicate(timeout=max(1, timeout - duration))
                    except subprocess.TimeoutExpired:
                        process.kill()
                        raise
                except:
                    process.kill()
                    raise
                rc = process.poll()
                if rc is None:
                    rc = 1337
                result = subprocess.CompletedProcess(process.args, rc, stdout, stderr)
            if check and result.returncode != 0:
                print(result.stdout.decode('utf-8'))
                print(result.stderr.decode('utf-8'))
                raise Exception(f'Process terminated with return code {result.returncode}')
            return result

    @classmethod
    def assert_no_exception(cls, r: subprocess.CompletedProcess) -> None:
        if b'Traceback' in r.stderr:
            print(r.stdout.decode('utf-8'))
            print(r.stderr.decode('utf-8'))
            assert b'Traceback' not in r.stderr

    @classmethod
    def parse_influx_format(cls, data: str) -> dict[str, list[dict[str, int | str]]]:
        result: dict[str, list[dict[str, int | str]]] = {}
        for line in data.split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.split(' ')
            parts1 = parts[0].split(',')
            parts2 = parts[1].split(',')
            assert len(parts) == 3
            if parts1[0] not in result:
                result[parts1[0]] = []
            result[parts1[0]].append({'time': int(parts[-1])} | dict(x.split('=', 1) for x in parts1[1:] + parts2))
        return result
