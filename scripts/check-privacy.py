"""Check tracked deliverables; complements, does not replace secret scanning."""
import pathlib
import re
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
bad = []
patterns = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', r'gh[pousr]_[A-Za-z0-9]{30,}', r'github_pat_[A-Za-z0-9_]{40,}', r'sk-[A-Za-z0-9]{32,}']
for name in filter(None, paths):
    p = pathlib.PurePosixPath(name)
    if (p.parts[0] in {'runtime', 'data', 'logs', 'reports', '.venv'} or name.startswith('config/private/') or (p.name.startswith('.env') and p.name != '.env.example') or re.search(r'\.(?:db|sqlite3?)(?:-.*)?$',name)):
        bad.append(name)
    file = root / name
    if file.is_file():
        content = file.read_text(encoding='utf-8',errors='replace')
        if any(re.search(pattern,content) for pattern in patterns):
            bad.append(name)
if bad:
    raise SystemExit('Privacy check failed for paths: ' + ', '.join(sorted(set(bad))))
print('Tracked deliverables passed baseline privacy checks (submodule internals excluded).')
