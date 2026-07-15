"""
Config loader - single JSON file, same idea as KlipperScreen's printer.cfg
but JSON since there's no Klipper config tree to piggyback on.
"""
import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "config.json")


class Config:
    def __init__(self, path=None):
        self.path = path or DEFAULT_PATH
        with open(self.path, "r") as f:
            self._data = json.load(f)

    def get(self, *keys, default=None):
        node = self._data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def set(self, value, *keys):
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
