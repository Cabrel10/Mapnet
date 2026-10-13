"""MapNet DOMAIN — Machine à états du cycle de vie d'une capture.

Une donnée géospatiale traverse un cycle strict, du terrain jusqu'au serveur :

    NEW -> LOCAL -> ENCRYPTED -> MESH_SHARED -> GATEWAY_UPLOADED
        -> SERVER_CONFIRMED -> ARCHIVED

Les transitions illégales sont refusées (InvalidTransition). Cela garantit
qu'une donnée ne peut pas, par exemple, être "confirmée serveur" sans être
passée par une passerelle. C'est une invariante métier forte.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List


class CaptureState(str, Enum):
    NEW = "NEW"
    LOCAL = "LOCAL"
    ENCRYPTED = "ENCRYPTED"
    MESH_SHARED = "MESH_SHARED"
    GATEWAY_UPLOADED = "GATEWAY_UPLOADED"
    SERVER_CONFIRMED = "SERVER_CONFIRMED"
    ARCHIVED = "ARCHIVED"


# Transitions autorisées. Le mesh est optionnel (LOCAL/ENCRYPTED peuvent
# monter directement à une passerelle si un peer mesh n'est pas trouvé).
_ALLOWED: Dict[CaptureState, List[CaptureState]] = {
    CaptureState.NEW: [CaptureState.LOCAL],
    CaptureState.LOCAL: [CaptureState.ENCRYPTED],
    CaptureState.ENCRYPTED: [CaptureState.MESH_SHARED, CaptureState.GATEWAY_UPLOADED],
    CaptureState.MESH_SHARED: [CaptureState.GATEWAY_UPLOADED],
    CaptureState.GATEWAY_UPLOADED: [CaptureState.SERVER_CONFIRMED],
    CaptureState.SERVER_CONFIRMED: [CaptureState.ARCHIVED],
    CaptureState.ARCHIVED: [],
}


class InvalidTransition(Exception):
    """Levée quand une transition d'état est interdite par la machine."""


class CaptureStateMachine:
    """Valide et applique les transitions d'état d'une capture."""

    def __init__(self, state: CaptureState = CaptureState.NEW):
        self.state = state
        self.history: List[CaptureState] = [state]

    def can_transition(self, target: CaptureState) -> bool:
        return target in _ALLOWED.get(self.state, [])

    def transition(self, target: CaptureState) -> "CaptureStateMachine":
        if not self.can_transition(target):
            raise InvalidTransition(
                f"Transition illégale : {self.state.value} -> {target.value}"
            )
        self.state = target
        self.history.append(target)
        return self

    @property
    def is_terminal(self) -> bool:
        return self.state == CaptureState.ARCHIVED

    def to_dict(self) -> Dict:
        return {
            "state": self.state.value,
            "history": [s.value for s in self.history],
            "is_terminal": self.is_terminal,
        }
