"""
SVG To Raster Node for ComfyUI
Converts SVG string to ComfyUI IMAGE tensor using CairoSVG
"""

import io
import json
from typing import Tuple, Optional
import numpy as np
import torch
from PIL import Image, ImageOps
from xml.etree import ElementTree as ET

try:
    import cairosvg  # type: ignore
except Exception as e:
    cairosvg = None


class SVGToImage:
    """
    Render an SVG string into a raster IMAGE tensor.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
                "width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1, "tooltip": "0=auto from SVG"}),
                "height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1, "tooltip": "0=auto from SVG"}),
                "scale": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 8.0, "step": 0.1}),
                "background": (["transparent", "white", "black", "custom"],),
                "background_color": ("STRING", {"default": "#00000000"}),
                "dpi": ("INT", {"default": 96, "min": 72, "max": 600, "step": 1}),
                "padding": ("INT", {"default": 0, "min": 0, "max": 512, "step": 1}),
            },
            "optional": {
                "antialias": ("BOOLEAN", {"default": True}),
                "clip_to_viewbox": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "meta")
    FUNCTION = "render"
    CATEGORY = "TJ_Vector"

    def render(self, svg_string: str, width: int = 0, height: int = 0, scale: float = 1.0,
               background: str = "transparent", background_color: str = "#00000000",
               dpi: int = 96, padding: int = 0, antialias: bool = True, clip_to_viewbox: bool = True):
        # Lazy import check
        if cairosvg is None:
            raise RuntimeError("cairosvg is not installed. Please install cairosvg and cairocffi.")

        # Compute base size from SVG
        base_w, base_h = self._infer_svg_size(svg_string)

        # Resolve target size
        tgt_w, tgt_h = self._resolve_size(base_w, base_h, width, height, scale)

        # Background handling
        bg_arg: Optional[str] = None
        if background == "white":
            bg_arg = "#FFFFFFFF"
        elif background == "black":
            bg_arg = "#000000FF"
        elif background == "custom":
            bg_arg = self._normalize_color(background_color)
        else:
            # transparent
            bg_arg = None

        # Render with CairoSVG to PNG bytes
        png_bytes = cairosvg.svg2png(
            bytestring=svg_string.encode("utf-8"),
            output_width=int(tgt_w),
            output_height=int(tgt_h),
            dpi=dpi,
            background_color=bg_arg,
            unsafe=True  # allow filters/fonts; assumes trusted input in workflow
        )

        # Load into PIL
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

        # Optional padding
        if padding > 0:
            pad_color = (0, 0, 0, 0) if background == "transparent" else self._parse_rgba(bg_arg or "#00000000")
            img = ImageOps.expand(img, border=padding, fill=pad_color)

        # Convert to tensor IMAGE (B,H,W,C) in 0..1
        arr = np.array(img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr).unsqueeze(0)

        meta = {
            "final_size": [int(img.width), int(img.height)],
            "base_size": [int(base_w), int(base_h)],
            "requested": {"width": int(width), "height": int(height), "scale": float(scale)},
            "dpi": int(dpi),
            "background": background,
            "background_color": bg_arg or "transparent",
            "padding": int(padding),
            "antialias": bool(antialias),
            "clip_to_viewbox": bool(clip_to_viewbox),
        }
        return (tensor, json.dumps(meta, indent=2))

    # ----- helpers -----
    def _infer_svg_size(self, svg: str) -> Tuple[int, int]:
        try:
            root = ET.fromstring(svg)
            w_attr = root.get("width")
            h_attr = root.get("height")
            vb = root.get("viewBox") or root.get("viewbox")

            def _parse_len(x):
                if x is None:
                    return None
                # remove units like px
                try:
                    return float(str(x).replace("px", "").strip())
                except:
                    return None

            w = _parse_len(w_attr)
            h = _parse_len(h_attr)
            if w and h:
                return int(round(w)), int(round(h))
            if vb:
                parts = [float(p) for p in vb.replace(",", " ").split()]
                if len(parts) == 4:
                    return int(round(parts[2])), int(round(parts[3]))
        except Exception:
            pass
        # fallback
        return 512, 512

    def _resolve_size(self, base_w: int, base_h: int, w: int, h: int, scale: float) -> Tuple[int, int]:
        if w > 0 and h > 0:
            return int(round(w * scale)), int(round(h * scale))
        if w > 0:
            return int(round(w * scale)), int(round((w * base_h / max(base_w, 1)) * scale))
        if h > 0:
            return int(round((h * base_w / max(base_h, 1)) * scale)), int(round(h * scale))
        return int(round(base_w * scale)), int(round(base_h * scale))

    def _normalize_color(self, s: str) -> str:
        s = (s or "").strip()
        if not s:
            return "#00000000"
        if s.startswith("#"):
            # Accept #RRGGBB or #RRGGBBAA
            if len(s) in (7, 9):
                return s
        # naive fallback: parse rgba(r,g,b,a)
        if s.startswith("rgba"):
            try:
                inside = s[s.find("(") + 1 : s.find(")")]
            except Exception:
                return "#00000000"
            parts = [p.strip() for p in inside.split(",")]
            if len(parts) == 4:
                r = max(0, min(255, int(float(parts[0]))))
                g = max(0, min(255, int(float(parts[1]))))
                b = max(0, min(255, int(float(parts[2]))))
                a = parts[3]
                if float(a) <= 1.0:
                    a = int(round(float(a) * 255))
                else:
                    a = int(round(float(a)))
                a = max(0, min(255, int(a)))
                return f"#{r:02X}{g:02X}{b:02X}{a:02X}"
        return s

    def _parse_rgba(self, s: str):
        # expects #RRGGBBAA
        s = (s or "#00000000").lstrip("#")
        if len(s) == 6:
            s += "FF"
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        a = int(s[6:8], 16)
        return (r, g, b, a)


NODE_CLASS_MAPPINGS = {
    "SVGToImage": SVGToImage
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGToImage": "SVG To Image"
}
