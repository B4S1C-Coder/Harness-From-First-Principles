from dataclasses import dataclass

@dataclass(frozen=True, kw_only=True)
class VirtualFSReadLimits:
    max_bytes: int = 8 * 1024
    max_lines: int = 100

    def __post__init__(self) -> None:
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive.")

        if self.max_lines <= 0:
            raise ValueError("max_lines must be positive.")