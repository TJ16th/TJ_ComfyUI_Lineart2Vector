"""
SVG Reorder Node for ComfyUI
Changes the drawing order (z-order) of SVG elements by reordering them in the XML tree.

Inputs:
- svg_string: SVG XML string
- order_rules_json: JSON array specifying desired order
  Example:
  [
    {"selector": "#background", "order": 0},
    {"selector": ".shadow", "order": 1},
    {"selector": "#path0", "order": 2},
    {"selector": "#path1", "order": 3}
  ]
  Elements not listed will appear after ordered elements in their original order.

Outputs:
- STRING: Modified SVG XML with reordered elements
- STRING: Meta JSON with reorder stats
"""

import json
from typing import List, Dict, Any, Optional
from xml.etree import ElementTree as ET


class SVGReorder:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "order_rules_json": ("STRING", {
                    "default": "[]",
                    "multiline": True,
                    "tooltip": "Array of {selector, order} to specify drawing order"
                }),
                "reverse_order": ("BOOLEAN", {"default": False, "tooltip": "Reverse entire order after applying rules"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("svg", "meta")
    FUNCTION = "reorder"
    CATEGORY = "TJ_Vector"

    def reorder(self, svg_string: str, order_rules_json: str = "[]", reverse_order: bool = False):
        # Parse SVG
        try:
            root = ET.fromstring(svg_string)
        except Exception as e:
            return (svg_string, json.dumps({"error": f"SVG parse error: {e}"}))

        # Parse rules
        rules: List[Dict[str, Any]] = []
        try:
            rules = json.loads(order_rules_json)
            if not isinstance(rules, list):
                rules = []
        except Exception:
            rules = []

        # Find the main group (usually <g id="centerlines"> or direct children of root)
        # Reorder within the first <g> if exists, otherwise reorder direct children
        target_parent = None
        ns_g = "{http://www.w3.org/2000/svg}g"
        for child in root:
            if child.tag == ns_g or child.tag.endswith('}g'):
                target_parent = child
                break
        
        if target_parent is None:
            # No group found, reorder direct children of root
            target_parent = root

        # Collect all children
        children = list(target_parent)
        
        # Create order map: element -> priority
        order_map: Dict[ET.Element, int] = {}
        stats = {"reordered_elements": 0, "rules_applied": 0}
        
        for rule in rules:
            selector = str(rule.get("selector", "")).strip()
            order = int(rule.get("order", 999))
            if not selector:
                continue
            
            # Find matching elements
            matched = self._find_elements_by_selector(root, selector)
            for elem in matched:
                if elem in children:
                    order_map[elem] = order
                    stats["rules_applied"] += 1
        
        # Sort children: ordered elements first (by order value), then unordered elements
        def sort_key(elem):
            if elem in order_map:
                return (0, order_map[elem])  # (priority_group, order)
            else:
                return (1, children.index(elem))  # Keep original order for unordered
        
        sorted_children = sorted(children, key=sort_key)
        
        if reverse_order:
            sorted_children = sorted_children[::-1]
        
        # Remove all children and re-add in new order
        for child in children:
            target_parent.remove(child)
        
        for child in sorted_children:
            target_parent.append(child)
        
        stats["reordered_elements"] = len(sorted_children)
        
        # Convert back to string
        output_svg = ET.tostring(root, encoding="unicode")
        
        return (output_svg, json.dumps(stats, indent=2))

    def _find_elements_by_selector(self, root: ET.Element, selector: str) -> List[ET.Element]:
        """Find all elements matching a simple selector"""
        results = []
        s = selector.strip()
        
        # ID selector: #id
        if s.startswith("#"):
            target_id = s[1:]
            for elem in root.iter():
                if elem.get("id") == target_id:
                    results.append(elem)
        
        # Class selector: .class
        elif s.startswith("."):
            target_class = s[1:]
            for elem in root.iter():
                classes = (elem.get("class") or "").split()
                if target_class in classes:
                    results.append(elem)
        
        # Tag selector: g, path, etc.
        elif s in ["g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text"]:
            ns_tag = f"{{http://www.w3.org/2000/svg}}{s}"
            for elem in root.iter():
                if elem.tag == ns_tag or elem.tag == s or elem.tag.endswith(f'}}{s}'):
                    results.append(elem)
        
        # Attribute contains selector: [attr*=value]
        elif s.startswith("[") and s.endswith("]") and "*=" in s:
            attr_part = s[1:-1]
            attr_name, attr_value = attr_part.split("*=", 1)
            attr_name = attr_name.strip()
            attr_value = attr_value.strip().strip('"').strip("'")
            for elem in root.iter():
                elem_value = elem.get(attr_name, "")
                if attr_value in elem_value:
                    results.append(elem)
        
        # Attribute equals selector: [attr=value]
        elif s.startswith("[") and s.endswith("]") and "=" in s and "*=" not in s:
            attr_part = s[1:-1]
            attr_name, attr_value = attr_part.split("=", 1)
            attr_name = attr_name.strip()
            attr_value = attr_value.strip().strip('"').strip("'")
            for elem in root.iter():
                if elem.get(attr_name) == attr_value:
                    results.append(elem)
        
        return results


NODE_CLASS_MAPPINGS = {
    "SVGReorder": SVGReorder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGReorder": "SVG Reorder Elements",
}
