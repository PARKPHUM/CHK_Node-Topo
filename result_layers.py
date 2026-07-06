# -*- coding: utf-8 -*-
"""
result_layers.py — สร้าง/จัดการชั้นข้อมูลผลลัพธ์ (Memory layer) แสดงจุดผิดพลาดด้วยสีแดง

สร้างได้ 3 ชั้นตามผลลัพธ์:
  - "ตรวจสอบ: ทับซ้อน (Overlap)"  โพลิกอนสีแดงโปร่งแสง
  - "ตรวจสอบ: ช่องว่าง (Gap)"      โพลิกอนสีแดงโปร่งแสง
  - "ตรวจสอบ: Node ไม่ตรงหมุด"     จุดสีแดง

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsMarkerSymbol,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

# property ที่ใช้ทำเครื่องหมายว่าเป็นชั้นผลลัพธ์ของปลั๊กอินนี้ (ไว้ค้นหา/ลบ)
MARKER_PROPERTY = "node_topology_checker_result"

LAYER_NAMES = {
    "overlap": "ตรวจสอบ: ทับซ้อน (Overlap)",
    "gap": "ตรวจสอบ: ช่องว่าง (Gap)",
    "node": "ตรวจสอบ: Node ไม่ตรงหมุด",
}


class ResultLayerManager:
    """สร้างและลบชั้นผลลัพธ์ พร้อมจัดสไตล์สีแดง"""

    def __init__(self):
        self._layer_ids = []

    # ------------------------------------------------------------------
    def clear(self):
        """ลบชั้นผลลัพธ์เดิมทั้งหมดออกจากโปรเจกต์"""
        project = QgsProject.instance()
        # ลบทั้งจากที่จำ id ไว้ และเผื่อกรณีเหลือค้างให้ค้นจาก property ด้วย
        to_remove = set(self._layer_ids)
        for layer in project.mapLayers().values():
            try:
                if layer.customProperty(MARKER_PROPERTY):
                    to_remove.add(layer.id())
            except Exception:  # noqa: BLE001
                pass
        for layer_id in to_remove:
            if project.mapLayer(layer_id) is not None:
                project.removeMapLayer(layer_id)
        self._layer_ids = []

    # ------------------------------------------------------------------
    def build(self, results, crs):
        """สร้างชั้นผลลัพธ์จาก list ของ dict results (เฉพาะประเภทที่มีข้อมูล)

        :param results: list ของ dict {type, geometry, fids, area, detail}
        :param crs: QgsCoordinateReferenceSystem ของชั้นผลลัพธ์ (CRS ของ POLYGON)
        """
        self.clear()
        by_type = {"overlap": [], "gap": [], "node": []}
        for item in results:
            by_type.setdefault(item["type"], []).append(item)

        if by_type["overlap"]:
            self._create_layer("overlap", "MultiPolygon", by_type["overlap"], crs)
        if by_type["gap"]:
            self._create_layer("gap", "MultiPolygon", by_type["gap"], crs)
        if by_type["node"]:
            self._create_layer("node", "MultiPoint", by_type["node"], crs)

    # ------------------------------------------------------------------
    def _create_layer(self, key, geom_type, items, crs):
        crs_token = crs.authid() if crs and crs.authid() else "EPSG:4326"
        uri = "{}?crs={}".format(geom_type, crs_token)
        layer = QgsVectorLayer(uri, LAYER_NAMES[key], "memory")
        if not layer.isValid():
            return None
        if crs and crs.isValid():
            layer.setCrs(crs)

        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("type", QVariant.String),
            QgsField("source", QVariant.String),
            QgsField("detail", QVariant.String),
            QgsField("area", QVariant.Double),
        ])
        layer.updateFields()

        feats = []
        for item in items:
            geom = item["geometry"]
            if geom is None or geom.isEmpty():
                continue
            g = QgsGeometry_clone(geom)
            if geom_type.startswith("Multi"):
                g.convertToMultiType()
            feat = QgsFeature(layer.fields())
            feat.setGeometry(g)
            feat.setAttributes([
                item.get("type", key),
                ", ".join(str(x) for x in item.get("fids", ())),
                item.get("detail", ""),
                float(item.get("area", 0.0)),
            ])
            feats.append(feat)

        provider.addFeatures(feats)
        layer.updateExtents()
        self._apply_red_style(layer, geom_type)

        # ชั้น Node (จุดไม่ตรงหมุด) ตั้งความโปร่งใสไว้ 40% ตามที่ผู้ใช้ต้องการ
        if key == "node":
            layer.setOpacity(0.4)

        layer.setCustomProperty(MARKER_PROPERTY, True)
        QgsProject.instance().addMapLayer(layer)
        self._layer_ids.append(layer.id())
        return layer

    # ------------------------------------------------------------------
    @staticmethod
    def _apply_red_style(layer, geom_type):
        if geom_type.endswith("Point"):
            symbol = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "color": "255,0,0,255",
                "size": "3.2",
                "outline_color": "255,255,255,255",
                "outline_width": "0.4",
            })
        else:
            symbol = QgsFillSymbol.createSimple({
                "color": "255,0,0,90",
                "outline_color": "255,0,0,255",
                "outline_width": "0.6",
                "outline_style": "solid",
            })
        renderer = layer.renderer()
        if renderer is not None:
            renderer.setSymbol(symbol)
        layer.triggerRepaint()


def QgsGeometry_clone(geom):
    """คัดลอก geometry เพื่อไม่ให้ convertToMultiType ไปแก้ตัวต้นฉบับ"""
    from qgis.core import QgsGeometry
    return QgsGeometry(geom)
