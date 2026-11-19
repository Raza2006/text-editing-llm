"""Command line: python -m manager <command>."""
import glob
import os
import sys

from . import settings


def _cfg():
    cfg = dict(os.environ)
    cfg.update(settings.load(sorted(glob.glob("/config/*.env"))))
    return cfg


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "setup":
            from . import setup
            setup.run(_cfg(), "/models")
        elif cmd == "seed":
            from . import seed
            seed.main(_cfg())
        elif cmd in ("backup-loop", "backup-now", "restore"):
            from . import backup
            backup.main(cmd, argv[2:], _cfg())
        elif cmd == "loadtest":
            from . import loadtest
            return 0 if loadtest.main(argv[2:]) else 1
        else:
            print("Usage: python -m manager setup|seed|backup-loop|backup-now|restore <file>|loadtest")
            return 2
    except Exception as e:  # plain-English failure for the installer to show
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
