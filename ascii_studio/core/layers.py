"""Шари ASCII-канвасу: стек шарів + компонування (без Qt)."""
from __future__ import annotations


TRANSPARENT = {" ", "\u2800"}


def compose(layers):
    """Компонує видимі шари; вхід — знизу вгору, перший непрозорий символ перемагає."""
    rows = [layer.split("\n") for layer in layers if isinstance(layer, str)]
    height = max((len(r) for r in rows), default=0)
    out_lines = []
    for y in range(height):
        width = 0
        for r in rows:
            if y < len(r):
                width = max(width, len(r[y]))
        chars = []
        for x in range(width):
            ch = " "
            for r in reversed(rows):
                if y < len(r) and x < len(r[y]):
                    c = r[y][x]
                    if c not in TRANSPARENT:
                        ch = c
                        break
            chars.append(ch)
        out_lines.append("".join(chars).rstrip())
    return "\n".join(out_lines)


class Layer:
    """Один шар полотна."""

    def __init__(self, name: str = "", visible: bool = True, text: str = ""):
        self.name = name
        self.visible = visible
        self.text = text

    def to_dict(self) -> dict:
        return {"name": self.name, "visible": self.visible, "text": self.text}

    @classmethod
    def from_dict(cls, data: dict) -> "Layer":
        return cls(
            name=data.get("name", ""),
            visible=bool(data.get("visible", True)),
            text=data.get("text", ""),
        )


class CanvasLayers:
    """Стек шарів (список знизу вгору) + композит."""

    def __init__(self, layers=None):
        self._layers: list[Layer] = [
            l if isinstance(l, Layer) else Layer.from_dict(l) for l in (layers or [])
        ]

    @property
    def layers(self) -> list[Layer]:
        return self._layers

    def __len__(self) -> int:
        return len(self._layers)

    def __iter__(self):
        return iter(self._layers)

    def get(self, index: int) -> Layer:
        return self._layers[index]

    @property
    def count(self) -> int:
        return len(self._layers)

    def add_layer(self, name: str = "", index: int | None = None) -> Layer:
        layer = Layer(name=name)
        if index is None or index >= len(self._layers):
            self._layers.append(layer)
        else:
            self._layers.insert(index, layer)
        return layer

    def remove_layer(self, index: int):
        if 0 <= index < len(self._layers):
            self._layers.pop(index)

    def move(self, index: int, delta: int):
        target = index + delta
        if 0 <= index < len(self._layers) and 0 <= target < len(self._layers):
            layer = self._layers.pop(index)
            self._layers.insert(target, layer)

    def set_visible(self, index: int, visible: bool):
        if 0 <= index < len(self._layers):
            self._layers[index].visible = bool(visible)

    def rename(self, index: int, name: str):
        if 0 <= index < len(self._layers):
            self._layers[index].name = name

    def active_index(self) -> int:
        for i in range(len(self._layers) - 1, -1, -1):
            if self._layers[i].visible:
                return i
        return max(0, len(self._layers) - 1) if self._layers else 0

    def composite_text(self) -> str:
        return compose([l.text for l in self._layers if l.visible])

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "layers": [l.to_dict() for l in self._layers],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CanvasLayers":
        raw = data.get("layers", []) if isinstance(data, dict) else []
        layers = []
        for item in raw:
            if isinstance(item, dict):
                layers.append(Layer.from_dict(item))
        return cls(layers)
