import os, time, datetime
from contextlib import contextmanager

LOG_PATH = os.path.join(os.path.dirname(__file__), 'logs', 'tiempos_debug.log')

def _ensure_log_dir():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

def reset_log():
    _ensure_log_dir()
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('')

def _write_log(line: str):
    try:
        _ensure_log_dir()
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

@contextmanager
def measure(label: str, also_print: bool = True):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f'[{stamp}] [TIMER] {label}: {ms:.1f} ms'
        _write_log(line)
        if also_print:
            print(line)
