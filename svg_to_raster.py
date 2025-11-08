"""
SVG To Raster Node for ComfyUI
Converts SVG string to ComfyUI IMAGE tensor using Pillow (fallback renderer)
Note: Uses basic SVG path rendering; complex features may not render perfectly.
"""

import io
import json
import re
from typing import Tuple, Optional, List
import numpy as np
import torch
from PIL import Image, ImageOps, ImageDraw
from xml.etree import ElementTree as ET


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
                "override_stroke_color": ("STRING", {"default": "", "tooltip": "Override all stroke colors (hex: #RRGGBB or empty=use original)"}),
                "override_stroke_width": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 50.0, "step": 0.1, "tooltip": "Override stroke width (0=use original)"}),
                "override_fill_color": ("STRING", {"default": "", "tooltip": "Override all fill colors (hex: #RRGGBB or empty=use original)"}),
                "show_control_points": ("BOOLEAN", {"default": False, "tooltip": "Draw square markers at path control points"}),
                "control_point_size": ("INT", {"default": 4, "min": 1, "max": 20, "step": 1, "tooltip": "Size of control point markers"}),
                "control_point_color": ("STRING", {"default": "#FF0000", "tooltip": "Color of control point markers (hex: #RRGGBB)"}),
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
               dpi: int = 96, padding: int = 0, 
               override_stroke_color: str = "", override_stroke_width: float = 0.0, override_fill_color: str = "",
               show_control_points: bool = False, control_point_size: int = 4, control_point_color: str = "#FF0000",
               antialias: bool = True, clip_to_viewbox: bool = True):
        # Compute base size from SVG
        base_w, base_h = self._infer_svg_size(svg_string)

        # Resolve target size
        tgt_w, tgt_h = self._resolve_size(base_w, base_h, width, height, scale)

        # Render SVG using basic PIL-based path renderer
        try:
            img = self._render_svg_basic(svg_string, int(tgt_w), int(tgt_h), background, background_color,
                                         override_stroke_color, override_stroke_width, override_fill_color,
                                         show_control_points, control_point_size, control_point_color)
        except Exception as e:
            # Fallback: create error placeholder
            img = Image.new("RGBA", (int(tgt_w), int(tgt_h)), (255, 0, 0, 128))
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"SVG render error:\n{str(e)}", fill=(255, 255, 255, 255))
            print(f"SVG rendering error: {e}")

        # Optional padding
        if padding > 0:
            if background == "transparent":
                pad_color = (0, 0, 0, 0)
            elif background == "white":
                pad_color = (255, 255, 255, 255)
            elif background == "black":
                pad_color = (0, 0, 0, 255)
            else:
                pad_color = self._parse_rgba(self._normalize_color(background_color))
            img = ImageOps.expand(img, border=padding, fill=pad_color)

        # Convert to tensor IMAGE (B,H,W,C) in 0..1
        arr = np.array(img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr).unsqueeze(0)

        bg_str = background if background != "custom" else background_color
        meta = {
            "final_size": [int(img.width), int(img.height)],
            "base_size": [int(base_w), int(base_h)],
            "requested": {"width": int(width), "height": int(height), "scale": float(scale)},
            "dpi": int(dpi),
            "background": background,
            "background_color": bg_str,
            "padding": int(padding),
            "antialias": bool(antialias),
            "clip_to_viewbox": bool(clip_to_viewbox),
            "overrides": {
                "stroke_color": override_stroke_color if override_stroke_color else "original",
                "stroke_width": float(override_stroke_width) if override_stroke_width > 0 else "original",
                "fill_color": override_fill_color if override_fill_color else "original"
            },
            "control_points": {
                "enabled": bool(show_control_points),
                "size": int(control_point_size),
                "color": control_point_color
            }
        }
        return (tensor, json.dumps(meta, indent=2))

    # ----- helpers -----
    def _render_svg_basic(self, svg_string: str, width: int, height: int, background: str, bg_color: str,
                          override_stroke_color: str, override_stroke_width: float, override_fill_color: str,
                          show_control_points: bool, control_point_size: int, control_point_color: str) -> Image.Image:
        """
        Basic SVG path renderer using PIL ImageDraw.
        Limitations: Only supports simple path commands (M, L, C, Z); no complex styles/filters.
        """
        # Create canvas
        if background == "transparent":
            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        elif background == "white":
            img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        elif background == "black":
            img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        else:
            rgba = self._parse_rgba(self._normalize_color(bg_color))
            img = Image.new("RGBA", (width, height), rgba)
        
        draw = ImageDraw.Draw(img, "RGBA")
        
        # Parse SVG
        try:
            root = ET.fromstring(svg_string)
        except:
            return img  # return blank canvas on parse error
        
        # Get viewBox for coordinate transformation
        viewbox = root.get("viewBox") or root.get("viewbox")
        if viewbox:
            parts = [float(p) for p in viewbox.replace(",", " ").split()]
            if len(parts) == 4:
                vb_x, vb_y, vb_w, vb_h = parts
                scale_x = width / vb_w if vb_w > 0 else 1
                scale_y = height / vb_h if vb_h > 0 else 1
            else:
                scale_x = scale_y = 1
                vb_x = vb_y = 0
        else:
            scale_x = scale_y = 1
            vb_x = vb_y = 0
        
        # Extract and render <path> elements
        for path_elem in root.iter("{http://www.w3.org/2000/svg}path"):
            d = path_elem.get("d")
            if not d:
                continue
            
            # Parse stroke/fill
            stroke_color = path_elem.get("stroke", "black")
            fill_color = path_elem.get("fill", "none")
            stroke_width = float(path_elem.get("stroke-width", 1))
            
            # Apply overrides
            if override_stroke_color and override_stroke_color.strip():
                stroke_color = override_stroke_color.strip()
            if override_stroke_width > 0:
                stroke_width = override_stroke_width
            if override_fill_color and override_fill_color.strip():
                fill_color = override_fill_color.strip()
            
            # Convert path commands to coordinates
            coords = self._parse_svg_path(d, vb_x, vb_y, scale_x, scale_y)
            
            if not coords or len(coords) < 2:
                continue
            
            # Draw path
            if fill_color and fill_color.lower() != "none":
                fill_rgba = self._color_to_rgba(fill_color)
                if fill_rgba:
                    draw.polygon(coords, fill=fill_rgba)
            
            if stroke_color and stroke_color.lower() != "none":
                stroke_rgba = self._color_to_rgba(stroke_color)
                if stroke_rgba:
                    draw.line(coords, fill=stroke_rgba, width=int(stroke_width * scale_x))
            
            # Draw control points if enabled
            if show_control_points and coords:
                cp_rgba = self._color_to_rgba(control_point_color)
                if cp_rgba:
                    half_size = control_point_size // 2
                    for x, y in coords:
                        # Draw square marker
                        draw.rectangle(
                            [x - half_size, y - half_size, x + half_size, y + half_size],
                            fill=cp_rgba,
                            outline=cp_rgba
                        )
        
        return img
    
    def _parse_svg_path(self, d: str, offset_x: float, offset_y: float, scale_x: float, scale_y: float) -> List[Tuple[float, float]]:
        """
        Parse SVG path 'd' attribute into coordinate list.
        Supports: M (moveto), L (lineto), H/V (horizontal/vertical), C (cubic bezier), Z (closepath).
        """
        coords = []
        # Simple regex tokenizer
        tokens = re.findall(r'[MLHVCSQTAZmlhvcsqtaz]|[-+]?[0-9]*\.?[0-9]+', d)
        
        i = 0
        current_x = current_y = 0
        start_x = start_y = 0
        
        while i < len(tokens):
            cmd = tokens[i]
            i += 1
            
            if cmd.upper() == 'M':  # Move to
                if i < len(tokens):
                    x = float(tokens[i])
                    i += 1
                if i < len(tokens):
                    y = float(tokens[i])
                    i += 1
                current_x, current_y = x, y
                start_x, start_y = x, y
                coords.append(((current_x - offset_x) * scale_x, (current_y - offset_y) * scale_y))
                
            elif cmd.upper() == 'L':  # Line to
                if i < len(tokens):
                    x = float(tokens[i])
                    i += 1
                if i < len(tokens):
                    y = float(tokens[i])
                    i += 1
                current_x, current_y = x, y
                coords.append(((current_x - offset_x) * scale_x, (current_y - offset_y) * scale_y))
                
            elif cmd.upper() == 'H':  # Horizontal line
                if i < len(tokens):
                    x = float(tokens[i])
                    i += 1
                current_x = x
                coords.append(((current_x - offset_x) * scale_x, (current_y - offset_y) * scale_y))
                
            elif cmd.upper() == 'V':  # Vertical line
                if i < len(tokens):
                    y = float(tokens[i])
                    i += 1
                current_y = y
                coords.append(((current_x - offset_x) * scale_x, (current_y - offset_y) * scale_y))
                
            elif cmd.upper() == 'C':  # Cubic bezier (simplified: just use end point)
                if i + 5 < len(tokens):
                    i += 4  # skip control points
                    x = float(tokens[i])
                    i += 1
                    y = float(tokens[i])
                    i += 1
                    current_x, current_y = x, y
                    coords.append(((current_x - offset_x) * scale_x, (current_y - offset_y) * scale_y))
                    
            elif cmd.upper() == 'Z':  # Close path
                if start_x != current_x or start_y != current_y:
                    coords.append(((start_x - offset_x) * scale_x, (start_y - offset_y) * scale_y))
                current_x, current_y = start_x, start_y
                
        return coords
    
    def _color_to_rgba(self, color: str) -> Optional[Tuple[int, int, int, int]]:
        """Convert CSS color string to RGBA tuple."""
        if not color or color.lower() == "none":
            return None
        if color.startswith("#"):
            return self._parse_rgba(self._normalize_color(color))
        # Named colors (basic set)
        named = {
            "black": (0, 0, 0, 255), "white": (255, 255, 255, 255),
            "red": (255, 0, 0, 255), "green": (0, 128, 0, 255), "blue": (0, 0, 255, 255),
        }
        return named.get(color.lower(), (0, 0, 0, 255))
    
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
