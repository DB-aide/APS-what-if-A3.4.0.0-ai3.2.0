import os
import sys

def is_android() -> bool:
    """
    Detecteer of we op Android draaien (incl. Termux).
    """
    return (
        sys.platform == "linux"
        and os.path.exists("/system/build.prop")
    )

def is_termux() -> bool:
    """
    Detecteer of we in Termux draaien.
    Betrouwbaar, ook bij debugpy / subprocess.
    """
    return (
        is_android()
        and os.path.isdir("/data/data/com.termux")
        and os.path.isdir("/data/data/com.termux/files/usr")
    )

def platform_info() -> dict[str, str | bool | None]:
    """
    Extra info voor debugging / logging.
    """
    return {
        "platform": sys.platform,
        "is_android": is_android(),
        "is_termux": is_termux(),
        "PREFIX": os.environ.get("PREFIX"),
        "TERMUX_VERSION": os.environ.get("TERMUX_VERSION"),
    }
