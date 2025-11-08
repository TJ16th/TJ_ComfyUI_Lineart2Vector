"""
SVG Color Hex Output Node for ComfyUI
Outputs a normalized #RRGGBBAA color string for use in downstream SVG style editors.

Features:
- Accept raw input (hex #RGB, #RRGGBB, #RRGGBBAA, rgb()/rgba(), named colors)
- Sliders for R,G,B,A (0-255) override (if > -1)
- Optional preset dropdown (basic palette)
- Normalizes final output to #RRGGBBAA

Inputs:
- base_color (STRING)
- preset (CHOICE)
- r_override / g_override / b_override / a_override (INT -1 = no override)

Outputs:
- STRING (color_hex): Normalized #RRGGBBAA
- STRING (meta): JSON with parsed components
"""

import json
from typing import Tuple
from xml.etree import ElementTree as ET  # (kept for parity; not used directly)

class SVGColorPicker:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_color": ("STRING", {"default": "#FFFFFFFF", "multiline": False, "tooltip": "Input color (hex, rgba(), or name)"}),
            },
            "optional": {
                "preset": ([
                    "none",
                    "transparent",
                    "white",
                    "black",
                    "red",
                    "green",
                    "blue",
                    "yellow",
                    "cyan",
                    "magenta",
                    "gray"
                ], {"default": "none"}),
                "r_override": ("INT", {"default": -1, "min": -1, "max": 255, "step": 1}),
                "g_override": ("INT", {"default": -1, "min": -1, "max": 255, "step": 1}),
                "b_override": ("INT", {"default": -1, "min": -1, "max": 255, "step": 1}),
                "a_override": ("INT", {"default": -1, "min": -1, "max": 255, "step": 1, "tooltip": "Alpha 0-255 (-1 keeps parsed)"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("color_hex", "meta")
    FUNCTION = "make_color"
    CATEGORY = "TJ_Vector"

    def make_color(self,
                   base_color: str = "#FFFFFFFF",
                   preset: str = "none",
                   r_override: int = -1,
                   g_override: int = -1,
                   b_override: int = -1,
                   a_override: int = -1):
        # If preset selected, override base_color
        if preset != "none":
            base_color = self._preset_to_color(preset)

        r, g, b, a = self._parse_color(base_color)

        # Apply overrides if provided
        if r_override >= 0: r = self._clamp(r_override)
        if g_override >= 0: g = self._clamp(g_override)
        if b_override >= 0: b = self._clamp(b_override)
        if a_override >= 0: a = self._clamp(a_override)

        hex_out = f"#{r:02X}{g:02X}{b:02X}{a:02X}"
        meta = {
            "input": base_color,
            "preset": preset,
            "r": r,
            "g": g,
            "b": b,
            "a": a,
            "hex": hex_out
        }
        return (hex_out, json.dumps(meta, indent=2))

    # ----- helpers -----
    def _preset_to_color(self, name: str) -> str:
        mapping = {
            "transparent": "#00000000",
            "white": "#FFFFFFFF",
            "black": "#000000FF",
            "red": "#FF0000FF",
            "green": "#00FF00FF",
            "blue": "#0000FFFF",
            "yellow": "#FFFF00FF",
            "cyan": "#00FFFFFF",
            "magenta": "#FF00FFFF",
            "gray": "#808080FF",
        }
        return mapping.get(name, "#FFFFFFFF")

    def _parse_color(self, s: str) -> Tuple[int,int,int,int]:
        if not s:
            return (255,255,255,255)
        s = s.strip()
        # Hex forms
        if s.startswith('#'):
            h = s[1:]
            if len(h) == 3:  # RGB shorthand
                r = int(h[0]*2,16); g = int(h[1]*2,16); b = int(h[2]*2,16); a = 255
                return (r,g,b,a)
            if len(h) == 4:  # RGBA shorthand
                r = int(h[0]*2,16); g = int(h[1]*2,16); b = int(h[2]*2,16); a = int(h[3]*2,16)
                return (r,g,b,a)
            if len(h) == 6:  # RRGGBB
                r = int(h[0:2],16); g = int(h[2:4],16); b = int(h[4:6],16); a = 255
                return (r,g,b,a)
            if len(h) == 8:  # RRGGBBAA
                r = int(h[0:2],16); g = int(h[2:4],16); b = int(h[4:6],16); a = int(h[6:8],16)
                return (r,g,b,a)
        # rgba() or rgb()
        if s.lower().startswith('rgb'):
            import re
            m = re.match(r'rgba?\(([^)]+)\)', s, re.IGNORECASE)
            if m:
                parts = [p.strip() for p in m.group(1).split(',')]
                if len(parts) >= 3:
                    try:
                        r = int(float(parts[0])); g = int(float(parts[1])); b = int(float(parts[2]))
                        a = 255
                        if len(parts) >= 4:
                            alpha = float(parts[3])
                            if alpha <= 1.0: alpha *= 255
                            a = int(alpha)
                        return (self._clamp(r), self._clamp(g), self._clamp(b), self._clamp(a))
                    except ValueError:
                        pass
        # Named colors fallback via simple mapping
        named = {
            'red': (255,0,0,255),
            'green': (0,255,0,255),
            'blue': (0,0,255,255),
            'black': (0,0,0,255),
            'white': (255,255,255,255),
            'yellow': (255,255,0,255),
            'cyan': (0,255,255,255),
            'magenta': (255,0,255,255),
            'gray': (128,128,128,255),
            'transparent': (0,0,0,0)
        }
        return named.get(s.lower(), (255,255,255,255))

    def _clamp(self, v: int) -> int:
        return max(0, min(255, int(v)))


NODE_CLASS_MAPPINGS = {
    "SVGColorPicker": SVGColorPicker,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGColorPicker": "SVG Color Picker",
}
