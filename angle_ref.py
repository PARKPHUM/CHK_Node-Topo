# -*- coding: utf-8 -*-
"""
angle_ref.py — "แนวอ้างอิงมุม" จากการ Ctrl + คลิกซ้าย 2 จุด

ปัญหาเดิม: ล็อกมุมได้แต่เป็นมุม "สัมพัทธ์กับช่วงก่อนหน้า" เท่านั้น เวลาต้องการ
ตีฉากจากแนวเขตจริง (เช่น แนวถนน แนวหมุดสองตัว) จึงอ้างอิงอะไรไม่ได้

วิธีใช้: กด Ctrl ค้างแล้วคลิกซ้ายบน Node ของ POLYGON หรือบนหมุด POINT 2 ครั้ง
→ ได้ "แนวอ้างอิง" พร้อมค่าอาซิมุท (องศาตามเข็มนาฬิกาจากทิศเหนือ) แสดงในช่อง
แล้วการล็อกมุมจะอิงแนวนี้แทน (มุมสัมบูรณ์) ไม่ใช่อิงช่วงก่อนหน้า

หมายเหตุเรื่อง shortcut: Ctrl + คลิกซ้าย ว่างอยู่สำหรับเครื่องมือ Add Feature
ของ QGIS (ที่ QGIS จองไว้เป็นของ Vertex Tool / Rotate Feature / Offset Curve)
โมดูลนี้จึงดักเฉพาะตอนที่เครื่องมือปัจจุบันเป็น QgsMapToolCapture เท่านั้น

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

import math

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt
from qgis.core import Qgis, QgsPointXY, QgsWkbTypes
from qgis.gui import QgsRubberBand, QgsVertexMarker

#: สีของแนวอ้างอิง — ม่วง ให้ต่างจากเส้นเหลืองที่วาดและจุด Node สีแดง
REF_COLOR = QColor("#8e44ad")
#: สีเส้นนำสายตาที่ลากผ่านเคอร์เซอร์ — ม่วงอมชมพู อ่อนกว่า ไม่แย่งสายตาแนวอ้างอิง
GUIDE_COLOR = QColor("#e050c8")


def _line_geometry_type():
    """ค่า enum ชนิดเรขาคณิต "เส้น" — รองรับตำแหน่ง enum ที่ต่างกันตามรุ่น QGIS"""
    try:
        return Qgis.GeometryType.Line
    except AttributeError:
        return QgsWkbTypes.LineGeometry


class AngleReference(QObject):
    """เก็บแนวอ้างอิง 2 จุด + วาดให้เห็นบนแผนที่ + คำนวณอาซิมุท"""

    #: ยิงทุกครั้งที่จุดอ้างอิงเปลี่ยน (เก็บจุดแรก / ครบ 2 จุด / ล้าง)
    referenceChanged = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self._p1 = None
        self._p2 = None
        self._band = None
        self._markers = []
        self._guide_band = None   # เส้นนำสายตาที่ลากผ่านเคอร์เซอร์

    # ==================================================================
    # สถานะ
    # ==================================================================
    def has_reference(self):
        """ครบ 2 จุดแล้วหรือยัง"""
        return self._p1 is not None and self._p2 is not None

    def point_count(self):
        return (1 if self._p1 is not None else 0) + (1 if self._p2 is not None else 0)

    def azimuth(self):
        """อาซิมุทของแนว: องศาตามเข็มนาฬิกาจากทิศเหนือ (0–360) — ไม่ครบ 2 จุดคืน None"""
        if not self.has_reference():
            return None
        dx = self._p2.x() - self._p1.x()
        dy = self._p2.y() - self._p1.y()
        if dx == 0 and dy == 0:
            return None
        # atan2(dx, dy) ให้มุมจากแกนเหนือ วนตามเข็ม — ตรงกับนิยามอาซิมุทงานรังวัด
        return math.degrees(math.atan2(dx, dy)) % 360.0

    # ==================================================================
    # รับการคลิก
    # ==================================================================
    def handle_click(self, screen_pos):
        """รับ Ctrl + คลิกซ้าย 1 ครั้ง — คืน True ถ้ารับไว้ (ให้ผู้เรียกกลืน event)

        คลิกครั้งที่ 3 = เริ่มจับแนวใหม่ ไม่ต้องกดล้างก่อน
        """
        point = self._snap(screen_pos)
        if point is None:
            return False

        if self.has_reference() or self._p1 is None:
            # เริ่มแนวใหม่
            self.clear(silent=True)
            self._p1 = point
        else:
            self._p2 = point

        self._redraw()
        self.referenceChanged.emit()
        return True

    def _snap(self, screen_pos):
        """หาพิกัดจากตำแหน่งคลิก — ดูดเข้า vertex/หมุดก่อนเสมอ

        คลิกตรง Node ของ POLYGON หรือหมุด POINT จะได้พิกัดของจุดนั้นเป๊ะ ๆ
        ถ้าไม่โดนอะไรเลยจึงใช้พิกัดดิบตรงที่คลิก
        """
        canvas = self.iface.mapCanvas()
        try:
            match = canvas.snappingUtils().snapToMap(screen_pos)
            if match is not None and match.isValid():
                return QgsPointXY(match.point())
        except Exception:  # noqa: BLE001 - snapping ใช้ไม่ได้ ก็ยังคลิกอิสระได้
            pass
        try:
            return QgsPointXY(canvas.getCoordinateTransform().toMapCoordinates(screen_pos))
        except Exception:  # noqa: BLE001
            return None

    # ==================================================================
    # วาดบนแผนที่
    # ==================================================================
    def _redraw(self):
        canvas = self.iface.mapCanvas()
        self._clear_markers()

        for point in (self._p1, self._p2):
            if point is None:
                continue
            marker = QgsVertexMarker(canvas)
            marker.setCenter(point)
            marker.setColor(REF_COLOR)
            marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
            marker.setIconSize(11)
            marker.setPenWidth(3)
            self._markers.append(marker)

        if self._band is None:
            self._band = QgsRubberBand(canvas, _line_geometry_type())
            self._band.setColor(REF_COLOR)
            self._band.setWidth(2)
            try:
                self._band.setLineStyle(Qt.DashLine)
            except (AttributeError, TypeError):
                pass
        self._band.reset(_line_geometry_type())
        if self.has_reference():
            self._band.addPoint(self._p1, False)
            self._band.addPoint(self._p2, True)

    def _clear_markers(self):
        canvas = self.iface.mapCanvas()
        for marker in self._markers:
            try:
                canvas.scene().removeItem(marker)
            except Exception:  # noqa: BLE001
                pass
        self._markers = []

    # ==================================================================
    # เส้นนำสายตาที่เคอร์เซอร์
    # ==================================================================
    def show_cursor_guide(self, screen_pos, azimuth):
        """ลากเส้นนำสายตาผ่านตำแหน่งเคอร์เซอร์ ตามแนวที่กด Shift แล้วจะล็อกได้

        ช่วยให้เห็นล่วงหน้าว่าแนวที่จะล็อกพาดไปทางไหน ก่อนจะคลิกลงจุดจริง
        (เส้นพาดยาวข้ามจอ เพราะประโยชน์คือใช้เล็งเทียบกับของอื่นบนแผนที่)
        """
        if azimuth is None or screen_pos is None:
            self.clear_cursor_guide()
            return

        canvas = self.iface.mapCanvas()
        try:
            centre = QgsPointXY(canvas.getCoordinateTransform().toMapCoordinates(screen_pos))
            extent = canvas.extent()
            reach = math.hypot(extent.width(), extent.height())
        except Exception:  # noqa: BLE001
            self.clear_cursor_guide()
            return

        # อาซิมุท (ตามเข็ม จากทิศเหนือ) → เวกเตอร์ทิศทางบนระนาบแผนที่
        rad = math.radians(azimuth)
        ux, uy = math.sin(rad), math.cos(rad)

        if self._guide_band is None:
            self._guide_band = QgsRubberBand(canvas, _line_geometry_type())
            self._guide_band.setColor(GUIDE_COLOR)
            self._guide_band.setWidth(1)
            try:
                self._guide_band.setLineStyle(Qt.DashLine)
            except (AttributeError, TypeError):
                pass

        self._guide_band.reset(_line_geometry_type())
        self._guide_band.addPoint(
            QgsPointXY(centre.x() - ux * reach, centre.y() - uy * reach), False)
        self._guide_band.addPoint(
            QgsPointXY(centre.x() + ux * reach, centre.y() + uy * reach), True)

    def clear_cursor_guide(self):
        if self._guide_band is not None:
            self._guide_band.reset(_line_geometry_type())

    # ==================================================================
    # ล้าง / เก็บกวาด
    # ==================================================================
    def clear(self, silent=False):
        self._p1 = None
        self._p2 = None
        self._clear_markers()
        if self._band is not None:
            self._band.reset(_line_geometry_type())
        self.clear_cursor_guide()
        if not silent:
            self.referenceChanged.emit()

    def cleanup(self):
        self._clear_markers()
        scene = None
        try:
            scene = self.iface.mapCanvas().scene()
        except Exception:  # noqa: BLE001
            pass
        for band in (self._band, self._guide_band):
            if band is not None and scene is not None:
                try:
                    scene.removeItem(band)
                except Exception:  # noqa: BLE001
                    pass
        self._band = None
        self._guide_band = None
