# -*- coding: utf-8 -*-
"""
guide_tools.py — "ขึงแนวตรึง" สำหรับตรวจว่าโพลิกอนสองฝั่งอยู่ในแนวเดียวกันหรือไม่

แนวคิด: ผู้ใช้คลิก 2 จุด (snap เข้าหมุดได้) เพื่อกำหนด "แนว" เหมือนขึงเชือกตรึงแนว
ปลั๊กอินยืดแนวนั้นออกไปทั้งสองด้านให้พาดข้ามจอ แล้ววัด "ระยะตั้งฉาก" ของ vertex
ของโพลิกอนที่อยู่ใกล้แนว → บอกได้เป็นตัวเลขว่าเยื้องออกจากแนวกี่เมตร ไปทางซ้ายหรือขวา

ชั้นข้อมูลที่ดูแล:
  1. "แนวตรึง (Guide)"   — เส้นแนวที่ขึง (เส้นประฟ้า) วาดเอง แก้ปลายได้
  2. "จุดเยื้องแนว"       — ผลตรวจ: จุดแดงเฉพาะที่เยื้องเกินค่าที่ยอมรับ (อ่านอย่างเดียว)

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

import math

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsEditFormConfig,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

GUIDE_LAYER_NAME = "แนวตรึง (Guide)"
OFFSET_LAYER_NAME = "จุดเยื้องแนว"


def _build_guide_symbol():
    """เส้นแนว: เส้นประสีฟ้าเข้ม หนากว่าเส้นวัดระยะ — แยกจากเส้นสีเหลืองได้ชัด"""
    return QgsLineSymbol.createSimple({
        "line_color": "0,123,255,255",   # ฟ้า Bootstrap #007bff
        "line_width": "0.5",
        "line_style": "dash",
        "capstyle": "flat",
    })


def _build_offset_symbol():
    """จุดผลตรวจ: วงกลมแดงขอบขาว"""
    return QgsMarkerSymbol.createSimple({
        "name": "circle",
        "color": "220,53,69,255",
        "outline_color": "255,255,255,255",
        "outline_width": "0.4",
        "size": "3.2",
    })


def _build_offset_labeling():
    """ป้ายบอกค่าเยื้องข้างจุด"""
    settings = QgsPalLayerSettings()
    settings.fieldName = "off_txt"
    settings.isExpression = False
    try:
        settings.placement = Qgis.LabelPlacement.AroundPoint
    except AttributeError:
        settings.placement = QgsPalLayerSettings.AroundPoint
    settings.dist = 1.5
    try:
        settings.distUnits = Qgis.RenderUnit.Millimeters
    except AttributeError:
        pass

    text_format = QgsTextFormat()
    text_format.setFont(QFont("Tahoma", 9))
    text_format.setSize(9)
    text_format.setColor(QColor("#a71d2a"))

    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    buffer_settings.setSize(1.0)
    buffer_settings.setColor(QColor("#ffffff"))
    text_format.setBuffer(buffer_settings)

    settings.setFormat(text_format)
    return QgsVectorLayerSimpleLabeling(settings)


class GuideLineTool(QObject):
    """ดูแลชั้น "แนวตรึง" + ชั้นผลตรวจ และคำนวณระยะเยื้องจากแนว"""

    #: ยิงเมื่อชั้นแนวถูกสร้าง/ถูกลบ หรือแนวถูกขึงเสร็จ
    guideChanged = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.guide_layer_id = None
        self.result_layer_id = None
        self._connected_layer_id = None
        self._busy = False   # กันงูกินหาง: แก้ geometry ในมือของ signal geometryChanged

        try:
            QgsProject.instance().layersRemoved.connect(self._on_layers_removed)
        except Exception:  # noqa: BLE001
            pass

    # ==================================================================
    # เข้าถึงชั้นข้อมูล
    # ==================================================================
    def guide_layer(self):
        if self.guide_layer_id is None:
            return None
        return QgsProject.instance().mapLayer(self.guide_layer_id)

    def result_layer(self):
        if self.result_layer_id is None:
            return None
        return QgsProject.instance().mapLayer(self.result_layer_id)

    def has_guide(self):
        """มีแนวที่ขึงไว้แล้วจริง ๆ หรือยัง (มีชั้น + มี feature)"""
        return self.guide_points() is not None

    # ==================================================================
    # สร้าง / ขึงแนว
    # ==================================================================
    def ensure_guide_layer(self):
        """สร้างชั้นแนวถ้ายังไม่มี แล้วคืนชั้นนั้น"""
        layer = self.guide_layer()
        if layer is not None:
            return layer

        project = QgsProject.instance()
        project_crs = project.crs()
        authid = project_crs.authid() if project_crs and project_crs.authid() else "EPSG:4326"
        layer = QgsVectorLayer(
            "LineString?crs={}".format(authid), GUIDE_LAYER_NAME, "memory")
        if not layer.isValid():
            return None
        if project_crs and project_crs.isValid():
            layer.setCrs(project_crs)

        renderer = layer.renderer()
        if renderer is not None:
            renderer.setSymbol(_build_guide_symbol())

        cfg = layer.editFormConfig()
        cfg.setSuppress(QgsEditFormConfig.SuppressOn)
        layer.setEditFormConfig(cfg)

        project.addMapLayer(layer)
        self.guide_layer_id = layer.id()
        self._connect_guide_layer(layer)
        self.guideChanged.emit()
        return layer

    def clear_guide(self):
        """ล้างแนวที่ขึงไว้ + ผลตรวจ (ยังเก็บชั้นไว้ให้ขึงใหม่ได้)"""
        layer = self.guide_layer()
        if layer is not None:
            self._busy = True
            try:
                if not layer.isEditable():
                    layer.startEditing()
                fids = [f.id() for f in layer.getFeatures()]
                for fid in fids:
                    layer.deleteFeature(fid)
                layer.triggerRepaint()
            finally:
                self._busy = False
        self.clear_results()
        self.guideChanged.emit()

    def guide_points(self):
        """คืน (จุดต้น, จุดปลาย) ของแนวใน CRS ของชั้นแนว — ไม่มีแนวคืน None

        ใช้ vertex แรกกับ vertex สุดท้าย ฉะนั้นต่อให้ผู้ใช้คลิกเกิน 2 จุด
        ก็ยังได้ "แนวตรง" หนึ่งแนวเสมอ
        """
        layer = self.guide_layer()
        if layer is None:
            return None
        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            pts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
            for part in pts:
                if len(part) >= 2 and part[0] != part[-1]:
                    return part[0], part[-1]
        return None

    # ------------------------------------------------------------------
    # ยืดแนวออกให้พาดข้ามจอ
    # ------------------------------------------------------------------
    def _connect_guide_layer(self, layer):
        if self._connected_layer_id == layer.id():
            return
        self._disconnect_guide_layer()
        try:
            layer.featureAdded.connect(self._on_guide_feature_added)
        except Exception:  # noqa: BLE001
            pass
        self._connected_layer_id = layer.id()

    def _disconnect_guide_layer(self):
        if self._connected_layer_id is None:
            return
        layer = QgsProject.instance().mapLayer(self._connected_layer_id)
        if layer is not None:
            try:
                layer.featureAdded.disconnect(self._on_guide_feature_added)
            except (TypeError, RuntimeError):
                pass
        self._connected_layer_id = None

    def _on_guide_feature_added(self, fid):
        """ขึงแนวเสร็จ — ยืดเส้นออกและลบแนวเก่าทิ้ง (เหลือแนวเดียวเสมอ)

        หน่วงด้วย singleShot เพราะห้ามแก้ข้อมูลชั้นระหว่างที่ signal ของชั้นนั้น
        ยังปล่อยไม่จบ
        """
        if self._busy:
            return
        QTimer.singleShot(0, lambda: self._finalize_guide(fid))

    def _finalize_guide(self, fid):
        layer = self.guide_layer()
        if layer is None or self._busy:
            return

        self._busy = True
        try:
            feature = layer.getFeature(fid)
            if not feature.isValid():
                return
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                return
            part = geom.asMultiPolyline()[0] if geom.isMultipart() else geom.asPolyline()
            if len(part) < 2 or part[0] == part[-1]:
                return

            extended = self._extend_line(part[0], part[-1])
            if extended is not None:
                layer.changeGeometry(fid, extended)

            # เหลือแนวเดียวเสมอ — ขึงใหม่ทับแนวเก่าได้เลย ไม่ต้องกดล้างก่อน
            for other in list(layer.getFeatures()):
                if other.id() != fid:
                    layer.deleteFeature(other.id())

            layer.triggerRepaint()
        finally:
            self._busy = False
        self.clear_results()
        self.guideChanged.emit()

    def _extend_line(self, p1, p2):
        """ยืดเส้นผ่าน p1,p2 ออกไปทั้งสองด้านให้พาดข้ามจอปัจจุบัน

        ยืดข้างละ 1 เท่าของเส้นทแยงมุมจอ — การันตีว่าพาดข้ามทั้งจอที่เห็นอยู่ตอนขึง
        (แนวที่ยืดแล้วยังอยู่บนเส้นตรงเดิมเป๊ะ ๆ ผลคำนวณระยะตั้งฉากจึงไม่เปลี่ยน)
        """
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length <= 0:
            return None
        ux, uy = dx / length, dy / length

        try:
            extent = self.iface.mapCanvas().extent()
            reach = math.hypot(extent.width(), extent.height())
        except Exception:  # noqa: BLE001
            reach = length * 10.0
        reach = max(reach, length)

        start = QgsPointXY(p1.x() - ux * reach, p1.y() - uy * reach)
        end = QgsPointXY(p2.x() + ux * reach, p2.y() + uy * reach)
        return QgsGeometry.fromPolylineXY([start, end])

    # ==================================================================
    # ตรวจระยะเยื้องจากแนว
    # ==================================================================
    def run_check(self, polygon_layer, search_dist, tolerance):
        """วัดระยะตั้งฉากของ vertex โพลิกอนเทียบกับแนว

        คืน (results, error) โดย results = list ของ dict
        {fid, offset (เมตร มีเครื่องหมาย), side, point (QgsPointXY ใน CRS ของแนว)}
        เก็บเฉพาะจุดที่ |offset| เกิน tolerance แต่ไม่เกิน search_dist
        (เกิน search_dist = คนละแนว ไม่ใช่ความผิดพลาด)
        """
        anchors = self.guide_points()
        if anchors is None:
            return None, "ยังไม่ได้ขึงแนว — กด '✎ ขึงแนว' แล้วคลิก 2 จุดก่อน"
        if polygon_layer is None:
            return None, "กรุณาเลือกชั้น POLYGON ที่จะตรวจ"

        guide_layer = self.guide_layer()
        guide_crs = guide_layer.crs()
        p1, p2 = anchors
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length <= 0:
            return None, "แนวที่ขึงสั้นเกินไป"
        ux, uy = dx / length, dy / length

        # ตัววัดระยะ: ค่า offset ที่คำนวณได้เป็น "หน่วยแผนที่" ต้องแปลงเป็นเมตรจริง
        measurer = QgsDistanceArea()
        measurer.setSourceCrs(guide_crs, QgsProject.instance().transformContext())
        try:
            measurer.setEllipsoid(QgsProject.instance().ellipsoid())
        except Exception:  # noqa: BLE001
            pass

        # แปลง search_dist (เมตร) กลับเป็นหน่วยแผนที่ เพื่อใช้กรองแบบเร็ว ๆ
        map_per_metre = self._map_units_per_metre(measurer, p1, ux, uy)
        search_map = search_dist * map_per_metre

        to_guide = None
        if polygon_layer.crs() != guide_crs:
            to_guide = QgsCoordinateTransform(
                polygon_layer.crs(), guide_crs, QgsProject.instance())

        # กรองด้วยกรอบรอบแนว — ดันลง spatial index ของแหล่งข้อมูล (เร็วกับ PostGIS)
        rect = self._search_rect(p1, p2, search_map, polygon_layer.crs(), guide_crs)
        request = QgsFeatureRequest()
        request.setNoAttributes()
        if rect is not None:
            request.setFilterRect(rect)

        results = []
        for feature in polygon_layer.getFeatures(request):
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            if to_guide is not None:
                geom = QgsGeometry(geom)
                try:
                    geom.transform(to_guide)
                except Exception:  # noqa: BLE001 - แปลงพิกัดไม่ได้ก็ข้ามแปลงนั้นไป
                    continue
            # วงแหวนของโพลิกอนเก็บ vertex แรกซ้ำอีกครั้งตอนปิดวง ถ้าไม่กรอง
            # จุดมุมนั้นจะถูกรายงานซ้ำสองรอบ
            seen = set()
            for vertex in geom.vertices():
                key = (round(vertex.x(), 6), round(vertex.y(), 6))
                if key in seen:
                    continue
                seen.add(key)

                # ระยะตั้งฉากแบบมีเครื่องหมาย (cross product) — บวก = ซ้ายของทิศแนว
                cross = ux * (vertex.y() - p1.y()) - uy * (vertex.x() - p1.x())
                if abs(cross) > search_map:
                    continue
                offset = cross / map_per_metre
                if abs(offset) <= tolerance:
                    continue
                results.append({
                    "fid": feature.id(),
                    "offset": offset,
                    "side": "ซ้าย" if cross > 0 else "ขวา",
                    "point": QgsPointXY(vertex.x(), vertex.y()),
                })

        results.sort(key=lambda r: -abs(r["offset"]))
        self._build_result_layer(results, guide_crs)
        return results, None

    @staticmethod
    def _map_units_per_metre(measurer, origin, ux, uy):
        """หน่วยแผนที่ต่อ 1 เมตร ณ บริเวณแนว

        CRS หน่วยเมตรจะได้ 1.0 ส่วน EPSG:4326 จะได้ค่าเล็ก ๆ (องศาต่อเมตร)
        คำนวณจากของจริงตรงตำแหน่งแนว จึงถูกต้องแม้บนพิกัดภูมิศาสตร์
        """
        probe = QgsPointXY(origin.x() - uy, origin.y() + ux)  # ตั้งฉาก ยาว 1 หน่วยแผนที่
        try:
            metres = measurer.measureLine(origin, probe)
            metres = measurer.convertLengthMeasurement(metres, Qgis.DistanceUnit.Meters)
        except Exception:  # noqa: BLE001
            metres = 0.0
        if metres <= 0:
            return 1.0
        return 1.0 / metres

    @staticmethod
    def _search_rect(p1, p2, search_map, dest_crs, guide_crs):
        """กรอบค้นหา = กรอบของแนว ขยายออกด้วยระยะค้นหา แปลงเข้า CRS ของชั้นโพลิกอน"""
        rect = QgsRectangle(
            min(p1.x(), p2.x()) - search_map, min(p1.y(), p2.y()) - search_map,
            max(p1.x(), p2.x()) + search_map, max(p1.y(), p2.y()) + search_map)
        if dest_crs == guide_crs:
            return rect
        try:
            xform = QgsCoordinateTransform(guide_crs, dest_crs, QgsProject.instance())
            return xform.transformBoundingBox(rect)
        except Exception:  # noqa: BLE001
            return None

    # ==================================================================
    # ชั้นผลตรวจ
    # ==================================================================
    def _build_result_layer(self, results, crs):
        layer = self.result_layer()
        if layer is None:
            authid = crs.authid() if crs and crs.authid() else "EPSG:4326"
            uri = ("Point?crs={}"
                   "&field=fid_poly:integer"
                   "&field=offset:double(10,4)"
                   "&field=side:string(8)"
                   "&field=off_txt:string(24)").format(authid)
            layer = QgsVectorLayer(uri, OFFSET_LAYER_NAME, "memory")
            if not layer.isValid():
                return
            if crs and crs.isValid():
                layer.setCrs(crs)
            renderer = layer.renderer()
            if renderer is not None:
                renderer.setSymbol(_build_offset_symbol())
            layer.setLabeling(_build_offset_labeling())
            layer.setLabelsEnabled(True)
            layer.setReadOnly(True)
            QgsProject.instance().addMapLayer(layer)
            self.result_layer_id = layer.id()

        provider = layer.dataProvider()
        provider.truncate()
        features = []
        for item in results:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(item["point"]))
            feature.setAttributes([
                int(item["fid"]),
                float(item["offset"]),
                item["side"],
                "{:+.3f} ม. ({})".format(item["offset"], item["side"]),
            ])
            features.append(feature)
        if features:
            provider.addFeatures(features)
        layer.updateExtents()
        layer.triggerRepaint()

    def clear_results(self):
        layer = self.result_layer()
        if layer is None:
            return
        layer.dataProvider().truncate()
        layer.updateExtents()
        layer.triggerRepaint()

    # ==================================================================
    # ชั้นข้อมูลหายไปจากโปรเจกต์
    # ==================================================================
    def _on_layers_removed(self, layer_ids):
        changed = False
        if self.guide_layer_id in layer_ids:
            self._disconnect_guide_layer()
            self.guide_layer_id = None
            changed = True
        if self.result_layer_id is not None and self.result_layer_id in layer_ids:
            self.result_layer_id = None
            changed = True
        if changed:
            self.guideChanged.emit()

    def cleanup(self):
        self._disconnect_guide_layer()
        try:
            QgsProject.instance().layersRemoved.disconnect(self._on_layers_removed)
        except (TypeError, RuntimeError):
            pass
