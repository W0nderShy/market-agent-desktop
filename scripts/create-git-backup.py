"""Create a self-contained Git snapshot without runtime data or credentials."""
import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT/'vendor'/'deepseek-harness'
DENY_PARTS = {'node_modules','.git','.venv','__pycache__','.pytest_cache'}
SECRET_PATTERNS = [
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(rb'sk-[A-Za-z0-9]{32,}'),
]


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd)


def source_files(repo):
    names = git('ls-files','--cached','--others','--exclude-standard','-z',cwd=repo).split(b'\0')
    return [pathlib.Path(raw.decode('utf-8','surrogateescape')) for raw in names if raw]


def included(relative):
    parts = relative.parts
    if not parts or any(part in DENY_PARTS for part in parts):return False
    if parts[0]=='runtime':return False
    if parts[:2] == ('config','private'):return False
    if relative.name.startswith('.env') and relative.name!='.env.example':return False
    if relative.suffix.lower() in {'.sqlite','.sqlite3','.db','.log','.pem','.key','.p12','.pfx'}:return False
    return True


def copy_sources(target):
    files=[]
    for relative in source_files(ROOT):
        if relative.as_posix() in ('.gitmodules','vendor/deepseek-harness'):continue
        if not included(relative):continue
        source=ROOT/relative
        if source.is_file():files.append((source,relative))
    for relative in source_files(VENDOR):
        destination=pathlib.Path('vendor')/'deepseek-harness'/relative
        if not included(destination):continue
        source=VENDOR/relative
        if source.is_file():files.append((source,destination))
    for source,relative in files:
        data=source.read_bytes()
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            raise RuntimeError(f'Potential secret in {relative}; backup not created')
    for source,relative in files:
        destination=target/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
    return len(files)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=pathlib.Path,help='New backup directory outside the project')
    args=parser.parse_args()
    stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    target=(args.output or ROOT.parent/f'AI_back_git_backup_{stamp}').resolve()
    if target==ROOT or ROOT in target.parents:raise SystemExit('Backup must be outside the live project')
    if target.exists():raise SystemExit(f'Backup already exists: {target}')
    target.mkdir(parents=True)
    count=copy_sources(target)
    info={'created_local':dt.datetime.now().astimezone().isoformat(),
          'source':str(ROOT),'source_commit':git('rev-parse','HEAD').decode().strip(),
          'dsh_commit':git('rev-parse','HEAD',cwd=VENDOR).decode().strip(),
          'files':count,'excluded':['runtime','config/private','.venv','node_modules','build outputs','Git metadata'],
          'layout':'Flattened source snapshot: vendor/deepseek-harness is a normal directory, not a submodule.'}
    (target/'BACKUP_INFO.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    git('init','-b','main',cwd=target)
    git('config','user.name','Local Backup',cwd=target)
    git('config','user.email','backup@local.invalid',cwd=target)
    git('add','--all',cwd=target)
    git('commit','-m','Snapshot market agent desktop with full DSH source',cwd=target)
    if git('status','--porcelain',cwd=target).strip():raise RuntimeError('Backup repository is not clean')
    git('fsck','--no-reflogs',cwd=target)
    bundle=target.with_suffix('.bundle')
    git('bundle','create',str(bundle),'--all',cwd=target)
    git('bundle','verify',str(bundle),cwd=target)
    archive=pathlib.Path(shutil.make_archive(str(target),'zip',root_dir=target.parent,base_dir=target.name))
    print(json.dumps({'directory':str(target),'zip':str(archive),'bundle':str(bundle),
                      'commit':git('rev-parse','HEAD',cwd=target).decode().strip(),'files':count},ensure_ascii=False))


if __name__=='__main__':main()
