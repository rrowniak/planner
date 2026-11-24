from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlannerError:
    message: str
    source: str = "project"
    path: str | None = None
    line: int | None = None
    column: int | None = None
    hint: str | None = None

    def to_dict(self) -> dict:
        return {
            key: value
            for key, value in {
                "message": self.message,
                "source": self.source,
                "path": self.path,
                "line": self.line,
                "column": self.column,
                "hint": self.hint,
            }.items()
            if value is not None
        }


class PlannerException(Exception):
    def __init__(self, errors: list[PlannerError]):
        super().__init__("; ".join(error.message for error in errors))
        self.errors = errors


def fail(message: str, **kwargs) -> None:
    raise PlannerException([PlannerError(message, **kwargs)])
