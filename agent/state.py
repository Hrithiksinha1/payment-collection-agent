from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class State(Enum):
    GREETING = "GREETING"
    ACCOUNT_LOOKUP = "ACCOUNT_LOOKUP"
    VERIFICATION = "VERIFICATION"
    PAYMENT_COLLECTION = "PAYMENT_COLLECTION"
    OUTCOME = "OUTCOME"
    TERMINATED = "TERMINATED"


@dataclass
class AgentContext:
    state: State = State.GREETING
    account: Optional[Dict[str, Any]] = None
    verified: bool = False
    retry_count: int = 0
    conversation: List[Dict[str, str]] = field(default_factory=list)
    collected: Dict[str, Any] = field(default_factory=dict)