# -*- coding: utf-8 -*-
"""
check_task.py — รันการตรวจสอบใน background (QgsTask) เพื่อไม่ให้ QGIS ค้าง

ข้อมูล geometry ถูกคัดลอกออกมาเป็น list ของ (fid, QgsGeometry) ก่อนส่งเข้า task
(QgsGeometry เป็น value type ใช้งานข้ามเธรดได้ปลอดภัย) การสร้างชั้น/ตารางผลลัพธ์
จะทำใน finished() ซึ่งรันบน main thread

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

from qgis.core import QgsMessageLog, QgsTask, Qgis

from .checks.overlap_check import find_overlaps
from .checks.gap_check import find_gaps
from .checks.node_check import find_unmatched_vertices


class TopologyCheckTask(QgsTask):
    """งานตรวจสอบ Overlap / Gap / Node แบบ background"""

    def __init__(self, polygon_features, point_features, tolerance, node_tolerance,
                 do_overlap, do_gap, do_node):
        super().__init__("ตรวจสอบ Topology / Node", QgsTask.CanCancel)
        self.polygon_features = polygon_features
        self.point_features = point_features
        self.tolerance = tolerance            # สำหรับ Overlap/Gap
        self.node_tolerance = node_tolerance  # ระยะยอมรับสำหรับ Node/หมุด (แยกต่างหาก)
        self.do_overlap = do_overlap
        self.do_gap = do_gap
        self.do_node = do_node

        self.results = []
        self.summary = {"overlap": 0, "gap": 0, "node": 0}
        self.error_message = None
        self._on_done = None

    def set_callback(self, callback):
        """ตั้ง callback ที่จะถูกเรียกบน main thread เมื่อทำงานเสร็จ

        callback(success: bool, task: TopologyCheckTask)
        """
        self._on_done = callback

    # ------------------------------------------------------------------
    def run(self):
        """รันบน background thread — ห้ามแตะ GUI/โปรเจกต์"""
        try:
            results = []

            if self.do_overlap:
                results.extend(find_overlaps(self.polygon_features, self.tolerance, self))
            if self.isCanceled():
                return False

            if self.do_gap:
                results.extend(find_gaps(self.polygon_features, self.tolerance, self))
            if self.isCanceled():
                return False

            if self.do_node:
                results.extend(find_unmatched_vertices(
                    self.polygon_features, self.point_features, self.node_tolerance, self))
            if self.isCanceled():
                return False

            self.results = results
            for item in results:
                t = item.get("type")
                if t in self.summary:
                    self.summary[t] += 1
            return True

        except Exception as exc:  # noqa: BLE001
            self.error_message = str(exc)
            QgsMessageLog.logMessage(
                "TopologyCheckTask error: {}".format(exc),
                "Node & Topology Checker", Qgis.Critical)
            return False

    # ------------------------------------------------------------------
    def finished(self, result):
        """เรียกโดย task manager บน main thread"""
        if self._on_done is not None:
            self._on_done(result, self)
