"""
SVG Cleanup Node for ComfyUI
Post-processes SVG strings to optimize and clean up paths
"""

import re
import json
import numpy as np
from xml.etree import ElementTree as ET


class SVGPathCleanup:
    """
    Cleans up and optimizes SVG paths
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "svg_string": ("STRING", {"forceInput": True}),
                "remove_short_paths": ("BOOLEAN", {"default": True}),
                "min_path_length": ("FLOAT", {
                    "default": 5.0,
                    "min": 0.0,
                    "max": 100.0,
                    "step": 0.5,
                    "tooltip": "Remove paths shorter than this length"
                }),
                "merge_close_paths": ("BOOLEAN", {"default": True}),
                "merge_distance": ("FLOAT", {
                    "default": 2.0,
                    "min": 0.0,
                    "max": 20.0,
                    "step": 0.5,
                    "tooltip": "Merge paths if endpoints are within this distance"
                }),
                "simplify_paths": ("BOOLEAN", {"default": True}),
                "simplify_tolerance": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 5.0,
                    "step": 0.1,
                    "tooltip": "Path simplification tolerance"
                }),
                "remove_near_duplicate_paths": ("BOOLEAN", {"default": True}),
                "near_duplicate_distance": ("FLOAT", {
                    "default": 1.5,
                    "min": 0.0,
                    "max": 10.0,
                    "step": 0.1,
                    "tooltip": "Treat two paths as duplicates if their bidirectional average distance is below this threshold"
                }),
                "round_coordinates": ("BOOLEAN", {"default": True}),
                "decimal_places": ("INT", {
                    "default": 2,
                    "min": 0,
                    "max": 6,
                    "step": 1
                }),
            },
            "optional": {
                "remove_duplicate_paths": ("BOOLEAN", {"default": True}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("cleaned_svg", "statistics")
    FUNCTION = "cleanup_svg"
    CATEGORY = "TJ_Vector"
    OUTPUT_NODE = True
    
    def cleanup_svg(self, svg_string, remove_short_paths=True, min_path_length=5.0,
                   merge_close_paths=True, merge_distance=2.0, simplify_paths=True,
                   simplify_tolerance=0.5, remove_near_duplicate_paths=True,
                   near_duplicate_distance=1.5, round_coordinates=True, decimal_places=2,
                   remove_duplicate_paths=True):
        """
        Clean up SVG by removing short paths, merging close paths, and simplifying
        """
        try:
            # Parse SVG
            root = ET.fromstring(svg_string)
            
            # Find all path elements
            namespace = {'svg': 'http://www.w3.org/2000/svg'}
            paths = root.findall('.//svg:path', namespace)
            if not paths:
                paths = root.findall('.//path')
            
            original_count = len(paths)
            
            # Extract path data
            path_data_list = []
            for path in paths:
                d = path.get('d', '')
                if d:
                    path_data_list.append({
                        'element': path,
                        'd': d,
                        'stroke': path.get('stroke', '#000000'),
                        'points': self._parse_path_d(d)
                    })
            
            exact_before = len(path_data_list)
            # Step 1: Remove exact duplicate paths
            if remove_duplicate_paths:
                path_data_list = self._remove_duplicates(path_data_list)
            exact_removed = exact_before - len(path_data_list)
            
            # Step 2: Remove short paths
            if remove_short_paths:
                path_data_list = self._remove_short_paths(path_data_list, min_path_length)
            
            # Step 3: Simplify paths first to stabilize duplicate detection
            if simplify_paths:
                path_data_list = self._simplify_paths(path_data_list, simplify_tolerance)

            # Step 4: Remove near-duplicate overlapping paths
            near_removed = 0
            if remove_near_duplicate_paths:
                before_near = len(path_data_list)
                path_data_list = self._remove_near_duplicates(path_data_list, near_duplicate_distance)
                near_removed = before_near - len(path_data_list)

            # Step 5: Merge close paths (end-to-end joining)
            if merge_close_paths:
                path_data_list = self._merge_close_paths(path_data_list, merge_distance)
            
            # Step 6: Round coordinates
            if round_coordinates:
                path_data_list = self._round_coordinates(path_data_list, decimal_places)
            
            # Remove all old paths
            g_element = root.find('.//svg:g[@id="centerlines"]', namespace)
            if g_element is None:
                g_element = root.find('.//g[@id="centerlines"]')
            
            if g_element is not None:
                # Clear existing paths
                for path in list(g_element):
                    g_element.remove(path)
                
                # Add cleaned paths
                for i, path_data in enumerate(path_data_list):
                    new_path = ET.SubElement(g_element, 'path')
                    new_path.set('id', f'path{i}')
                    new_path.set('d', path_data['d'])
                    new_path.set('stroke', path_data['stroke'])
                    new_path.set('stroke-width', '2')
                    new_path.set('fill', 'none')
                    new_path.set('stroke-linecap', 'round')
                    new_path.set('stroke-linejoin', 'round')
            
            # Convert back to string
            cleaned_svg = ET.tostring(root, encoding='unicode')
            
            # Pretty print
            cleaned_svg = self._pretty_print_svg(cleaned_svg)
            
            # Generate statistics
            stats = {
                "original_path_count": original_count,
                "cleaned_path_count": len(path_data_list),
                "removed_paths": original_count - len(path_data_list),
                "operations": {
                    "remove_short_paths": remove_short_paths,
                    "merge_close_paths": merge_close_paths,
                    "simplify_paths": simplify_paths,
                    "remove_near_duplicate_paths": remove_near_duplicate_paths,
                    "round_coordinates": round_coordinates,
                    "remove_duplicate_paths": remove_duplicate_paths
                },
                "removed_detail": {
                    "exact_duplicates": int(exact_removed),
                    "near_duplicates": int(near_removed)
                }
            }
            
            stats_str = json.dumps(stats, indent=2)
            
            return (cleaned_svg, stats_str)
        
        except Exception as e:
            print(f"Error cleaning up SVG: {e}")
            return (svg_string, json.dumps({"error": str(e)}))
    
    def _parse_path_d(self, d):
        """
        Parse SVG path d attribute to extract points
        """
        points = []
        
        # Extract all numbers
        numbers = re.findall(r'[-+]?[0-9]*\.?[0-9]+', d)
        
        # Convert to float and group into coordinates
        for i in range(0, len(numbers) - 1, 2):
            x = float(numbers[i])
            y = float(numbers[i + 1])
            points.append([x, y])
        
        return np.array(points) if points else np.array([])
    
    def _calculate_path_length(self, points):
        """
        Calculate total path length
        """
        if len(points) < 2:
            return 0.0
        
        diffs = np.diff(points, axis=0)
        lengths = np.sqrt(np.sum(diffs**2, axis=1))
        return np.sum(lengths)
    
    def _remove_duplicates(self, path_data_list):
        """
        Remove duplicate paths
        """
        unique_paths = []
        seen_paths = set()
        
        for path_data in path_data_list:
            # Create a simple hash of the path
            if len(path_data['points']) > 0:
                path_hash = hash(path_data['points'].tobytes())
                
                if path_hash not in seen_paths:
                    seen_paths.add(path_hash)
                    unique_paths.append(path_data)
        
        return unique_paths

    def _resample_polyline(self, points, n_points=50):
        """
        Resample polyline to fixed number of points along arc length
        """
        if len(points) < 2:
            return points

        # cumulative lengths
        seg = np.diff(points, axis=0)
        seg_len = np.sqrt((seg**2).sum(axis=1))
        total = seg_len.sum()
        if total == 0:
            return np.repeat(points[:1], n_points, axis=0)

        cum = np.concatenate([[0.0], np.cumsum(seg_len)])
        target = np.linspace(0.0, total, n_points)

        resampled = []
        idx = 0
        for t in target:
            # advance idx to segment containing t
            while idx < len(seg_len) and cum[idx+1] < t:
                idx += 1
            if idx >= len(seg_len):
                resampled.append(points[-1])
                continue
            ratio = 0.0 if seg_len[idx] == 0 else (t - cum[idx]) / seg_len[idx]
            p = points[idx] + ratio * (points[idx+1] - points[idx])
            resampled.append(p)
        return np.asarray(resampled)

    def _bidirectional_mean_distance(self, A, B):
        """
        Compute bidirectional mean nearest-neighbor distance between two polylines.
        Returns (mean_dist, max_dist) using the better orientation (forward/reversed).
        """
        if len(A) == 0 or len(B) == 0:
            return np.inf, np.inf

        def nn_stats(P, Q):
            # pairwise distances using broadcasting
            d = P[:, None, :] - Q[None, :, :]
            d2 = np.sqrt((d**2).sum(axis=2))
            min_pq = d2.min(axis=1)
            min_qp = d2.min(axis=0)
            mean_val = (min_pq.mean() + min_qp.mean()) / 2.0
            max_val = max(min_pq.max(), min_qp.max())
            return mean_val, max_val

        m1, M1 = nn_stats(A, B)
        m2, M2 = nn_stats(A, B[::-1])
        if m2 < m1:
            return m2, M2
        return m1, M1

    def _remove_near_duplicates(self, path_data_list, distance_thresh):
        """
        Remove paths that closely overlap existing ones (near duplicates).
        Keep the longer path when two are near-duplicates.
        """
        if len(path_data_list) < 2:
            return path_data_list

        kept = []
        used = [False] * len(path_data_list)

        # Precompute resampled polylines and lengths
        resampled = []
        lengths = []
        for pd in path_data_list:
            pts = pd['points']
            res = self._resample_polyline(pts, n_points=min(80, max(10, len(pts))))
            resampled.append(res)
            lengths.append(self._calculate_path_length(pts))

        for i in range(len(path_data_list)):
            if used[i]:
                continue

            base = path_data_list[i]
            used[i] = True
            to_keep = base

            for j in range(i+1, len(path_data_list)):
                if used[j]:
                    continue
                mean_d, max_d = self._bidirectional_mean_distance(resampled[i], resampled[j])
                if mean_d <= distance_thresh and max_d <= distance_thresh * 2.5:
                    # treat as near duplicate; keep longer
                    if lengths[j] > lengths[path_data_list.index(to_keep)]:
                        to_keep = path_data_list[j]
                    used[j] = True

            kept.append(to_keep)

        # Recompute 'd' strings from points to ensure consistency
        out = []
        for pd in kept:
            out.append({
                'element': pd['element'],
                'd': self._points_to_path_d(pd['points']),
                'stroke': pd['stroke'],
                'points': pd['points']
            })
        return out
    
    def _remove_short_paths(self, path_data_list, min_length):
        """
        Remove paths shorter than min_length
        """
        filtered = []
        
        for path_data in path_data_list:
            points = path_data['points']
            if len(points) >= 2:
                length = self._calculate_path_length(points)
                if length >= min_length:
                    filtered.append(path_data)
        
        return filtered
    
    def _merge_close_paths(self, path_data_list, max_distance):
        """
        Merge paths whose endpoints are close together
        """
        if len(path_data_list) < 2:
            return path_data_list
        
        merged = []
        used = set()
        
        for i, path1 in enumerate(path_data_list):
            if i in used:
                continue
            
            points1 = path1['points']
            if len(points1) < 2:
                continue
            
            # Try to find a path to merge with
            merged_points = points1.copy()
            current_end = merged_points[-1]
            used.add(i)
            
            changed = True
            while changed:
                changed = False
                
                for j, path2 in enumerate(path_data_list):
                    if j in used or j == i:
                        continue
                    
                    points2 = path2['points']
                    if len(points2) < 2:
                        continue
                    
                    # Check if paths can be connected
                    dist_to_start = np.linalg.norm(current_end - points2[0])
                    dist_to_end = np.linalg.norm(current_end - points2[-1])
                    
                    if dist_to_start <= max_distance:
                        # Connect to start of path2
                        merged_points = np.vstack([merged_points, points2])
                        current_end = merged_points[-1]
                        used.add(j)
                        changed = True
                        break
                    elif dist_to_end <= max_distance:
                        # Connect to end of path2 (reversed)
                        merged_points = np.vstack([merged_points, points2[::-1]])
                        current_end = merged_points[-1]
                        used.add(j)
                        changed = True
                        break
            
            # Create merged path
            merged_d = self._points_to_path_d(merged_points)
            merged.append({
                'element': path1['element'],
                'd': merged_d,
                'stroke': path1['stroke'],
                'points': merged_points
            })
        
        return merged
    
    def _simplify_paths(self, path_data_list, tolerance):
        """
        Simplify paths using Douglas-Peucker algorithm
        """
        if tolerance <= 0:
            return path_data_list
        
        simplified = []
        
        for path_data in path_data_list:
            points = path_data['points']
            if len(points) < 3:
                simplified.append(path_data)
                continue
            
            # Douglas-Peucker simplification
            simplified_points = self._douglas_peucker(points, tolerance)
            
            if len(simplified_points) >= 2:
                simplified_d = self._points_to_path_d(simplified_points)
                simplified.append({
                    'element': path_data['element'],
                    'd': simplified_d,
                    'stroke': path_data['stroke'],
                    'points': simplified_points
                })
        
        return simplified
    
    def _douglas_peucker(self, points, tolerance):
        """
        Douglas-Peucker path simplification algorithm
        """
        if len(points) < 3:
            return points
        
        # Find the point with maximum distance
        start = points[0]
        end = points[-1]
        
        max_dist = 0
        max_idx = 0
        
        for i in range(1, len(points) - 1):
            dist = self._point_line_distance(points[i], start, end)
            if dist > max_dist:
                max_dist = dist
                max_idx = i
        
        # If max distance is greater than tolerance, recursively simplify
        if max_dist > tolerance:
            # Recursive call
            left = self._douglas_peucker(points[:max_idx + 1], tolerance)
            right = self._douglas_peucker(points[max_idx:], tolerance)
            
            # Combine (remove duplicate middle point)
            return np.vstack([left[:-1], right])
        else:
            # Return endpoints only
            return np.array([start, end])
    
    def _point_line_distance(self, point, line_start, line_end):
        """
        Calculate perpendicular distance from point to line
        """
        if np.allclose(line_start, line_end):
            return np.linalg.norm(point - line_start)
        
        # Vector from line_start to line_end
        line_vec = line_end - line_start
        line_len = np.linalg.norm(line_vec)
        line_unitvec = line_vec / line_len
        
        # Vector from line_start to point
        point_vec = point - line_start
        
        # Project point onto line
        projection_length = np.dot(point_vec, line_unitvec)
        
        if projection_length < 0:
            return np.linalg.norm(point - line_start)
        elif projection_length > line_len:
            return np.linalg.norm(point - line_end)
        else:
            projection = line_start + projection_length * line_unitvec
            return np.linalg.norm(point - projection)
    
    def _round_coordinates(self, path_data_list, decimal_places):
        """
        Round coordinates to specified decimal places
        """
        rounded = []
        
        for path_data in path_data_list:
            points = path_data['points']
            rounded_points = np.round(points, decimal_places)
            rounded_d = self._points_to_path_d(rounded_points)
            
            rounded.append({
                'element': path_data['element'],
                'd': rounded_d,
                'stroke': path_data['stroke'],
                'points': rounded_points
            })
        
        return rounded
    
    def _points_to_path_d(self, points):
        """
        Convert points array to SVG path d attribute
        """
        if len(points) == 0:
            return ""
        
        d_parts = [f"M {points[0][0]:.2f},{points[0][1]:.2f}"]
        
        for point in points[1:]:
            d_parts.append(f"L {point[0]:.2f},{point[1]:.2f}")
        
        return " ".join(d_parts)
    
    def _pretty_print_svg(self, svg_string):
        """
        Add proper indentation to SVG
        """
        # Simple pretty printing
        svg_string = svg_string.replace('><', '>\n<')
        return svg_string


NODE_CLASS_MAPPINGS = {
    "SVGPathCleanup": SVGPathCleanup
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SVGPathCleanup": "SVG Path Cleanup"
}
