import copy

import numpy as np


class Channel:
    """
    Representation of one RPC3 channel.
    """

    def __init__(
        self,
        number: int,
        name: str = "",
        units: str = "",
        dt: float | None = None,
        scale: float = 1.0,
    ) -> None:
        self.number = number
        self.name = name
        self.units = units
        self.dt = dt
        self.values: np.ndarray = np.array([], dtype=np.float32)
        self.scale = scale

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str):
            raise ValueError("Channel name must be a string.")
        self._name = value

    @property
    def number(self) -> int:
        return self._number

    @number.setter
    def number(self, value: int) -> None:
        if value is not None and not isinstance(value, int):
            raise ValueError("Channel number must be an integer.")
        self._number = value

    @property
    def scale(self) -> float:
        return self._scale

    @scale.setter
    def scale(self, value: float) -> None:
        if not isinstance(value, (int, float)):
            raise ValueError("Channel scale must be numeric.")
        self._scale = float(value)

    def __len__(self) -> int:
        return int(self.values.size)

    def get_max(self) -> float:
        if self.values.size == 0:
            raise ValueError("No data available to determine the maximum value.")
        return float(self.values.max())

    def get_min(self) -> float:
        if self.values.size == 0:
            raise ValueError("No data available to determine the minimum value.")
        return float(self.values.min())

    def _apply_scale(self) -> None:
        self.values = self.values.astype(np.float32, copy=False)
        self.values *= self._scale

    def copy(self) -> "Channel":
        return copy.deepcopy(self)

    def plot(self, linewidth: float = 1.0) -> None:
        if self.dt is None or self.dt <= 0:
            raise ValueError("A positive dt is required before plotting.")
        if self.values.size == 0:
            raise ValueError("No data available for plotting.")

        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise ImportError("matplotlib is required for Channel.plot().") from exc

        time = np.arange(0, len(self.values) * self.dt, self.dt)
        plt.plot(time, self.values, linewidth=linewidth)
        plt.grid(True)
        plt.xlim(time.min(), time.max())
        plt.ylim(self.get_min(), self.get_max())
        plt.title(f"Channel {self.number}: {self.name}")
        plt.xlabel("Time [s]")
        plt.ylabel(self.units)
        plt.show()

    def __repr__(self) -> str:
        return (
            f"Channel(number={self.number}, name={self.name!r}, units={self.units!r}, "
            f"dt={self.dt}, samples={self.values.size})"
        )
