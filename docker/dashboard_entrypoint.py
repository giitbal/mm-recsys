"""Serve measured charts during model preparation and announce HTTP readiness."""
from __future__ import annotations

from src.common.console import log, run_cli

import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request


def wait_dashboard(process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'대시보드가 준비 전에 종료되었습니다: exit {process.returncode}')
        try:
            with opener.open('http://127.0.0.1:8501/_stcore/health', timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(min(.5, max(0, deadline - time.monotonic())))
    raise TimeoutError('대시보드 HTTP 준비 시간이 초과되었습니다')


def main() -> int:
    process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', 'dashboard/app.py',
                                '--server.port=8501', '--server.address=0.0.0.0',
                                '--browser.gatherUsageStats=false'], stdout=subprocess.PIPE)
    # Preserve stdout diagnostics without repeating Streamlit's startup banner.
    def save_stdout() -> None:
        if process.stdout is not None:
            with open('/tmp/streamlit-stdout.log', 'ab') as output:
                for line in process.stdout:
                    output.write(line)
                    output.flush()
    reader = threading.Thread(target=save_stdout, daemon=True)
    reader.start()
    previous = signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        wait_dashboard(process, 60)
        url = os.getenv('PUBLIC_DASHBOARD_URL', 'http://localhost:8501')
        log('대시보드', '시작', f'{url} 에서 대시보드 시작', status='성공')
        return process.wait()
    finally:
        signal.signal(signal.SIGTERM, previous)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        reader.join(timeout=5)


if __name__ == '__main__':
    raise SystemExit(run_cli(main, '대시보드', 'Streamlit 원본 로그와 대시보드 포트 설정을 확인하세요.'))
