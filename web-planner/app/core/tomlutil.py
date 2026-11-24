from __future__ import annotations

import re
import tomllib

from .errors import PlannerError, PlannerException

_LINE_COLUMN = re.compile(r"at line (\d+), column (\d+)")


def load_toml(text: str, source: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        line = getattr(exc, "lineno", None)
        column = getattr(exc, "colno", None)
        if line is None or column is None:
            match = _LINE_COLUMN.search(str(exc))
            if match:
                line, column = int(match.group(1)), int(match.group(2))
        raise PlannerException(
            [
                PlannerError(
                    str(exc),
                    source=source,
                    line=line,
                    column=column,
                )
            ]
        ) from exc
