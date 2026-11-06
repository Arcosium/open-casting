"""Keep local databases and session keys in private storage for every entry point."""
import os
from pathlib import Path


def runtime_directory():
    link = Path("data")
    if not link.exists() and not link.is_symlink():
        target = Path(os.getenv("OPEN_CASTING_RUNTIME_DIR", str(Path.home() / "vault/runtime/open-casting"))).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            link.symlink_to(target, target_is_directory=True)
        except FileExistsError:
            pass
    if not link.is_symlink() or not link.is_dir():
        raise RuntimeError("data must be a symlink to private runtime storage; existing data is never moved automatically")
    return link
