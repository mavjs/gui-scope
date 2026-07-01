# backends/base.py — shared contract every OS backend must implement.
#
# gui_scope.py's dispatch() calls these private methods without knowing which
# backend is behind them. Keep signatures identical across backends so the
# JSON tool contract never changes per platform.

from abc import ABC, abstractmethod


class GUIScopeBackend(ABC):
    @abstractmethod
    def __init__(self, app_name: str, auto_launch: bool, timeout: int, launch_cmd: str | None = None):
        ...

    @abstractmethod
    def _get_tree(self, max_depth: int) -> dict:
        ...

    @abstractmethod
    def _find(self, role: str = None, title: str = None, description: str = None):
        ...

    @abstractmethod
    def _find_all(self, role: str = None, title: str = None, description: str = None) -> list:
        ...

    @abstractmethod
    def _click(self, role: str = None, title: str = None, description: str = None) -> str:
        ...

    @abstractmethod
    def _type_into(self, text: str, role: str = None, title: str = None, description: str = None) -> bool:
        ...

    @abstractmethod
    def _press_key(self, key: str) -> bool:
        ...

    @abstractmethod
    def _screenshot(self) -> bytes:
        ...

    def close(self) -> None:
        """Release any held resources (portal sessions, etc). No-op by default."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
