"""Prepare private synthetic credentials and a free localhost port for Compose."""
import os
import secrets
import socket
from pathlib import Path


def prepare():
    root = Path(os.getenv("OPEN_CASTING_RUNTIME_DIR", str(Path.home() / "vault/runtime/open-casting")))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / 'm2-compose.env'
    link = Path('_workspace/compose.env')
    link.parent.mkdir(exist_ok=True)
    if not path.exists():
        for port in range(8900, 9000):
            with socket.socket() as sock:
                try:
                    sock.bind(('127.0.0.1', port))
                    break
                except OSError:
                    continue
        else:
            raise SystemExit('No free port in 8900-8999')
        path.write_text(f'POSTGRES_PASSWORD={secrets.token_hex(24)}\nSESSION_SECRET={secrets.token_hex(32)}\nAPP_PORT={port}\nRATE_LIMIT_IP=300\n')
        path.chmod(0o600)
    if not link.exists():
        link.symlink_to(path.resolve())
    print('Compose configuration ready: _workspace/compose.env (private symlink).')


if __name__ == '__main__':
    prepare()
