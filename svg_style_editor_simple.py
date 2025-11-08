"""
SVG Style Editor (Simple) Node for ComfyUI
Modifies stroke color, fill color, and stroke width of SVG paths by index number.
Simpler alternative to JSON-based SVGStyleEditor for use with SVGGroupLayout path numbering.

Inputs:
- svg_string: SVG XML string
- path_indices: Comma-separated path numbers (e.g., "0,1,5" or "0-5,10")
- stroke_color: Stroke color (#RRGGBB or color name)
- stroke_width: Stroke width (0 = no change)
- fill_color: Fill color (#RRGGBB or "none" or color name)
- opacity: Opacity (0.0-1.0, -1 = no change)

Outputs:
- STRING: Modified SVG XML
- STRING: Meta JSON with applied changes stats
"""

import json
import re
from typing import List, Set
from xml.etree import ElementTree as ET


class SVGStyleEditorSimple:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "path_indices": ("STRING", {
                    "default": "",
                    "tooltip": "Path numbers: 0,1,5 or 0-5 or mix like 0,2-4,10"
                }),
                "stroke_color": ("STRING", {
                    "default": "",
                    "tooltip": "Stroke color: #FF0000 or red (empty = no change)"
                }),
                "stroke_width": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 50.0,
                    "step": 0.1,
                    "tooltip": "Stroke width (0 = no change)"
                }),
                "fill_color": ("STRING", {
                    "default": "",
                    "tooltip": "Fill color: #00FF00 or none (empty = no change)"
                }),
                "opacity": ("FLOAT", {
                    "default": -1.0,
                    "min": -1.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "Opacity (-1 = no change)"
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("svg", "meta")
    FUNCTION = "edit_styles"
    CATEGORY = "TJ_Vector"

    def edit_styles(self,
                    svg_string: str,
                    path_indices: str = "",
                    stroke_color: str = "",
                    stroke_width: float = 0.0,
                    fill_color: str = "",
                    opacity: float = -1.0):
        # Parse SVG
        try:
            root = ET.fromstring(svg_string)
        except Exception as e:
            return (svg_string, json.dumps({"error": f"SVG parse error: {e}"}))

        # Parse path indices
        target_indices = self._parse_indices(path_indices)
        
        if not target_indices and path_indices.strip():
            # Invalid format
            return (svg_string, json.dumps({"error": "Invalid path_indices format"}))

        stats = {
            "target_indices": sorted(list(target_indices)) if target_indices else "all",
            "modified_count": 0
        }

        # Find all path elements
        ns_path = "{http://www.w3.org/2000/svg}path"
        all_paths = list(root.iter(ns_path))
        
        for idx, path_elem in enumerate(all_paths):
            # Check if this path should be modified
            if target_indices and idx not in target_indices:
                continue
            
            # Apply style changes
            modified = False
            
            if stroke_color and stroke_color.strip():
                path_elem.set("stroke", stroke_color.strip())
                modified = True
            
            if stroke_width > 0:
                path_elem.set("stroke-width", str(stroke_width))
                modified = True
            
            if fill_color and fill_color.strip():
                path_elem.set("fill", fill_color.strip())
                modified = True
            
            if opacity >= 0.0:
                path_elem.set("opacity", str(opacity))
                modified = True
            
            if modified:
                stats["modified_count"] += 1

        # Convert back to string
        output_svg = ET.tostring(root, encoding="unicode")
        
        return (output_svg, json.dumps(stats, indent=2))

    def _parse_indices(self, indices_str: str) -> Set[int]:
        """Parse comma-separated indices with range support (e.g., '0,2-5,10')"""
        if not indices_str or not indices_str.strip():
            return set()
        
        result = set()
        parts = indices_str.split(",")
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Check for range (e.g., "2-5")
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    start_idx = int(start.strip())
                    end_idx = int(end.strip())
                    result.update(range(start_idx, end_idx + 1))
                except ValueError:
                    continue
            else:
                # Single number
                try:
                    result.add(int(part))
                except ValueError:
                    continue
        
        return result


NODE_CLASS_MAPPINGS = {
    "SVGStyleEditorSimple": SVGStyleEditorSimple,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGStyleEditorSimple": "SVG Style Editor (Simple)",
}
