"""
Line Region Detector Node for ComfyUI
Detects line regions and separates fill areas from line art images
"""

import numpy as np
import torch
import cv2
from PIL import Image
import json


class LineRegionDetector:
    """
    Detects line regions from line art images
    Separates background, lines, and fill areas
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "background_mode": (["auto", "white", "black"],),
                "background_threshold": ("INT", {
                    "default": 240,
                    "min": 0,
                    "max": 255,
                    "step": 1
                }),
                "line_detection_method": (["edge", "morphology", "hybrid"],),
                "min_line_width": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 100,
                    "step": 1
                }),
                "max_line_width": ("INT", {
                    "default": 50,
                    "min": 1,
                    "max": 500,
                    "step": 1
                }),
                "fill_handling": (["ignore", "separate", "include"],),
            },
            "optional": {
                "color_clustering": ("BOOLEAN", {"default": False}),
                "num_colors": ("INT", {
                    "default": 5,
                    "min": 2,
                    "max": 20,
                    "step": 1
                }),
            }
        }
    
    RETURN_TYPES = ("MASK", "MASK", "IMAGE", "STRING")
    RETURN_NAMES = ("line_mask", "fill_mask", "preview_image", "color_info")
    FUNCTION = "detect_lines"
    CATEGORY = "TJ_Vector"
    
    def detect_lines(self, image, background_mode="auto", background_threshold=240,
                    line_detection_method="hybrid", min_line_width=1, max_line_width=50,
                    fill_handling="separate", color_clustering=False, num_colors=5):
        """
        Main function to detect line regions
        """
        # Convert from ComfyUI format (B, H, W, C) to numpy
        img_np = image[0].cpu().numpy()
        
        # Convert to 0-255 range
        img_255 = (img_np * 255).astype(np.uint8)
        
        # Convert to grayscale
        if img_255.shape[-1] >= 3:
            gray = cv2.cvtColor(img_255, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_255[..., 0]
        
        height, width = gray.shape
        
        # Step 1: Background separation
        foreground_mask = self._separate_background(gray, background_mode, background_threshold)
        
        # Step 2: Line detection
        line_mask = self._detect_line_regions(
            gray, foreground_mask, line_detection_method, 
            min_line_width, max_line_width
        )
        
        # Step 3: Fill area separation
        fill_mask = self._separate_fill_areas(
            foreground_mask, line_mask, fill_handling
        )
        
        # Step 4: Color extraction (optional)
        color_info = {}
        if color_clustering:
            color_info = self._extract_colors(img_255, line_mask, num_colors)
        
        # Create preview image
        preview_image = self._create_preview(img_255, line_mask, fill_mask)
        
        # Convert masks to ComfyUI format
        line_mask_tensor = torch.from_numpy(line_mask.astype(np.float32) / 255.0).unsqueeze(0)
        fill_mask_tensor = torch.from_numpy(fill_mask.astype(np.float32) / 255.0).unsqueeze(0)
        preview_tensor = torch.from_numpy(preview_image.astype(np.float32) / 255.0).unsqueeze(0)
        
        color_info_str = json.dumps(color_info, indent=2)
        
        return (line_mask_tensor, fill_mask_tensor, preview_tensor, color_info_str)
    
    def _separate_background(self, gray, mode, threshold):
        """
        Separate background from foreground
        """
        if mode == "auto":
            # Use Otsu's method for automatic thresholding
            _, foreground = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        elif mode == "white":
            # White background
            _, foreground = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
        elif mode == "black":
            # Black background
            _, foreground = cv2.threshold(gray, 255 - threshold, 255, cv2.THRESH_BINARY)
        
        # Clean up noise
        kernel = np.ones((3, 3), np.uint8)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel, iterations=1)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        return foreground
    
    def _detect_line_regions(self, gray, foreground_mask, method, min_width, max_width):
        """
        Detect line regions using specified method
        """
        if method == "edge":
            return self._edge_based_detection(gray, foreground_mask, min_width, max_width)
        elif method == "morphology":
            return self._morphology_based_detection(foreground_mask, min_width, max_width)
        elif method == "hybrid":
            return self._hybrid_detection(gray, foreground_mask, min_width, max_width)
        
        return foreground_mask
    
    def _edge_based_detection(self, gray, foreground_mask, min_width, max_width):
        """
        Edge-based line detection using Canny
        """
        # Canny edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Dilate edges to create line regions
        kernel_size = max(3, min_width)
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        dilated_edges = cv2.dilate(edges, kernel, iterations=1)
        
        # Combine with foreground mask
        line_mask = cv2.bitwise_and(dilated_edges, foreground_mask)
        
        return line_mask
    
    def _morphology_based_detection(self, foreground_mask, min_width, max_width):
        """
        Morphology-based line detection
        """
        # Erode to remove fill areas
        kernel_size = max(3, max_width // 2)
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        eroded = cv2.erode(foreground_mask, kernel, iterations=1)
        
        # Subtract eroded from original to get line regions
        line_mask = cv2.subtract(foreground_mask, eroded)
        
        # Opening to clean up
        kernel_small = np.ones((3, 3), np.uint8)
        line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_OPEN, kernel_small, iterations=1)
        
        return line_mask
    
    def _hybrid_detection(self, gray, foreground_mask, min_width, max_width):
        """
        Hybrid method combining edge and morphology
        """
        # Get both methods
        edge_mask = self._edge_based_detection(gray, foreground_mask, min_width, max_width)
        morph_mask = self._morphology_based_detection(foreground_mask, min_width, max_width)
        
        # Combine using OR operation
        combined = cv2.bitwise_or(edge_mask, morph_mask)
        
        # Clean up
        kernel = np.ones((3, 3), np.uint8)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        return combined
    
    def _separate_fill_areas(self, foreground_mask, line_mask, fill_handling):
        """
        Separate fill areas from lines
        """
        if fill_handling == "ignore":
            return np.zeros_like(foreground_mask)
        
        # Subtract line mask from foreground to get fill areas
        fill_mask = cv2.subtract(foreground_mask, line_mask)
        
        if fill_handling == "separate":
            # Remove small noise
            kernel = np.ones((5, 5), np.uint8)
            fill_mask = cv2.morphologyEx(fill_mask, cv2.MORPH_OPEN, kernel, iterations=1)
            
            # Remove very small regions
            contours, _ = cv2.findContours(fill_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            min_area = 100  # pixels
            for contour in contours:
                if cv2.contourArea(contour) < min_area:
                    cv2.drawContours(fill_mask, [contour], -1, 0, -1)
        
        return fill_mask
    
    def _extract_colors(self, img_rgb, line_mask, num_colors):
        """
        Extract color information using K-means clustering
        """
        # Get pixels in line regions
        mask_bool = line_mask > 127
        if not np.any(mask_bool):
            return {"colors": [], "count": 0}
        
        line_pixels = img_rgb[mask_bool]
        
        if len(line_pixels) == 0:
            return {"colors": [], "count": 0}
        
        # K-means clustering
        line_pixels_float = line_pixels.astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
        k = min(num_colors, len(line_pixels))
        
        if k < 1:
            return {"colors": [], "count": 0}
        
        _, labels, centers = cv2.kmeans(
            line_pixels_float, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS
        )
        
        # Convert centers to color info
        colors = []
        for i, center in enumerate(centers):
            color_rgb = center.astype(int).tolist()
            count = np.sum(labels == i)
            colors.append({
                "rgb": color_rgb,
                "hex": "#{:02x}{:02x}{:02x}".format(color_rgb[0], color_rgb[1], color_rgb[2]),
                "count": int(count),
                "percentage": float(count / len(labels) * 100)
            })
        
        # Sort by count
        colors.sort(key=lambda x: x["count"], reverse=True)
        
        return {
            "colors": colors,
            "count": len(colors)
        }
    
    def _create_preview(self, img_rgb, line_mask, fill_mask):
        """
        Create preview image showing detected regions
        """
        preview = img_rgb.copy()
        
        # Overlay line mask in red
        line_overlay = np.zeros_like(preview)
        line_overlay[line_mask > 127] = [255, 0, 0]  # Red for lines
        
        # Overlay fill mask in blue
        fill_overlay = np.zeros_like(preview)
        fill_overlay[fill_mask > 127] = [0, 0, 255]  # Blue for fills
        
        # Blend
        preview = cv2.addWeighted(preview, 0.7, line_overlay, 0.3, 0)
        preview = cv2.addWeighted(preview, 1.0, fill_overlay, 0.2, 0)
        
        return preview


NODE_CLASS_MAPPINGS = {
    "LineRegionDetector": LineRegionDetector
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LineRegionDetector": "Line Region Detector"
}
