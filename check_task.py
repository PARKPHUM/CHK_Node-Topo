# -*- coding: utf-8 -*-
"""
check_task.py — รันการตรวจสอบใน background (QgsTask) เพื่อไม่ให้ QGIS ค้าง

การดึงข้อมูล (I/O) ทำใน background ผ่าน QgsVectorLayerFeatureSource ซึ่งเปิด
การเชื่อมต่อของตัวเองต่อ provider — จำเป็นมากกับชั้นข้อมูลจากฐานข้อมูล
(PostgreSQL/PostGIS) เพราะการดึง feature บน main thread จะทำให้ QGIS ค้าง
ระหว่างรอฐานข้อมูล/เครือข่าย ตัว filter rect ใน request จะถูกส่งลงไปทำที่
ฝั่งฐานข้อมูล (bbox query บน GiST index) โดยอัตโนมัติ

การสร้างชั้น/ตารางผลลัพธ์จะทำใน finished() ซึ่งรันบน main thread

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

from qgis.core import Qgis, QgsGeometry, QgsMessageLog, QgsRectangle, QgsTask

from .checks.overlap_check import find_overlaps
from .checks.gap_check import find_gaps
from .checks.node_check import find_unmatched_vertices

# เช็ก cancel / อัปเดต progress ทุก ๆ กี่ feature ระหว่างดึงข้อมูล
_FETCH_CHECK_EVERY = 500


class _StageProgress:
    """แปลง progress 0-100 ของขั้นตอนย่อย ให้เป็นช่วง [start, end] ของงานรวม

    ใช้ส่งให้ฟังก์ชันตรวจสอบแทนตัว task ตรง ๆ เพื่อให้แถบ progress เดินต่อเนื่อง
    ทั้งงาน และ throttle การยิง signal (ยิงเฉพาะเมื่อเปอร์เซ็นต์จำนวนเต็มเปลี่ยน)
    """

    def __init__(self, task, start, end):
        self._task = task
        self._start = float(start)
        self._span = float(end) - float(start)
        self._last = -1

    def isCanceled(self):  # noqa: N802 (เลียนแบบ QgsTask/QgsFeedback)
        return self._task.isCanceled()

    def setProgress(self, value):  # noqa: N802
        value = max(0.0, min(100.0, float(value)))
        pct = self._start + self._span * value / 100.0
        if int(pct) != self._last:
            self._last = int(pct)
            self._task.setProgress(pct)


class TopologyCheckTask(QgsTask):
    """งานตรวจสอบ Overlap / Gap / Node แบบ background (รวมการดึงข้อมูล)"""

    def __init__(self, poly_source, poly_request, tolerance, node_tolerance,
                 do_overlap, do_gap, do_node,
                 point_source=None, point_request=None,
                 point_transform=None, rect_back_transform=None,
                 window_scope=False, window_rect=None,
                 poly_count_hint=0, point_count_hint=0):
        """
        :param poly_source: QgsVectorLayerFeatureSource ของชั้น POLYGON
                            (สร้างบน main thread แล้วใช้อ่านใน background ได้)
        :param poly_request: QgsFeatureRequest สำหรับ POLYGON (ตั้ง filter rect มาแล้ว)
        :param point_source: QgsVectorLayerFeatureSource ของชั้น POINT (เมื่อตรวจ Node)
        :param point_request: QgsFeatureRequest สำหรับ POINT
        :param point_transform: QgsCoordinateTransform POINT -> POLYGON CRS (หรือ None)
        :param rect_back_transform: QgsCoordinateTransform POLYGON -> POINT CRS
                                    ใช้แปลงกรอบกรองหมุดในโหมด "เฉพาะหน้าต่าง"
        :param window_scope: True เมื่อผู้ใช้เลือกตรวจเฉพาะหน้าต่างปัจจุบัน
        :param window_rect: QgsRectangle กรอบหน้าต่าง (CRS ของ POLYGON) — ใช้กรอง
                            ผลลัพธ์ Overlap/Gap ให้เหลือเฉพาะที่แตะกรอบหน้าต่างจริง
                            (แปลงคาบขอบถูกดึงมาทั้งตัว จึงอาจพบพื้นที่ผิดนอกกรอบ)
        :param poly_count_hint: จำนวน feature โดยประมาณ (ใช้คำนวณ progress เท่านั้น)

        หมายเหตุโหมดหน้าต่าง: Gap ตรวจจากแปลงที่แตะกรอบหน้าต่างเท่านั้น —
        การตัดขอบ fetch ไม่สร้าง Gap ปลอม (วงล้อมที่ไม่ครบจะรวมกับภายนอก
        ไม่เกิด interior ring) มีแต่พลาดช่องว่างที่วงล้อมใหญ่เกินหน้าต่าง
        ซึ่งตรงตามความหมาย "ตรวจเฉพาะหน้าต่างปัจจุบัน"
        """
        super().__init__("ตรวจสอบ Topology / Node", QgsTask.CanCancel)
        self.poly_source = poly_source
        self.poly_request = poly_request
        self.point_source = point_source
        self.point_request = point_request
        self.point_transform = point_transform
        self.rect_back_transform = rect_back_transform
        self.window_scope = window_scope
        self.window_rect = window_rect
        self.poly_count_hint = poly_count_hint
        self.point_count_hint = point_count_hint

        self.tolerance = tolerance            # สำหรับ Overlap/Gap
        self.node_tolerance = node_tolerance  # ระยะยอมรับสำหรับ Node/หมุด (แยกต่างหาก)
        self.do_overlap = do_overlap
        self.do_gap = do_gap
        self.do_node = do_node

        self.results = []
        self.summary = {"overlap": 0, "gap": 0, "node": 0}
        self.polygon_count = 0
        self.point_count = 0
        self.transform_drops = 0  # จำนวนหมุดที่แปลง CRS ไม่สำเร็จ (ไว้แจ้งเตือน)
        self.error_message = None
        self._on_done = None

    def set_callback(self, callback):
        """ตั้ง callback ที่จะถูกเรียกบน main thread เมื่อทำงานเสร็จ

        callback(success: bool, task: TopologyCheckTask)
        """
        self._on_done = callback

    # ------------------------------------------------------------------
    def run(self):
        """รันบน background thread — ห้ามแตะ GUI/QgsProject/layer ตรง ๆ"""
        try:
            # ---- ขั้นที่ 1: ดึงข้อมูล POLYGON (0-10%) ----
            polygon_features, _ = self._fetch_features(
                self.poly_source, self.poly_request, None,
                _StageProgress(self, 0, 10), self.poly_count_hint)
            if self.isCanceled():
                return False
            self.polygon_count = len(polygon_features)
            if not polygon_features:
                return True  # ไม่มีข้อมูล — ให้ฝั่ง UI แจ้งเตือนเอง

            # ---- ขั้นที่ 2: ดึงข้อมูล POINT (10-20%) ----
            point_features = []
            if self.do_node and self.point_source is not None:
                if self.window_scope:
                    # สำคัญ: กรองหมุดด้วย "ขอบเขตของแปลงที่ถูกดึงมาตรวจ" ไม่ใช่กรอบหน้าต่าง
                    # เพราะแปลงที่คาบเกี่ยวขอบหน้าต่างมี vertex อยู่นอกกรอบ — ถ้ากรองหมุด
                    # ด้วยกรอบหน้าต่าง หมุดของ vertex เหล่านั้นจะหายไปและถูกฟ้องผิด
                    rect = _features_extent(
                        polygon_features,
                        margin=max(self.node_tolerance * 2.0, 1.0))
                    if rect is not None and self.rect_back_transform is not None:
                        try:
                            rect = self.rect_back_transform.transformBoundingBox(rect)
                        except Exception:  # noqa: BLE001
                            rect = None  # แปลงกรอบไม่ได้ -> ไม่กรอง (ดึงหมุดทั้งหมด ปลอดภัยกว่า)
                    if rect is not None:
                        self.point_request.setFilterRect(rect)
                point_features, self.transform_drops = self._fetch_features(
                    self.point_source, self.point_request, self.point_transform,
                    _StageProgress(self, 10, 20), self.point_count_hint)
                if self.isCanceled():
                    return False
                self.point_count = len(point_features)

            # ---- ขั้นที่ 3: ตรวจสอบ (20-100% แบ่งเท่ากันตามรายการที่เลือก) ----
            stages = []
            if self.do_overlap:
                stages.append(("overlap", find_overlaps,
                               (polygon_features, self.tolerance)))
            if self.do_gap:
                stages.append(("gap", find_gaps,
                               (polygon_features, self.tolerance)))
            if self.do_node:
                stages.append(("node", find_unmatched_vertices,
                               (polygon_features, point_features, self.node_tolerance)))

            results = []
            span = 80.0 / max(len(stages), 1)
            for i, (_name, func, args) in enumerate(stages):
                if self.isCanceled():
                    return False
                progress = _StageProgress(self, 20 + span * i, 20 + span * (i + 1))
                results.extend(func(*args, feedback=progress))
            if self.isCanceled():
                return False

            # โหมดหน้าต่าง: ตัดผล Overlap/Gap ที่อยู่นอกกรอบหน้าต่างออก
            # (แปลงคาบขอบถูกดึงมาทั้งตัว พื้นที่ผิดจึงโผล่นอกกรอบได้)
            if self.window_scope and self.window_rect is not None:
                results = _filter_to_window(results, self.window_rect)

            self.results = results
            for item in results:
                t = item.get("type")
                if t in self.summary:
                    self.summary[t] += 1
            self.setProgress(100)
            return True

        except Exception as exc:  # noqa: BLE001
            self.error_message = str(exc)
            QgsMessageLog.logMessage(
                "TopologyCheckTask error: {}".format(exc),
                "Node & Topology Checker", Qgis.Critical)
            return False

    # ------------------------------------------------------------------
    def _fetch_features(self, source, request, transform, progress, count_hint):
        """ดึง (fid, QgsGeometry) จาก feature source ใน background

        คืน (list ของ (fid, geometry), จำนวนที่แปลง CRS ไม่สำเร็จ)
        การทิ้ง feature ที่แปลงพิกัดไม่ได้จะถูกนับไว้ เพื่อให้ UI แจ้งเตือน
        (การทิ้งเงียบ ๆ ทำให้ผลตรวจ Node หลอก)
        """
        out = []
        drops = 0
        for i, feat in enumerate(source.getFeatures(request)):
            if i % _FETCH_CHECK_EVERY == 0:
                if self.isCanceled():
                    break
                if count_hint > 0:
                    progress.setProgress(min(100.0 * i / count_hint, 100.0))
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            g = QgsGeometry(geom)
            if transform is not None:
                try:
                    g.transform(transform)
                except Exception:  # noqa: BLE001
                    drops += 1
                    continue
            out.append((feat.id(), g))
        progress.setProgress(100.0)
        return out, drops

    # ------------------------------------------------------------------
    def finished(self, result):
        """เรียกโดย task manager บน main thread"""
        if self._on_done is not None:
            self._on_done(result, self)


def _filter_to_window(results, window_rect):
    """คงเฉพาะผล Overlap/Gap ที่ geometry แตะกรอบหน้าต่าง (Node คงพฤติกรรมเดิม)

    เช็ก bbox ก่อน (ถูก) แล้วค่อย intersects จริง (แพง) เฉพาะตัวที่ bbox ชนกรอบ
    """
    window_geom = QgsGeometry.fromRect(window_rect)
    out = []
    for item in results:
        if item.get("type") not in ("overlap", "gap"):
            out.append(item)
            continue
        geom = item.get("geometry")
        if geom is None or geom.isEmpty():
            continue
        if not geom.boundingBox().intersects(window_rect):
            continue
        if geom.intersects(window_geom):
            out.append(item)
    return out


def _features_extent(features, margin):
    """คืนกรอบรวมของ features [(fid, geom)] ขยายขอบด้วย margin (หน่วยแผนที่)"""
    rect = None
    for _fid, geom in features:
        bb = geom.boundingBox()
        if rect is None:
            rect = QgsRectangle(bb)
        else:
            rect.combineExtentWith(bb)
    if rect is not None:
        rect.grow(margin)
    return rect
