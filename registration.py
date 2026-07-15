"""
registration.py
-----------------
Camera-based registration mark detection + tilt/offset correction.

Pipeline per mark:
1. Take the mark's nominal machine position (mm), convert to an expected
   pixel location using the camera calibration (px_per_mm + origin offset).
2. Crop a search ROI around that expected pixel location.
3. Threshold + find contours, pick the most "mark-like" blob (area + shape
   filters), take its centroid.
4. Convert the found pixel centroid back to machine mm using the same
   calibration.

Once we have N (nominal_mm -> detected_mm) point pairs, fit an affine
transform. That transform is what gcode_transform.py applies to the job
before cutting.

This module intentionally keeps calibration (px_per_mm, origin offset)
simple and file-based - swap in a proper checkerboard/homography calibration
later without changing the public API (detect_marks / compute_correction).
"""
import cv2
import numpy as np


class RegistrationError(Exception):
    pass


class RegistrationSystem:
    def __init__(self, camera_index, frame_size, px_per_mm, origin_offset_mm):
        self.camera_index = camera_index
        self.frame_w, self.frame_h = frame_size
        self.px_per_mm = px_per_mm
        self.ox_mm, self.oy_mm = origin_offset_mm
        self.cap = None

    # ------------------------------------------------------------- lifecycle
    def open(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_h)
        if not self.cap.isOpened():
            raise RegistrationError(f"Could not open camera index {self.camera_index}")

    def close(self):
        if self.cap:
            self.cap.release()
            self.cap = None

    def grab_frame(self):
        if not self.cap:
            raise RegistrationError("Camera not open")
        ok, frame = self.cap.read()
        if not ok:
            raise RegistrationError("Failed to read frame from camera")
        return frame

    # ------------------------------------------------------------ conversion
    def mm_to_px(self, x_mm, y_mm):
        px = (x_mm + self.ox_mm) * self.px_per_mm
        py = (y_mm + self.oy_mm) * self.px_per_mm
        return int(px), int(py)

    def px_to_mm(self, px, py):
        x_mm = px / self.px_per_mm - self.ox_mm
        y_mm = py / self.px_per_mm - self.oy_mm
        return x_mm, y_mm

    # --------------------------------------------------------------- detect
    def _find_mark_in_roi(self, frame, cx, cy, radius):
        h, w = frame.shape[:2]
        x0, x1 = max(0, cx - radius), min(w, cx + radius)
        y0, y1 = max(0, cy - radius), min(h, cy + radius)
        roi = frame[y0:y1, x0:x1]
        if roi.size == 0:
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        # Registration marks are printed as solid dark shapes on light label
        # stock, so an inverse binary threshold with Otsu picks them out
        # without needing a fixed brightness value.
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        best = None
        best_score = -1
        roi_area = roi.shape[0] * roi.shape[1]
        for c in contours:
            area = cv2.contourArea(c)
            if area < 20 or area > roi_area * 0.8:
                continue
            perim = cv2.arcLength(c, True)
            if perim == 0:
                continue
            circularity = 4 * np.pi * area / (perim * perim)  # 1.0 == perfect circle
            score = circularity * area
            if score > best_score:
                best_score = score
                best = c
        if best is None:
            return None

        M = cv2.moments(best)
        if M["m00"] == 0:
            return None
        cx_local = M["m10"] / M["m00"]
        cy_local = M["m01"] / M["m00"]
        return x0 + cx_local, y0 + cy_local

    def detect_marks(self, nominal_points_mm, search_radius_px=60, frame=None):
        """Returns list of (nominal_mm, detected_mm) pairs. Raises
        RegistrationError naming which mark failed, so the UI can show the
        operator exactly where to look instead of a generic failure."""
        if frame is None:
            frame = self.grab_frame()

        pairs = []
        for idx, (mx, my) in enumerate(nominal_points_mm):
            cx, cy = self.mm_to_px(mx, my)
            found = self._find_mark_in_roi(frame, cx, cy, search_radius_px)
            if found is None:
                raise RegistrationError(
                    f"Mark {idx + 1} not found near expected position ({mx:.1f}, {my:.1f}) mm"
                )
            fx, fy = found
            det_mm = self.px_to_mm(fx, fy)
            pairs.append(((mx, my), det_mm))
        return pairs

    # ------------------------------------------------------------- transform
    @staticmethod
    def compute_affine(pairs):
        """Fits a 2x3 affine transform mapping nominal(mm) -> detected(mm)
        using all provided mark pairs (>=3). With exactly 3 points this is
        exact; with 4+ it's a least-squares best fit, which is what you want
        when marks aren't perfectly co-planar/printed."""
        if len(pairs) < 3:
            raise RegistrationError("Need at least 3 registration marks to fit a transform")
        src = np.array([p[0] for p in pairs], dtype=np.float32)
        dst = np.array([p[1] for p in pairs], dtype=np.float32)
        affine, inliers = cv2.estimateAffine2D(src, dst)
        if affine is None:
            raise RegistrationError("Affine fit failed - check mark detection quality")
        return affine  # 2x3 numpy array

    @staticmethod
    def describe_transform(affine):
        """Human-readable summary for the registration panel: rotation angle
        (tilt) and translation offset."""
        a, b = affine[0, 0], affine[1, 0]
        angle_deg = np.degrees(np.arctan2(b, a))
        tx, ty = affine[0, 2], affine[1, 2]
        return {"tilt_deg": angle_deg, "offset_mm": (tx, ty)}
