"""The `dt` ORBIT plugin: digital twins as a long-running service.

Importing this module registers the plugin (ORBIT auto-registers any
`Plugin` subclass carrying a `plugin_name`); the `radical.orbit.plugins`
entry point in `pyproject.toml` is what makes a broker or endpoint find
it without patching ORBIT.
"""

from .client import DTClient
from .plugin import PluginDT
from .session import DTSession, TwinInstance, ROLE_INFERENCE, ROLE_LEARNING
from .wire import Package, register_user_modules

__all__ = [
    "DTClient",
    "DTSession",
    "Package",
    "PluginDT",
    "TwinInstance",
    "register_user_modules",
    ROLE_INFERENCE,
    ROLE_LEARNING
]
