"""Shared in-memory models for PLANET and NSMA antenna patterns."""

from dataclasses import dataclass, field


@dataclass
class PatternCut:
    """A single radiation-pattern cut containing ``(angle, level_db)`` points.

    ``source_name`` retains the originating format's name, while ``axis`` is
    the NSMA cut designator (H, V, AZ, or EL).
    """

    source_name: str
    axis: str
    points: list[tuple[float, float]] = field(default_factory=list)

    @property
    def first_angle(self):
        """Return the first angle in degrees, or ``None`` for an empty cut."""

        return self.points[0][0] if self.points else None

    @property
    def last_angle(self):
        """Return the last angle in degrees, or ``None`` for an empty cut."""

        return self.points[-1][0] if self.points else None


@dataclass
class AntennaPattern:
    """Antenna metadata and its ordered collection of pattern cuts."""

    fields: dict[str, str] = field(default_factory=dict)
    cuts: list[PatternCut] = field(default_factory=list)
