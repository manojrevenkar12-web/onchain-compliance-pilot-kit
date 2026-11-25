"""The analysts' alert queue. Analysts work office hours on weekdays; each alert costs minutes by how it was
routed. First in, first out, or by priority with a reserved slice for the fast lane."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(order=True)
class Item:
    sort: tuple[float, ...]
    key: str = field(compare=False)
    minutes: float = field(compare=False)
    lane: str = field(compare=False)


@dataclass
class Team:
    analysts: int
    minutes_per_day_each: float
    office_hours: tuple[int, int]

    def minutes_in_hour(self, hour: int) -> float:
        day, h = divmod(hour, 24)
        a, b = self.office_hours
        if day % 7 >= 5 or not a <= h < b:
            return 0.0
        return self.analysts * self.minutes_per_day_each / (b - a)

    def working_hours(self, start: int, end: int) -> int:
        """Office hours on weekdays in [start, end): how service levels are counted."""
        a, b = self.office_hours
        return sum(1 for h in range(start, end) if (h // 24) % 7 < 5 and a <= h % 24 < b)

    def minutes_per_calendar_day(self) -> float:
        return self.analysts * self.minutes_per_day_each * 5 / 7


class Queue:
    def __init__(self, order: str, fast_share: float = 0.15) -> None:
        self.order = order
        self.fast_share = fast_share
        self.items: list[Item] = []
        self.fast: list[Item] = []
        self.credit = 0.0
        self.fast_credit = 0.0

    def push(self, key: str, minutes: float, lane: str, arrival: int, rank: float = 0.0) -> None:
        if self.order == "priority" and lane == "fast":
            self.fast.append(Item((arrival,), key, minutes, lane))
            return
        sort = (arrival,) if self.order == "fifo" else ({"priority": 0, "normal": 1}.get(lane, 1), -rank, arrival)
        self.items.append(Item(sort, key, minutes, lane))

    def __len__(self) -> int:
        return len(self.items) + len(self.fast)

    def work(self, minutes: float) -> list[Item]:
        """Spend this hour's minutes; return what was finished."""
        done: list[Item] = []
        if minutes <= 0:
            return done
        if self.fast:
            self.fast_credit += minutes * self.fast_share
            minutes -= minutes * self.fast_share
            while self.fast and self.fast_credit >= self.fast[0].minutes:
                it = self.fast.pop(0)
                self.fast_credit -= it.minutes
                done.append(it)
        self.items.sort()
        self.credit += minutes + (self.fast_credit if not self.fast else 0.0)
        if not self.fast:
            self.fast_credit = 0.0
        while self.items and self.credit >= self.items[0].minutes:
            it = self.items.pop(0)
            self.credit -= it.minutes
            done.append(it)
        if not self.items:
            self.credit = min(self.credit, 60.0)
        return done
