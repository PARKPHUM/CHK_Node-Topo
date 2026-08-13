# -*- coding: utf-8 -*-
"""
line_tools.py — ตัวจัดการชั้นข้อมูลของเครื่องมือวาดเส้น

รับผิดชอบ 2 ชั้นข้อมูล (memory layer) ที่ทำงานคู่กัน:

  1. "เส้นที่วาด (Line)"   — ชั้นที่ผู้ใช้วาดจริง (แก้ไขได้)
                             สไตล์ = เส้นเหลือง + จุด Node สีแดงทุกจุดหัก
  2. "ระยะเส้น (Label)"    — ชั้นสำหรับ "แสดงผล" อย่างเดียว (อ่านอย่างเดียว)
                             แตกเส้นออกเป็นช่วง ๆ ช่วงละ 1 feature เพื่อให้ QGIS
                             ติด label ระยะได้ทีละด้าน แล้ววาง label ข้างเส้น (ไม่ทับแนวเส้น)

ทำไมต้องมีชั้นที่ 2: QGIS ติด label ได้ 1 label ต่อ 1 feature ฉะนั้นถ้าอยากเห็น
ระยะ "แต่ละช่วง" ก็ต้องมี feature แยกต่อช่วง ชั้นนี้จึงถูกสร้างใหม่ทั้งชั้น
(rebuild) ทุกครั้งที่เส้นถูกวาด/แก้ไข/ลบ

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsDistanceArea,
    QgsEditFormConfig,
    QgsFeature,
    QgsGeometry,
    QgsLineSymbol,
    QgsMarkerLineSymbolLayer,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

LINE_LAYER_NAME = "เส้นที่วาด (Line)"
LABEL_LAYER_NAME = "ระยะเส้น (Label)"

# หน่วงก่อน rebuild ชั้น label — ระหว่างลาก vertex QGIS ยิง geometryChanged รัว ๆ
# ถ้า rebuild ทุกครั้งจะหน่วงจนลากไม่ลื่น
REBUILD_DELAY_MS = 150


def _vertex_placement(marker_line):
    """ตั้งให้ marker วางที่ "ทุก vertex" — รองรับชื่อเมธอด/enum ต่างรุ่น QGIS

    QGIS ตั้งแต่ 3.24 ใช้ setPlacements() + Qgis.MarkerLinePlacement
    รุ่นก่อนหน้าใช้ setPlacement() + enum ที่ติดมากับคลาสเอง
    """
    try:
        marker_line.setPlacements(Qgis.MarkerLinePlacement.Vertex)
        return
    except (AttributeError, TypeError):
        pass
    try:
        marker_line.setPlacement(QgsMarkerLineSymbolLayer.Vertex)
    except (AttributeError, TypeError):  # noqa: BLE001 - ไม่ได้ก็แค่ไม่มีจุด Node
        pass


def _build_line_symbol():
    """สไตล์ของชั้นเส้น: เส้นเหลือง + จุด Node สีแดงที่ทุกจุดหัก

    จุด Node ทำด้วย QgsMarkerLineSymbolLayer แบบวางที่ vertex — ได้จุดที่หัวท้าย
    และทุกจุดหักฟรี ๆ ไม่ต้องสร้างชั้น POINT แยกแล้วคอย sync ตามเส้น
    """
    symbol = QgsLineSymbol.createSimple({
        "line_color": "255,255,0,255",
        "line_width": "0.8",
        "capstyle": "round",
        "joinstyle": "round",
    })

    node_marker = QgsMarkerSymbol.createSimple({
        "name": "circle",
        "color": "220,53,69,255",          # แดง Bootstrap #dc3545
        "outline_color": "255,255,255,255",  # ขอบขาว — เห็นชัดบนเส้นเหลือง
        "outline_width": "0.3",
        "size": "2.6",
    })
    node_layer = QgsMarkerLineSymbolLayer()
    node_layer.setSubSymbol(node_marker)
    _vertex_placement(node_layer)
    symbol.appendSymbolLayer(node_layer)
    return symbol


def _build_labeling():
    """ตั้งค่า label ระยะ: วางขนานเส้น เยื้องขึ้นด้านบน 2 มม. (ไม่ทับแนวเส้น)"""
    settings = QgsPalLayerSettings()
    settings.fieldName = "len_txt"   # ข้อความจัดรูปแบบมาแล้วจากฝั่ง Python
    settings.isExpression = False

    # วางตามแนวเส้น
    try:
        settings.placement = Qgis.LabelPlacement.Line
    except AttributeError:
        settings.placement = QgsPalLayerSettings.Line

    # AboveLine   = วางเหนือเส้น (ไม่ทับแนวเส้น)
    # MapOrientation = "เหนือ" อิงทิศแผนที่ ไม่ใช่ทิศที่ลากเส้น
    #                  (ไม่งั้นเส้นที่วาดย้อนกลับ label จะไปโผล่อีกฝั่ง)
    try:
        line_settings = settings.lineSettings()
        line_settings.setPlacementFlags(
            Qgis.LabelLinePlacementFlag.AboveLine
            | Qgis.LabelLinePlacementFlag.MapOrientation)
        settings.setLineSettings(line_settings)
    except (AttributeError, TypeError):  # noqa: BLE001 - รุ่นเก่าใช้ค่าเริ่มต้นไป
        pass

    # ระยะเยื้องจากเส้น — จุดนี้แหละที่ทำให้ label ไม่ทับแนวเส้น
    settings.dist = 2.0
    try:
        settings.distUnits = Qgis.RenderUnit.Millimeters
    except AttributeError:
        pass

    # ตัวอักษร + ขอบขาว ให้อ่านออกทั้งบนภาพถ่ายและแผนที่พื้นอ่อน
    text_format = QgsTextFormat()
    text_format.setFont(QFont("Tahoma", 9))
    text_format.setSize(9)
    text_format.setColor(QColor("#212529"))

    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    buffer_settings.setSize(1.0)
    buffer_settings.setColor(QColor("#ffffff"))
    text_format.setBuffer(buffer_settings)

    settings.setFormat(text_format)
    return QgsVectorLayerSimpleLabeling(settings)


class LineToolLayers(QObject):
    """สร้าง/ดูแลชั้นเส้น + ชั้น label ระยะ ให้ทำงานสอดคล้องกันตลอดเวลา

    เก็บเป็น layer id (ไม่ใช่ตัว layer) เพราะผู้ใช้ลบชั้นทิ้งจาก layer tree ได้
    ทุกเมื่อ — ถือ reference ตรง ๆ ไว้แล้วเรียกใช้ทีหลังจะทำ QGIS ค้าง
    """

    #: ยิงเมื่อชั้นข้อมูลถูกสร้าง/ถูกลบ — ให้ dock ไปปรับสถานะปุ่มเอง
    layersChanged = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.line_layer_id = None
        self.label_layer_id = None
        self.show_labels = True
        self.show_nodes = True

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(REBUILD_DELAY_MS)
        self._timer.timeout.connect(self.rebuild_labels)

        self._connected_layer_id = None
        try:
            QgsProject.instance().layersRemoved.connect(self._on_layers_removed)
        except Exception:  # noqa: BLE001
            pass

    # ==================================================================
    # เข้าถึงชั้นข้อมูล
    # ==================================================================
    def line_layer(self):
        """คืนชั้นเส้น (ถ้ายังอยู่ในโปรเจกต์) หรือ None"""
        if self.line_layer_id is None:
            return None
        return QgsProject.instance().mapLayer(self.line_layer_id)

    def label_layer(self):
        """คืนชั้น label ระยะ (ถ้ายังอยู่ในโปรเจกต์) หรือ None"""
        if self.label_layer_id is None:
            return None
        return QgsProject.instance().mapLayer(self.label_layer_id)

    def has_layers(self):
        return self.line_layer() is not None

    # ==================================================================
    # สร้างชั้นข้อมูล
    # ==================================================================
    def create_layers(self):
        """สร้างชั้นเส้น + ชั้น label ระยะ

        คืน (layer, error_message) — ถ้าสำเร็จ error_message เป็น None
        ถ้ามีชั้นเดิมอยู่แล้วจะคืนชั้นเดิม (บังคับให้มีได้ชุดเดียว)
        """
        existing = self.line_layer()
        if existing is not None:
            self._ensure_label_layer(existing)
            return existing, None

        # ใช้ CRS ของโปรเจกต์ (ตรงกับพิกัดบนจอ) — fallback EPSG:4326
        project = QgsProject.instance()
        project_crs = project.crs()
        authid = project_crs.authid() if project_crs and project_crs.authid() else "EPSG:4326"

        layer = QgsVectorLayer("LineString?crs={}".format(authid), LINE_LAYER_NAME, "memory")
        if not layer.isValid():
            return None, "สร้างชั้นเส้นไม่สำเร็จ"
        if project_crs and project_crs.isValid():
            layer.setCrs(project_crs)

        renderer = layer.renderer()
        if renderer is not None:
            renderer.setSymbol(_build_line_symbol())

        # ปิดฟอร์ม attribute ตอนจบเส้น (ชั้นนี้ไม่มีฟิลด์ให้กรอกอยู่แล้ว)
        cfg = layer.editFormConfig()
        cfg.setSuppress(QgsEditFormConfig.SuppressOn)
        layer.setEditFormConfig(cfg)

        project.addMapLayer(layer)
        self.line_layer_id = layer.id()
        self._apply_node_visibility(layer)
        self._connect_line_layer(layer)

        self._ensure_label_layer(layer)
        self.layersChanged.emit()
        return layer, None

    def _ensure_label_layer(self, line_layer):
        """สร้างชั้น label ระยะให้คู่กับชั้นเส้น ถ้ายังไม่มี"""
        if self.label_layer() is not None:
            return

        crs = line_layer.crs()
        authid = crs.authid() if crs and crs.authid() else "EPSG:4326"
        uri = ("LineString?crs={}"
               "&field=len_m:double(12,3)"
               "&field=len_txt:string(32)").format(authid)
        layer = QgsVectorLayer(uri, LABEL_LAYER_NAME, "memory")
        if not layer.isValid():
            return
        if crs and crs.isValid():
            layer.setCrs(crs)

        # ชั้นนี้มีไว้แบก label อย่างเดียว — เส้นโปร่งใสสนิท
        renderer = layer.renderer()
        if renderer is not None:
            renderer.setSymbol(QgsLineSymbol.createSimple({
                "line_color": "0,0,0,0",
                "line_width": "0.1",
            }))

        layer.setLabeling(_build_labeling())
        layer.setLabelsEnabled(self.show_labels)
        layer.setReadOnly(True)  # กันผู้ใช้เผลอไปแก้ชั้นที่ระบบสร้างเอง

        QgsProject.instance().addMapLayer(layer)
        self.label_layer_id = layer.id()
        self.rebuild_labels()

    # ==================================================================
    # เปิด/ปิดการแสดงผล
    # ==================================================================
    def set_labels_visible(self, visible):
        """เปิด/ปิด label ระยะ (ปุ่มเช็กบนหน้าต่างปลั๊กอิน)"""
        self.show_labels = bool(visible)
        layer = self.label_layer()
        if layer is None:
            return
        layer.setLabelsEnabled(self.show_labels)
        layer.triggerRepaint()

    def set_nodes_visible(self, visible):
        """เปิด/ปิดจุด Node ที่จุดหักของเส้น"""
        self.show_nodes = bool(visible)
        layer = self.line_layer()
        if layer is not None:
            self._apply_node_visibility(layer)

    def _apply_node_visibility(self, layer):
        """เปิด/ปิดเฉพาะ symbol layer ที่เป็นจุด Node — เส้นเหลืองยังอยู่เหมือนเดิม"""
        node_layer = self._node_symbol_layer(layer)
        if node_layer is None:
            return
        node_layer.setEnabled(self.show_nodes)
        layer.triggerRepaint()
        try:
            self.iface.layerTreeView().refreshLayerSymbology(layer.id())
        except Exception:  # noqa: BLE001 - แค่ legend ไม่รีเฟรช ไม่ใช่เรื่องคอขาดบาดตาย
            pass

    @staticmethod
    def _node_symbol_layer(layer):
        renderer = layer.renderer()
        if renderer is None or not hasattr(renderer, "symbol"):
            return None
        symbol = renderer.symbol()
        if symbol is None:
            return None
        for i in range(symbol.symbolLayerCount()):
            sl = symbol.symbolLayer(i)
            if isinstance(sl, QgsMarkerLineSymbolLayer):
                return sl
        return None

    # ==================================================================
    # สร้างชั้น label ระยะใหม่
    # ==================================================================
    def _connect_line_layer(self, layer):
        """ผูก signal ของชั้นเส้น เพื่อ rebuild label ทุกครั้งที่เส้นเปลี่ยน"""
        if self._connected_layer_id == layer.id():
            return
        self._disconnect_line_layer()
        for signal in (layer.featureAdded, layer.geometryChanged,
                       layer.featuresDeleted, layer.afterCommitChanges,
                       layer.editingStopped):
            try:
                signal.connect(self._schedule_rebuild)
            except Exception:  # noqa: BLE001
                pass
        self._connected_layer_id = layer.id()

    def _disconnect_line_layer(self):
        if self._connected_layer_id is None:
            return
        layer = QgsProject.instance().mapLayer(self._connected_layer_id)
        if layer is not None:
            for signal in (layer.featureAdded, layer.geometryChanged,
                           layer.featuresDeleted, layer.afterCommitChanges,
                           layer.editingStopped):
                try:
                    signal.disconnect(self._schedule_rebuild)
                except (TypeError, RuntimeError):
                    pass
        self._connected_layer_id = None

    def _schedule_rebuild(self, *_args):
        """ตั้งเวลา rebuild — รวบหลาย ๆ การเปลี่ยนแปลงติด ๆ กันให้เหลือรอบเดียว"""
        self._timer.start()

    def rebuild_labels(self):
        """สร้าง feature ของชั้น label ใหม่ทั้งชั้น: 1 feature = 1 ช่วงของเส้น"""
        label_layer = self.label_layer()
        line_layer = self.line_layer()
        if label_layer is None:
            return

        provider = label_layer.dataProvider()
        provider.truncate()

        if line_layer is not None:
            measurer = self._distance_area(line_layer)
            features = []
            # getFeatures() เห็น edit buffer อยู่แล้ว — ไม่ต้องรอผู้ใช้กดบันทึกก่อน
            for feature in line_layer.getFeatures():
                geom = feature.geometry()
                if geom is None or geom.isEmpty():
                    continue
                parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
                for part in parts:
                    for i in range(len(part) - 1):
                        p1, p2 = part[i], part[i + 1]
                        metres = self._segment_length(measurer, p1, p2)
                        seg = QgsFeature(label_layer.fields())
                        seg.setGeometry(QgsGeometry.fromPolylineXY([p1, p2]))
                        seg.setAttributes([metres, "{:.3f} ม.".format(metres)])
                        features.append(seg)
            if features:
                provider.addFeatures(features)

        label_layer.updateExtents()
        label_layer.triggerRepaint()

    @staticmethod
    def _distance_area(line_layer):
        """ตัววัดระยะที่ใช้ ellipsoid ของโปรเจกต์ — ได้ "เมตรจริง" เสมอ

        ไม่ใช้ $length ใน expression เพราะให้หน่วยตาม CRS ของชั้นข้อมูล
        ซึ่งจะกลายเป็น "องศา" ทันทีถ้าโปรเจกต์อยู่บน EPSG:4326
        """
        project = QgsProject.instance()
        measurer = QgsDistanceArea()
        measurer.setSourceCrs(line_layer.crs(), project.transformContext())
        try:
            measurer.setEllipsoid(project.ellipsoid())
        except Exception:  # noqa: BLE001 - โปรเจกต์ไม่ได้ตั้ง ellipsoid ก็วัดแบบระนาบไป
            pass
        return measurer

    @staticmethod
    def _segment_length(measurer, p1, p2):
        """ความยาว 1 ช่วง หน่วยเมตร"""
        raw = measurer.measureLine(p1, p2)
        try:
            return measurer.convertLengthMeasurement(raw, Qgis.DistanceUnit.Meters)
        except (AttributeError, TypeError):
            return raw

    # ==================================================================
    # ชั้นข้อมูลหายไปจากโปรเจกต์
    # ==================================================================
    def _on_layers_removed(self, layer_ids):
        """ผู้ใช้ลบชั้นทิ้งจาก layer tree — เคลียร์ id ที่จำไว้ ไม่งั้นจะไปเรียกของที่ตายแล้ว"""
        changed = False

        if self.line_layer_id in layer_ids:
            self._disconnect_line_layer()
            self.line_layer_id = None
            changed = True
            # ชั้น label ไม่มีประโยชน์ถ้าไม่มีเส้นต้นทาง — เก็บกวาดตามไปด้วย
            # แต่ต้องรอให้ QGIS ปล่อย signal นี้จบก่อน (singleShot 0) ไม่งั้นเป็นการ
            # สั่งลบ layer ซ้อนเข้าไปกลางการลบ layer ซึ่งเสี่ยง QGIS ค้าง
            orphan_id = self.label_layer_id
            if orphan_id is not None:
                self.label_layer_id = None
                QTimer.singleShot(0, lambda: self._remove_layer(orphan_id))

        if self.label_layer_id is not None and self.label_layer_id in layer_ids:
            self.label_layer_id = None
            changed = True

        if changed:
            self.layersChanged.emit()

    @staticmethod
    def _remove_layer(layer_id):
        """ลบชั้นออกจากโปรเจกต์ (ถ้ายังอยู่) — เรียกแบบหน่วงจาก _on_layers_removed"""
        project = QgsProject.instance()
        if project.mapLayer(layer_id) is None:
            return
        try:
            project.removeMapLayer(layer_id)
        except Exception:  # noqa: BLE001 - ผู้ใช้อาจลบเองไปแล้วระหว่างนั้น
            pass

    # ==================================================================
    # cleanup (เรียกตอน unload ปลั๊กอิน)
    # ==================================================================
    def cleanup(self):
        self._timer.stop()
        self._disconnect_line_layer()
        try:
            QgsProject.instance().layersRemoved.disconnect(self._on_layers_removed)
        except (TypeError, RuntimeError):
            pass
