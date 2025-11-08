"""
SVG Group Layout Node for ComfyUI
Renders selected SVG groups (<g>) separately and places them on a canvas at given (x,y) positions.
Pure-Python renderer reuses the simple path drawing used in SVGToImage (Pillow-based).

Inputs:
- svg_string: SVG XML string
- canvas_width, canvas_height: output canvas size
- background: transparent/white/black/custom
- background_color: used when background=custom (#RRGGBB or #RRGGBBAA or rgba())
- group_positions_json: JSON array of placement rules
  Example:
  [
    {"selector": "#hair", "x": 100, "y": 80, "scale": 1.0, "rotate": 0.0,
     "stroke": "#000000", "stroke_width": 2.0, "fill": ""},
    {"selector": ".shadow", "x": 260, "y": 50, "opacity": 0.5}
  ]
- auto_layout: when no rules or empty, tile all top-level <g> groups into a grid
- tile_cols, tile_spacing: grid layout params

Outputs:
- IMAGE: Composite canvas
- STRING: meta JSON with match stats
"""

import json
import math
import re
from typing import List, Tuple, Optional, Dict, Any

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont
from xml.etree import ElementTree as ET


class SVGGroupLayout:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
                "canvas_width": ("INT", {"default": 1024, "min": 16, "max": 8192, "step": 1}),
                "canvas_height": ("INT", {"default": 1024, "min": 16, "max": 8192, "step": 1}),
                "background": (["transparent", "white", "black", "custom"],),
                "background_color": ("STRING", {"default": "#00000000"}),
            },
            "optional": {
                "group_positions_json": ("STRING", {"default": "[]", "multiline": True, "tooltip": "Array of {selector, x, y, scale?, rotate?, stroke?, stroke_width?, fill?, opacity?}"}),
                "auto_layout": ("BOOLEAN", {"default": True}),
                "tile_cols": ("INT", {"default": 4, "min": 1, "max": 32, "step": 1}),
                "tile_spacing": ("INT", {"default": 16, "min": 0, "max": 512, "step": 1}),
                "show_grid_lines": ("BOOLEAN", {"default": True}),
                "grid_line_color": ("STRING", {"default": "#CCCCCC"}),
                "grid_line_width": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
                "show_labels": ("BOOLEAN", {"default": True}),
                "label_color": ("STRING", {"default": "#000000"}),
                "label_size": ("INT", {"default": 12, "min": 6, "max": 48, "step": 1}),
                "show_control_points": ("BOOLEAN", {"default": False}),
                "control_point_size": ("INT", {"default": 3, "min": 1, "max": 20, "step": 1}),
                "control_point_color": ("STRING", {"default": "#00AEEF"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "meta")
    FUNCTION = "layout"
    CATEGORY = "TJ_Vector"

    def layout(self,
               svg_string: str,
               canvas_width: int = 1024,
               canvas_height: int = 1024,
               background: str = "transparent",
               background_color: str = "#00000000",
               group_positions_json: str = "[]",
               auto_layout: bool = True,
               tile_cols: int = 4,
               tile_spacing: int = 16,
               show_grid_lines: bool = True,
               grid_line_color: str = "#CCCCCC",
               grid_line_width: int = 1,
               show_labels: bool = True,
               label_color: str = "#000000",
               label_size: int = 12,
               show_control_points: bool = False,
               control_point_size: int = 3,
               control_point_color: str = "#00AEEF",
               ):
        # Parse SVG
        try:
            root = ET.fromstring(svg_string)
        except Exception as e:
            # return empty transparent canvas with error meta
            img = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
            tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0).unsqueeze(0)
            return (tensor, json.dumps({"error": f"SVG parse error: {e}"}))

        viewbox = root.get("viewBox") or root.get("viewbox")
        vb_x = vb_y = 0.0
        vb_w = canvas_width
        vb_h = canvas_height
        if viewbox:
            try:
                parts = [float(p) for p in viewbox.replace(",", " ").split()]
                if len(parts) == 4:
                    vb_x, vb_y, vb_w, vb_h = parts
            except Exception:
                pass

        # Prepare canvas
        if background == "transparent":
            canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        elif background == "white":
            canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
        elif background == "black":
            canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 255))
        else:
            canvas = Image.new("RGBA", (canvas_width, canvas_height), self._parse_rgba(self._normalize_color(background_color)))

        # Collect top-level groups
        top_groups = []  # [(elem, id, classes)]
        ns_tag = "{http://www.w3.org/2000/svg}g"
        for g in root.iter(ns_tag):
            # only consider groups that are direct or any depth? we'll include any depth but provide id/class
            gid = g.get("id") or ""
            cls = g.get("class") or ""
            top_groups.append((g, gid, cls))

        # Parse positions JSON
        placements: List[Dict[str, Any]] = []
        try:
            if group_positions_json and group_positions_json.strip():
                placements = json.loads(group_positions_json)
                if not isinstance(placements, list):
                    placements = []
        except Exception:
            placements = []

        # Auto layout if requested and no placements provided
        auto_used = False
        layout_items = []  # items to tile: list of (elem, id, cls)
        if (not placements) and auto_layout:
            # If <=1 group (or no groups), treat each <path> as individual item
            ns_path = "{http://www.w3.org/2000/svg}path"
            all_paths = list(root.iter(ns_path))
            if len(top_groups) <= 1 and len(all_paths) > 1:
                # Single/no group with many paths → tile each path
                for p in all_paths:
                    pid = p.get("id") or ""
                    pcls = p.get("class") or ""
                    layout_items.append((p, pid, pcls))
            elif top_groups:
                # Multiple groups → tile by group
                layout_items = top_groups
            
        if (not placements) and auto_layout and layout_items:
            auto_used = True
            cols = max(1, int(tile_cols))
            spacing = max(0, int(tile_spacing))
            cell_w = (canvas_width - spacing * (cols + 1)) / cols
            rows = math.ceil(len(layout_items) / cols)
            cell_h = (canvas_height - spacing * (rows + 1)) / max(1, rows)
            for idx, (_, gid, cls) in enumerate(layout_items):
                r = idx // cols
                c = idx % cols
                x = int(spacing + c * (cell_w + spacing))
                y = int(spacing + r * (cell_h + spacing))
                placements.append({
                    "selector": f"#{gid}" if gid else f".auto_{idx}",
                    "x": x,
                    "y": y,
                    "scale": min(cell_w / max(vb_w, 1), cell_h / max(vb_h, 1)),
                    "cell_index": idx,  # for label display
                })

        # Draw grid lines and labels for auto layout
        if auto_used and show_grid_lines:
            draw = ImageDraw.Draw(canvas, "RGBA")
            grid_rgba = self._color_to_rgba(grid_line_color, 1.0)
            if grid_rgba:
                cols = max(1, int(tile_cols))
                spacing = max(0, int(tile_spacing))
                cell_w = (canvas_width - spacing * (cols + 1)) / cols
                rows = math.ceil(len(layout_items) / cols)
                cell_h = (canvas_height - spacing * (rows + 1)) / max(1, rows)
                
                # Vertical lines (column separators)
                for c in range(cols + 1):
                    x = int(spacing + c * (cell_w + spacing))
                    draw.line([(x, 0), (x, canvas_height)], fill=grid_rgba, width=grid_line_width)
                
                # Horizontal lines (row separators)
                for r in range(rows + 1):
                    y = int(spacing + r * (cell_h + spacing))
                    draw.line([(0, y), (canvas_width, y)], fill=grid_rgba, width=grid_line_width)

        # Build index for selector resolution
        # Allow selectors: #id, .class, tag (g), [attr=value]
        def selector_match(elem: ET.Element, selector: str) -> bool:
            if not selector:
                return False
            s = selector.strip()
            if s.startswith("#"):
                return elem.get("id") == s[1:]
            if s.startswith("."):
                classes = (elem.get("class") or "").split()
                return s[1:] in classes
            if s == "g" or s.lower() == "group":
                return elem.tag.endswith('}g')
            # [attr=value]
            if s.startswith("[") and s.endswith("]") and "=" in s:
                k, v = s[1:-1].split("=", 1)
                return (elem.get(k) or "") == v
            return False

        # Helper: does path belong to any matching group for a selector
        def path_in_selector(path_elem: ET.Element, selector: str) -> bool:
            p = path_elem
            while p is not None:
                if selector_match(p, selector):
                    return True
                p = p.getparent() if hasattr(p, 'getparent') else None
                # xml.etree doesn't have getparent by default; emulate by walking from root
                if p is None:
                    # emulate: walk up by searching parent
                    p = _parent_of(root, path_elem) if selector_match(root, selector) else None
            return False

        def _parent_of(root_elem: ET.Element, child: ET.Element) -> Optional[ET.Element]:
            # simple DFS to find parent; acceptable for moderate SVG sizes
            stack = [root_elem]
            while stack:
                node = stack.pop()
                for ch in list(node):
                    if ch is child:
                        return node
                    stack.append(ch)
            return None

        # Render placements
        ns_path = "{http://www.w3.org/2000/svg}path"
        stats = {"placements": [], "auto_layout_used": auto_used}
        for rule in placements:
            selector = str(rule.get("selector", "")).strip()
            x = float(rule.get("x", 0))
            y = float(rule.get("y", 0))
            scale = float(rule.get("scale", 1.0))
            # style overrides per placement
            ov_stroke = rule.get("stroke", "")
            ov_sw = float(rule.get("stroke_width", 0) or 0)
            ov_fill = rule.get("fill", "")
            ov_opacity = float(rule.get("opacity", 1.0))

            drawn = 0
            draw = ImageDraw.Draw(canvas, "RGBA")

            # Iterate all paths; draw those under selector
            for path_elem in root.iter(ns_path):
                if selector and not self._path_in_group_by_selector(root, path_elem, selector):
                    continue
                d = path_elem.get("d")
                if not d:
                    continue
                stroke_color = ov_stroke or (path_elem.get("stroke") or "black")
                fill_color = ov_fill or (path_elem.get("fill") or "none")
                stroke_width = ov_sw if ov_sw > 0 else float(path_elem.get("stroke-width", 1) or 1)
                opacity = max(0.0, min(1.0, float(path_elem.get("opacity", ov_opacity))))

                coords = self._parse_svg_path(d, vb_x, vb_y, scale, scale)
                if not coords or len(coords) < 2:
                    continue
                # apply placement offset
                coords_off = [(x + px, y + py) for (px, py) in coords]

                # fill first
                if fill_color and fill_color.lower() != "none":
                    rgba = self._color_to_rgba(fill_color, opacity)
                    if rgba:
                        draw.polygon(coords_off, fill=rgba)
                # stroke
                if stroke_color and stroke_color.lower() != "none":
                    rgba = self._color_to_rgba(stroke_color, opacity)
                    if rgba:
                        draw.line(coords_off, fill=rgba, width=max(1, int(stroke_width * scale)))

                # optional control points
                if show_control_points:
                    cp_rgba = self._color_to_rgba(control_point_color, 1.0)
                    if cp_rgba:
                        half = max(1, int(control_point_size)) // 2
                        for (px, py) in coords_off:
                            draw.rectangle([px - half, py - half, px + half, py + half], fill=cp_rgba, outline=cp_rgba)

                drawn += 1

            stats["placements"].append({"selector": selector, "drawn_paths": drawn})

        # Draw labels (ID/index) for each placement
        if show_labels and placements:
            draw = ImageDraw.Draw(canvas, "RGBA")
            label_rgba = self._color_to_rgba(label_color, 1.0)
            if label_rgba:
                # Try to load a font, fallback to default
                try:
                    font = ImageFont.truetype("arial.ttf", label_size)
                except Exception:
                    try:
                        font = ImageFont.truetype("DejaVuSans.ttf", label_size)
                    except Exception:
                        font = ImageFont.load_default()
                
                for rule in placements:
                    selector = str(rule.get("selector", "")).strip()
                    x = int(rule.get("x", 0))
                    y = int(rule.get("y", 0))
                    
                    # Determine label text: show ID (without #) or cell index
                    if selector.startswith("#"):
                        label_text = selector[1:]  # Remove # prefix
                    elif "cell_index" in rule:
                        label_text = str(rule["cell_index"])
                    else:
                        label_text = selector if selector else "?"
                    
                    # Draw label at top-left corner of cell with padding
                    text_x = x + 2
                    text_y = y + 2
                    
                    # Draw text with slight shadow for readability
                    draw.text((text_x + 1, text_y + 1), label_text, fill=(0, 0, 0, 128), font=font)
                    draw.text((text_x, text_y), label_text, fill=label_rgba, font=font)

        # Convert to tensor
        arr = np.array(canvas).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr).unsqueeze(0)
        return (tensor, json.dumps(stats, indent=2))

    # -------- helpers (shared-style with svg_to_raster) --------
    def _element_matches_selector(self, elem: ET.Element, selector: str) -> bool:
        if not selector:
            return False
        s = selector.strip()
        if s.startswith("#"):
            return elem.get("id") == s[1:]
        if s.startswith("."):
            classes = (elem.get("class") or "").split()
            return s[1:] in classes
        if s == "g" or s.lower() == "group":
            return elem.tag.endswith('}g')
        if s.startswith("[") and s.endswith("]") and "=" in s:
            k, v = s[1:-1].split("=", 1)
            return (elem.get(k) or "") == v
        return False

    def _find_parent(self, root: ET.Element, child: ET.Element) -> Optional[ET.Element]:
        # xml.etree.ElementTree lacks getparent; do a DFS to find parent
        stack = [root]
        while stack:
            node = stack.pop()
            for ch in list(node):
                if ch is child:
                    return node
                stack.append(ch)
        return None

    def _path_in_group_by_selector(self, root: ET.Element, path_elem: ET.Element, selector: str) -> bool:
        # Return True if path_elem or any ancestor matches selector
        node: Optional[ET.Element] = path_elem
        visited = set()
        while node is not None and node not in visited:
            visited.add(node)
            if self._element_matches_selector(node, selector):
                return True
            node = self._find_parent(root, node)
        return False

    def _normalize_color(self, s: str) -> str:
        s = (s or "").strip()
        if not s:
            return "#00000000"
        if s.startswith("#"):
            if len(s) in (7, 9):
                return s
        if s.startswith("rgba"):
            try:
                inside = s[s.find("(") + 1 : s.find(")")]
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
            except Exception:
                return "#00000000"
        return s

    def _parse_rgba(self, s: str):
        s = (s or "#00000000").lstrip("#")
        if len(s) == 6:
            s += "FF"
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        a = int(s[6:8], 16)
        return (r, g, b, a)

    def _color_to_rgba(self, color: str, opacity: float = 1.0) -> Optional[Tuple[int, int, int, int]]:
        if not color or color.lower() == "none":
            return None
        if color.startswith("#"):
            r, g, b, a = self._parse_rgba(self._normalize_color(color))
            a = int(max(0, min(255, a * opacity))) if a > 1 else int(max(0, min(255, 255 * opacity)))
            return (r, g, b, a)
        named = {
            "black": (0, 0, 0, int(255 * opacity)),
            "white": (255, 255, 255, int(255 * opacity)),
            "red": (255, 0, 0, int(255 * opacity)),
            "green": (0, 128, 0, int(255 * opacity)),
            "blue": (0, 0, 255, int(255 * opacity)),
        }
        return named.get(color.lower(), (0, 0, 0, int(255 * opacity)))

    def _parse_svg_path(self, d: str, offset_x: float, offset_y: float, scale_x: float, scale_y: float) -> List[Tuple[float, float]]:
        coords = []
        tokens = re.findall(r'[MLHVCSQTAZmlhvcsqtaz]|[-+]?[0-9]*\.?[0-9]+', d)
        i = 0
        current_x = current_y = 0.0
        start_x = start_y = 0.0
        last_cmd = ''
        def abs_pt(x, y):
            return ((x - offset_x) * scale_x, (y - offset_y) * scale_y)
        while i < len(tokens):
            cmd = tokens[i]
            i += 1
            last_cmd = cmd
            rel = cmd.islower()
            cu = cmd.upper()
            if cu == 'M':
                x = float(tokens[i]); i += 1
                y = float(tokens[i]); i += 1
                if rel:
                    x += current_x; y += current_y
                current_x, current_y = x, y
                start_x, start_y = x, y
                coords.append(abs_pt(current_x, current_y))
            elif cu == 'L':
                x = float(tokens[i]); i += 1
                y = float(tokens[i]); i += 1
                if rel:
                    x += current_x; y += current_y
                current_x, current_y = x, y
                coords.append(abs_pt(current_x, current_y))
            elif cu == 'H':
                x = float(tokens[i]); i += 1
                if rel:
                    x += current_x
                current_x = x
                coords.append(abs_pt(current_x, current_y))
            elif cu == 'V':
                y = float(tokens[i]); i += 1
                if rel:
                    y += current_y
                current_y = y
                coords.append(abs_pt(current_x, current_y))
            elif cu == 'C':
                # cubic Bezier: (x1,y1,x2,y2,x,y) -> we sample end point only (simple)
                # For better quality, adaptive sampling can be added later
                i += 4  # skip control points (x1,y1,x2,y2)
                x = float(tokens[i]); i += 1
                y = float(tokens[i]); i += 1
                if rel:
                    x += current_x; y += current_y
                current_x, current_y = x, y
                coords.append(abs_pt(current_x, current_y))
            elif cu == 'Z':
                if start_x != current_x or start_y != current_y:
                    coords.append(abs_pt(start_x, start_y))
                current_x, current_y = start_x, start_y
        return coords


NODE_CLASS_MAPPINGS = {
    "SVGGroupLayout": SVGGroupLayout
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGGroupLayout": "SVG Group Layout"
}
