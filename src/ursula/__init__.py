"""Ursula — a library research capability for Virginia Tech University Libraries.

Three functions (`search`, `read`, `resolve`) over VT's discovery layer, institutional
repository, data repository and the open-access literature, normalized to one record
shape. Exposed as an HTTP service for NebulaONE and Open WebUI, and as an MCP server for
locally run agents.
"""

from .core import read, resolve, search
from .models import AccessRoute, Record

__version__ = "0.1.0"
__all__ = ["AccessRoute", "Record", "read", "resolve", "search"]
