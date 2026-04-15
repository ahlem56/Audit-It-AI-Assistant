from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Common interface for all AI agents in the audit workflow."""

    @abstractmethod
    def run(self, input_data: Any) -> Any:
        """Execute the agent and return a serializable output."""
