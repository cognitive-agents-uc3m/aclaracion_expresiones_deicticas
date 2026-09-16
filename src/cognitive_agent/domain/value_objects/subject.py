from __future__ import annotations

from enum import Enum

class Subject(str, Enum):
    GENERIC = "generic"
    STATISTICS = "statistics"
    SOFTWARE_ENGINEERING = "software_engineering"

    @property
    def display_name(self) -> str:
        return {
            Subject.GENERIC: "General",
            Subject.STATISTICS: "Estadistica",
            Subject.SOFTWARE_ENGINEERING: "Ingenieria del Software",
        }[self]

    @classmethod
    def parse(cls, raw: str | None) -> "Subject":

        if raw is None:
            return cls.GENERIC
        key = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
        legacy = {
            "estadistica": cls.STATISTICS,
            "estadística": cls.STATISTICS,
            "ingenieria_software": cls.SOFTWARE_ENGINEERING,
            "ingeniería_software": cls.SOFTWARE_ENGINEERING,
            "ingenieria_del_software": cls.SOFTWARE_ENGINEERING,
        }
        if key in legacy:
            return legacy[key]
        for member in cls:
            if member.value == key:
                return member
        return cls.GENERIC
