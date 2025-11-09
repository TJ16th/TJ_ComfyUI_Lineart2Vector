"""
SVG Auto Reorder Node for ComfyUI
Automatically reorders SVG paths based on area (large=background) and spatial proximity.

Sorting strategies:
- area_desc: Large paths first (backgrounds), small paths last (details)
- area_asc: Small paths first, large paths last
- proximity: Group nearby paths together using nearest-neighbor clustering
- area_then_proximity: Sort by area first, then group by proximity within size tiers

Inputs:
- svg_string: SVG XML string
- sort_mode: Sorting strategy
- reverse: Reverse final order

Outputs:
- STRING: Reordered SVG XML
- STRING: Meta JSON with path stats (area, position, new order)
"""

import json
import math
from typing import List, Tuple, Dict, Any
from xml.etree import ElementTree as ET


class SVGAutoReorder:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
                "sort_mode": ([
                    "area_desc",  # Large to small (backgrounds first)
                    "area_asc",   # Small to large
                    "proximity",  # Spatial clustering
                    "area_then_proximity"  # Area tiers, then proximity
                ], {"default": "area_then_proximity"}),
            },
            "optional": {
                "reverse": ("BOOLEAN", {"default": False, "tooltip": "Reverse final order"}),
                "area_tiers": ("INT", {"default": 3, "min": 1, "max": 10, "step": 1, 
                               "tooltip": "Number of area tiers for area_then_proximity mode"}),
                "renumber_ids": ("BOOLEAN", {"default": True, "tooltip": "Renumber path IDs as path0, path1, ... after reordering"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("svg", "meta")
    FUNCTION = "auto_reorder"
    CATEGORY = "TJ_Vector"

    def auto_reorder(self, svg_string: str, sort_mode: str = "area_then_proximity", 
                     reverse: bool = False, area_tiers: int = 3, renumber_ids: bool = True):
        # Parse SVG
        try:
            root = ET.fromstring(svg_string)
        except Exception as e:
            return (svg_string, json.dumps({"error": f"SVG parse error: {e}"}))

        # Find target parent (usually <g> or root)
        target_parent = None
        ns_g = "{http://www.w3.org/2000/svg}g"
        for child in root:
            if child.tag == ns_g or child.tag.endswith('}g'):
                target_parent = child
                break
        
        if target_parent is None:
            target_parent = root

        # Collect all path children with stats
        ns_path = "{http://www.w3.org/2000/svg}path"
        path_data = []
        
        for path_elem in list(target_parent):
            if not (path_elem.tag == ns_path or path_elem.tag.endswith('}path')):
                continue
            
            d = path_elem.get("d", "")
            if not d:
                continue
            
            # Calculate area and centroid
            area, centroid = self._calculate_path_stats(d)
            
            path_data.append({
                "element": path_elem,
                "area": area,
                "centroid": centroid,
                "id": path_elem.get("id", "")
            })

        if not path_data:
            return (svg_string, json.dumps({"info": "No paths found"}))

        # Sort based on mode
        if sort_mode == "area_desc":
            sorted_data = sorted(path_data, key=lambda x: x["area"], reverse=True)
        
        elif sort_mode == "area_asc":
            sorted_data = sorted(path_data, key=lambda x: x["area"], reverse=False)
        
        elif sort_mode == "proximity":
            sorted_data = self._sort_by_proximity(path_data)
        
        elif sort_mode == "area_then_proximity":
            sorted_data = self._sort_area_then_proximity(path_data, area_tiers)
        
        else:
            sorted_data = path_data

        if reverse:
            sorted_data = sorted_data[::-1]

        # Remove and re-add in new order
        for item in path_data:
            target_parent.remove(item["element"])
        
        for idx, item in enumerate(sorted_data):
            # Renumber IDs if requested
            if renumber_ids:
                item["element"].set("id", f"path{idx}")
            target_parent.append(item["element"])

        # Build stats
        stats = {
            "sort_mode": sort_mode,
            "renumber_ids": renumber_ids,
            "total_paths": len(sorted_data),
            "paths": []
        }
        
        for idx, item in enumerate(sorted_data):
            old_id = item["id"]
            new_id = f"path{idx}" if renumber_ids else old_id
            stats["paths"].append({
                "new_index": idx,
                "old_id": old_id,
                "new_id": new_id,
                "area": round(item["area"], 2),
                "centroid": [round(item["centroid"][0], 1), round(item["centroid"][1], 1)]
            })

        # Convert back to string
        output_svg = ET.tostring(root, encoding="unicode")
        
        return (output_svg, json.dumps(stats, indent=2))

    def _calculate_path_stats(self, d: str) -> Tuple[float, Tuple[float, float]]:
        """Calculate approximate area and centroid of a path"""
        # Simple polygon approximation: extract M/L/H/V coordinates
        coords = []
        tokens = d.replace(",", " ").split()
        x, y = 0.0, 0.0
        
        i = 0
        while i < len(tokens):
            token = tokens[i].strip()
            if not token:
                i += 1
                continue
            
            cmd = token[0] if token[0].isalpha() else None
            
            if cmd == 'M' or cmd == 'L':
                # Absolute move/line
                try:
                    x = float(token[1:] if len(token) > 1 else tokens[i + 1])
                    y = float(tokens[i + 2])
                    coords.append((x, y))
                    i += 3
                except (ValueError, IndexError):
                    i += 1
            
            elif cmd == 'm' or cmd == 'l':
                # Relative move/line
                try:
                    dx = float(token[1:] if len(token) > 1 else tokens[i + 1])
                    dy = float(tokens[i + 2])
                    x += dx
                    y += dy
                    coords.append((x, y))
                    i += 3
                except (ValueError, IndexError):
                    i += 1
            
            elif cmd == 'H':
                # Absolute horizontal
                try:
                    x = float(token[1:] if len(token) > 1 else tokens[i + 1])
                    coords.append((x, y))
                    i += 2
                except (ValueError, IndexError):
                    i += 1
            
            elif cmd == 'V':
                # Absolute vertical
                try:
                    y = float(token[1:] if len(token) > 1 else tokens[i + 1])
                    coords.append((x, y))
                    i += 2
                except (ValueError, IndexError):
                    i += 1
            
            elif cmd == 'C':
                # Cubic bezier - use endpoint
                try:
                    x = float(tokens[i + 5])
                    y = float(tokens[i + 6])
                    coords.append((x, y))
                    i += 7
                except (ValueError, IndexError):
                    i += 1
            
            elif cmd is None:
                # Implicit lineto continuation
                try:
                    x = float(token)
                    y = float(tokens[i + 1])
                    coords.append((x, y))
                    i += 2
                except (ValueError, IndexError):
                    i += 1
            
            else:
                i += 1

        if len(coords) < 3:
            # Not enough points for area calculation
            centroid = coords[0] if coords else (0.0, 0.0)
            return (0.0, centroid)

        # Calculate area using shoelace formula
        area = 0.0
        for i in range(len(coords)):
            x1, y1 = coords[i]
            x2, y2 = coords[(i + 1) % len(coords)]
            area += x1 * y2 - x2 * y1
        area = abs(area) / 2.0

        # Calculate centroid
        cx = sum(p[0] for p in coords) / len(coords)
        cy = sum(p[1] for p in coords) / len(coords)

        return (area, (cx, cy))

    def _distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """Euclidean distance between two points"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

    def _sort_by_proximity(self, path_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Nearest-neighbor clustering: pick closest unvisited path"""
        if not path_data:
            return []
        
        result = []
        remaining = path_data.copy()
        
        # Start with first path
        current = remaining.pop(0)
        result.append(current)
        
        while remaining:
            # Find nearest to current
            nearest = min(remaining, key=lambda p: self._distance(current["centroid"], p["centroid"]))
            remaining.remove(nearest)
            result.append(nearest)
            current = nearest
        
        return result

    def _sort_area_then_proximity(self, path_data: List[Dict[str, Any]], tiers: int) -> List[Dict[str, Any]]:
        """Sort by area into tiers, then by proximity within each tier"""
        if not path_data:
            return []
        
        # Sort by area first
        sorted_by_area = sorted(path_data, key=lambda x: x["area"], reverse=True)
        
        # Divide into tiers
        tier_size = max(1, len(sorted_by_area) // tiers)
        result = []
        
        for tier_idx in range(tiers):
            start = tier_idx * tier_size
            end = start + tier_size if tier_idx < tiers - 1 else len(sorted_by_area)
            tier_paths = sorted_by_area[start:end]
            
            if tier_paths:
                # Sort this tier by proximity
                tier_sorted = self._sort_by_proximity(tier_paths)
                result.extend(tier_sorted)
        
        return result


NODE_CLASS_MAPPINGS = {
    "SVGAutoReorder": SVGAutoReorder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGAutoReorder": "SVG Auto Reorder (Smart)",
}
