import argparse
import json
from pathlib import Path
from .api import InstanceLock, make_server
from .service import Monitor

def main(argv=None):
    parser = argparse.ArgumentParser(description='Local public Bitget collector; no model or trading calls.')
    parser.add_argument('--runtime',default='runtime',help='Private state directory (default: runtime)')
    sub = parser.add_subparsers(dest='command',required=True)
    for command in ('serve','once','status','configure'):
        item = sub.add_parser(command)
        if command in ('serve','once','configure'): item.add_argument('--config',help='JSON file with an items array; omission preserves SQLite watchlist')
        if command == 'serve':
            item.add_argument('--port',type=int,default=8765)
            item.add_argument('--interval',type=int,default=60)
    args = parser.parse_args(argv)
    try:
        with InstanceLock(args.runtime):
            monitor = Monitor(args.runtime,poll_interval=getattr(args,'interval',60))
            try:
                if getattr(args,'config',None):
                    body = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
                    monitor.set_watchlist(body['items'])
                if args.command == 'serve':
                    server = make_server(monitor,args.port)
                    monitor.start()
                    print(f'Monitor listening on 127.0.0.1:{server.server_port}',flush=True)
                    try: server.serve_forever()
                    except KeyboardInterrupt: pass
                    finally: server.server_close()
                else:
                    if args.command == 'once': monitor.poll()
                    print(json.dumps(monitor.status(),ensure_ascii=False,indent=2))
            finally: monitor.close()
    except (ValueError,KeyError,OSError,RuntimeError):
        parser.exit(1,'Monitor failed: invalid configuration, unavailable runtime, or service already running.\n')

if __name__ == '__main__': main()
