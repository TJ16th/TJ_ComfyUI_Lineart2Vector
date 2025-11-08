"""
Centerline to SVG Node for ComfyUI
Extracts centerlines from line masks and generates SVG paths
"""

import numpy as np
import torch
import cv2
from scipy import ndimage
from scipy.interpolate import splprep, splev
from skimage.morphology import medial_axis, skeletonize
import json
from datetime import datetime


class CenterlineToSVG:
    """
    Extracts centerlines from line masks and generates SVG paths
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "line_mask": ("MASK",),
                "algorithm": (["ridge", "skeleton", "medial_axis"],),
                "smoothing": ("FLOAT", {
                    "default": 2.0,
                    "min": 0.0,
                    "max": 10.0,
                    "step": 0.1
                }),
                "min_path_length": ("INT", {
                    "default": 10,
                    "min": 1,
                    "max": 1000,
                    "step": 1
                }),
                "simplify_tolerance": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 10.0,
                    "step": 0.1
                }),
                "bezier_smoothing": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "original_image": ("IMAGE",),
                "color_info": ("STRING", {"default": ""}),
                "preserve_colors": ("BOOLEAN", {"default": True}),
            }
        }
    
    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("svg_string", "centerline_image", "statistics")
    FUNCTION = "generate_svg"
    CATEGORY = "TJ_Vector"
    OUTPUT_NODE = True
    
    def generate_svg(self, line_mask, algorithm="ridge", smoothing=2.0, 
                    min_path_length=10, simplify_tolerance=1.0, bezier_smoothing=True,
                    original_image=None, color_info="", preserve_colors=True):
        """
        Main function to generate SVG from line mask
        """
        # Convert mask to numpy
        mask_np = line_mask[0].cpu().numpy()
        mask_255 = (mask_np * 255).astype(np.uint8)
        
        height, width = mask_255.shape
        
        # Step 1: Extract centerline
        centerline = self._extract_centerline(mask_255, algorithm)
        
        # Step 2: Generate paths from centerline
        paths = self._extract_paths(centerline, min_path_length)
        
        # Step 3: Simplify paths
        simplified_paths = self._simplify_paths(paths, simplify_tolerance)
        
        # Step 4: Smooth paths
        if bezier_smoothing:
            smoothed_paths = self._smooth_paths(simplified_paths, smoothing)
        else:
            smoothed_paths = simplified_paths
        
        # Step 5: Extract colors (optional)
        path_colors = self._get_path_colors(
            smoothed_paths, original_image, color_info, preserve_colors
        )
        
        # Step 6: Generate SVG
        svg_string = self._generate_svg_string(
            smoothed_paths, path_colors, width, height
        )
        
        # Step 7: Create preview
        preview_image = self._create_centerline_preview(
            centerline, smoothed_paths, width, height
        )
        preview_tensor = torch.from_numpy(preview_image.astype(np.float32) / 255.0).unsqueeze(0)
        
        # Step 8: Generate statistics
        statistics = self._generate_statistics(
            smoothed_paths, path_colors, width, height, algorithm
        )
        statistics_str = json.dumps(statistics, indent=2)
        
        return (svg_string, preview_tensor, statistics_str)
    
    def _extract_centerline(self, mask, algorithm):
        """
        Extract centerline using specified algorithm
        """
        if np.sum(mask > 127) == 0:
            return np.zeros_like(mask)
        
        if algorithm == "skeleton":
            return self._skeleton_method(mask)
        elif algorithm == "medial_axis":
            return self._medial_axis_method(mask)
        elif algorithm == "ridge":
            return self._ridge_detection_method(mask)
        
        return mask
    
    def _skeleton_method(self, mask):
        """
        Zhang-Suen thinning algorithm
        """
        binary = mask > 127
        skeleton = skeletonize(binary)
        return (skeleton * 255).astype(np.uint8)
    
    def _medial_axis_method(self, mask):
        """
        Medial axis transform (more accurate for thick lines)
        """
        binary = mask > 127
        skel, distance = medial_axis(binary, return_distance=True)
        
        # Filter by distance to remove noise
        if np.any(distance > 0):
            threshold = np.percentile(distance[distance > 0], 10)
            skel_filtered = skel & (distance > threshold)
            return (skel_filtered * 255).astype(np.uint8)
        
        return (skel * 255).astype(np.uint8)
    
    def _ridge_detection_method(self, mask):
        """
        Ridge detection using distance transform
        """
        binary = mask > 127
        
        # Distance transform
        dist_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        
        # Normalize
        if np.max(dist_transform) > 0:
            dist_norm = dist_transform / np.max(dist_transform)
        else:
            dist_norm = dist_transform
        
        # Detect local maxima (ridges)
        # Use morphological gradient to find ridges
        kernel = np.ones((3, 3), np.uint8)
        
        # Dilate and erode to find local maxima
        dilated = cv2.dilate(dist_norm, kernel, iterations=1)
        ridge = (dist_norm == dilated) & (dist_norm > 0.1)
        
        # Thin the ridge using skimage skeletonize
        ridge_uint8 = (ridge * 255).astype(np.uint8)
        ridge_bool = ridge_uint8 > 127
        thinned = skeletonize(ridge_bool)
        
        return (thinned * 255).astype(np.uint8)
    
    def _extract_paths(self, centerline, min_length):
        """
        Extract individual paths from centerline
        """
        # Find contours
        contours, _ = cv2.findContours(centerline, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        
        paths = []
        for contour in contours:
            if len(contour) >= min_length:
                # Convert to simple point list
                points = contour.squeeze()
                if len(points.shape) == 1:
                    points = points.reshape(1, -1)
                paths.append(points)
        
        return paths
    
    def _simplify_paths(self, paths, tolerance):
        """
        Simplify paths using Douglas-Peucker algorithm
        """
        if tolerance <= 0:
            return paths
        
        simplified = []
        for path in paths:
            # Reshape for cv2.approxPolyDP
            path_reshaped = path.reshape(-1, 1, 2).astype(np.float32)
            approx = cv2.approxPolyDP(path_reshaped, tolerance, closed=False)
            simplified_path = approx.squeeze()
            
            if len(simplified_path.shape) == 1:
                simplified_path = simplified_path.reshape(1, -1)
            
            if len(simplified_path) >= 2:
                simplified.append(simplified_path)
        
        return simplified
    
    def _smooth_paths(self, paths, smoothing):
        """
        Smooth paths using spline interpolation
        """
        if smoothing <= 0:
            return paths
        
        smoothed = []
        for path in paths:
            if len(path) < 4:
                smoothed.append(path)
                continue
            
            try:
                # Parametric spline interpolation
                x = path[:, 0]
                y = path[:, 1]
                
                # Remove duplicate points
                unique_indices = np.where(np.sum(np.abs(np.diff(path, axis=0)), axis=1) > 0)[0]
                if len(unique_indices) < 3:
                    smoothed.append(path)
                    continue
                
                unique_indices = np.concatenate([[0], unique_indices + 1])
                x_unique = x[unique_indices]
                y_unique = y[unique_indices]
                
                if len(x_unique) < 4:
                    smoothed.append(path)
                    continue
                
                # Fit spline
                tck, u = splprep([x_unique, y_unique], s=smoothing * len(x_unique), k=min(3, len(x_unique) - 1))
                
                # Generate smooth curve
                u_new = np.linspace(0, 1, len(path))
                x_new, y_new = splev(u_new, tck)
                
                smooth_path = np.column_stack([x_new, y_new])
                smoothed.append(smooth_path)
            except Exception as e:
                # If smoothing fails, use original path
                smoothed.append(path)
        
        return smoothed
    
    def _get_path_colors(self, paths, original_image, color_info, preserve_colors):
        """
        Get colors for each path
        """
        if not preserve_colors or original_image is None:
            return ["#000000"] * len(paths)
        
        # Convert image to numpy
        img_np = original_image[0].cpu().numpy()
        img_255 = (img_np * 255).astype(np.uint8)
        
        colors = []
        for path in paths:
            # Sample color from middle of path
            mid_idx = len(path) // 2
            x, y = path[mid_idx].astype(int)
            
            # Clamp coordinates
            y = max(0, min(y, img_255.shape[0] - 1))
            x = max(0, min(x, img_255.shape[1] - 1))
            
            # Get color
            if len(img_255.shape) >= 3:
                r, g, b = img_255[y, x, :3]
            else:
                r = g = b = img_255[y, x]
            
            hex_color = "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))
            colors.append(hex_color)
        
        return colors
    
    def _generate_svg_string(self, paths, colors, width, height):
        """
        Generate SVG string from paths
        """
        timestamp = datetime.now().isoformat()
        
        svg_lines = [
            f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
            '  <metadata>',
            f'    <created>{timestamp}</created>',
            '    <generator>tj_comfyui_centerVector v1.0</generator>',
            '  </metadata>',
            '  <g id="centerlines">',
        ]
        
        for i, (path, color) in enumerate(zip(paths, colors)):
            svg_path = self._path_to_svg_d(path)
            svg_lines.append(
                f'    <path id="path{i}" d="{svg_path}" '
                f'stroke="{color}" stroke-width="2" '
                f'fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        
        svg_lines.append('  </g>')
        svg_lines.append('</svg>')
        
        return '\n'.join(svg_lines)
    
    def _path_to_svg_d(self, path):
        """
        Convert path points to SVG d attribute
        """
        if len(path) == 0:
            return ""
        
        # Start with Move command
        d_parts = [f"M {path[0][0]:.2f},{path[0][1]:.2f}"]
        
        # Add Line commands for remaining points
        for point in path[1:]:
            d_parts.append(f"L {point[0]:.2f},{point[1]:.2f}")
        
        return " ".join(d_parts)
    
    def _create_centerline_preview(self, centerline, paths, width, height):
        """
        Create preview image of centerlines
        """
        preview = np.zeros((height, width, 3), dtype=np.uint8)
        preview.fill(255)  # White background
        
        # Draw original centerline in light gray
        preview[centerline > 127] = [200, 200, 200]
        
        # Draw paths in different colors
        colors = [
            (255, 0, 0),    # Red
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
        ]
        
        for i, path in enumerate(paths):
            color = colors[i % len(colors)]
            path_int = path.astype(np.int32)
            cv2.polylines(preview, [path_int], False, color, 2, cv2.LINE_AA)
        
        return preview
    
    def _generate_statistics(self, paths, colors, width, height, algorithm):
        """
        Generate statistics about the generated paths
        """
        total_length = 0
        for path in paths:
            if len(path) > 1:
                diffs = np.diff(path, axis=0)
                lengths = np.sqrt(np.sum(diffs**2, axis=1))
                total_length += np.sum(lengths)
        
        avg_length = total_length / len(paths) if len(paths) > 0 else 0
        
        return {
            "path_count": len(paths),
            "total_length": float(total_length),
            "average_path_length": float(avg_length),
            "image_size": [width, height],
            "algorithm": algorithm,
            "colors_used": len(set(colors)),
        }


NODE_CLASS_MAPPINGS = {
    "CenterlineToSVG": CenterlineToSVG
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CenterlineToSVG": "Centerline to SVG"
}
