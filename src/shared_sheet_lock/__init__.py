"""Safe shared access to an .xlsx workbook for two agents or machines."""
from .core import AddResult, LockError, SharedSheet
from .normalize import normalize_domain, normalize_name, normalize_phone

__all__ = [
    "AddResult", "LockError", "SharedSheet",
    "normalize_domain", "normalize_name", "normalize_phone",
]
__version__ = "0.1.0"
