"""
DAKU Remote Server Package
Provides the HTTP/REST API layer, authentication, health monitoring,
and remote agent coordination.
"""

from server.daku_server import DakuServer, create_server

__all__ = ["DakuServer", "create_server"]
