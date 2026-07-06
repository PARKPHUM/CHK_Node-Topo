# -*- coding: utf-8 -*-
"""
topology_dock.py — หน้าต่าง (Dock) หลักของปลั๊กอิน สร้าง UI ด้วยโค้ด (ภาษาไทย)

รวมทุกฟีเจอร์: เลือกชั้น POINT/POLYGON, ตั้ง tolerance, เลือกขอบเขต (ทั้งหมด/หน้าต่าง),
เลือกรายการตรวจ (Overlap/Gap/Node), แสดงผลสีแดง + ตารางผลลัพธ์ (คลิกซูม),
และปุ่มตรวจสอบ/อัปเดตปลั๊กอินจาก GitHub

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsGeometry,
    QgsMapLayerProxyModel,
    QgsProject,
    QgsRectangle,
)
from qgis.gui import QgsDockWidget, QgsMapLayerComboBox

from .check_task import TopologyCheckTask
from .result_layers import ResultLayerManager
from . import update_checker

PLUGIN_DIR = os.path.dirname(__file__)

TYPE_LABEL = {
    "overlap": "ทับซ้อน (Overlap)",
    "gap": "ช่องว่าง (Gap)",
    "node": "Node ไม่ตรงหมุด",
}

GEOM_ROLE = Qt.UserRole + 1

# ==================================================================
# ชุดสี/สไตล์ — โทน Bootstrap ให้เข้าชุดกับปลั๊กอิน Filter_PATH
#   น้ำเงิน #007bff | แดง #dc3545 | เทา #6c757d
#   พื้นอ่อน #f8f9fa | ตัวหนังสือ #333 | ขอบ #ced4da
# ==================================================================
_BTN_BASE = (
    "QPushButton {{"
    " background-color: {bg}; color: white; border: none;"
    " border-radius: 6px; padding: 9px 16px; font-size: 11pt; font-weight: bold;"
    " min-height: 20px; }}"
    "QPushButton:hover:enabled {{ background-color: {hover}; }}"
    "QPushButton:pressed:enabled {{ background-color: {pressed}; }}"
    "QPushButton:disabled {{ background-color: #ced4da; color: #f1f3f5; }}"
)

# ปุ่ม "อัปเดตปลั๊กอิน" — สีแดง
BTN_RED = _BTN_BASE.format(bg="#dc3545", hover="#e15361", pressed="#bd2130")
# ปุ่ม "ตรวจสอบ Topology/Node" — สีฟ้า
BTN_BLUE = _BTN_BASE.format(bg="#007bff", hover="#268fff", pressed="#0062cc")
# ปุ่ม "ล้างผลลัพธ์" — สีเทา
BTN_GRAY = _BTN_BASE.format(bg="#6c757d", hover="#828a91", pressed="#5a6268")

# ปุ่ม "ยกเลิก" — แบบเส้นขอบ (outline) ให้ดูเบากว่า ไม่แย่งความสนใจ
BTN_OUTLINE = (
    "QPushButton {"
    " background-color: #ffffff; color: #dc3545;"
    " border: 1px solid #dc3545; border-radius: 6px;"
    " padding: 9px 16px; font-size: 11pt; font-weight: bold; min-height: 20px; }"
    "QPushButton:hover:enabled { background-color: #fdeaec; }"
    "QPushButton:pressed:enabled { background-color: #f8d7da; }"
    "QPushButton:disabled { color: #ced4da; border-color: #e9ecef; background-color: #ffffff; }"
)

# สไตล์รวมของหน้าต่าง — ธีมสว่างแบบ modern (ให้หน้าตาเหมือนกันทุกธีม QGIS)
DOCK_QSS = """
#ntcContainer, QScrollArea { background-color: #f8f9fa; }
#ntcContainer { font-family: "Segoe UI", "Tahoma", sans-serif; }

QLabel { font-size: 10pt; color: #343a40; }

QGroupBox {
    font-size: 10.5pt;
    font-weight: bold;
    color: #2c3e50;
    background-color: #ffffff;
    border: 1px solid #e3e6ea;
    border-radius: 10px;
    margin-top: 16px;
    padding: 12px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 10px;
    color: #007bff;
}

QComboBox, QDoubleSpinBox {
    font-size: 11pt;
    color: #343a40;
    background-color: #ffffff;
    border: 1px solid #ced4da;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 24px;
}
QComboBox:hover, QDoubleSpinBox:hover { border: 1px solid #86b7fe; }
QComboBox:focus, QDoubleSpinBox:focus { border: 1px solid #007bff; }
QComboBox::drop-down {
    border: none;
    width: 26px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}
QComboBox::down-arrow {
    image: none;
    width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 7px solid #6c757d;
    margin-right: 10px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #343a40;
    border: 1px solid #ced4da;
    border-radius: 6px;
    outline: none;
    selection-background-color: #007bff;
    selection-color: #ffffff;
}

QCheckBox, QRadioButton { font-size: 10.5pt; color: #343a40; spacing: 8px; padding: 3px 0; }

QTableWidget {
    font-size: 10pt;
    background-color: #ffffff;
    color: #343a40;
    border: 1px solid #e3e6ea;
    border-radius: 8px;
    gridline-color: #eef1f4;
}
QTableWidget::item { padding: 3px; }
QTableWidget::item:selected { background-color: #cfe2ff; color: #1a1a1a; }
QHeaderView::section {
    background-color: #eef1f4;
    color: #495057;
    padding: 7px;
    border: none;
    border-bottom: 1px solid #dee2e6;
    font-weight: bold;
    font-size: 10pt;
}

QProgressBar {
    font-size: 9pt;
    color: #343a40;
    background-color: #e9ecef;
    border: none;
    border-radius: 7px;
    text-align: center;
    min-height: 18px;
}
QProgressBar::chunk { background-color: #007bff; border-radius: 7px; }

QScrollArea { border: none; }
QFrame[frameShape="4"] { color: #e3e6ea; }
"""


class TopologyCheckerDock(QgsDockWidget):
    """หน้าต่างหลักของปลั๊กอิน"""

    def __init__(self, iface, parent=None):
        super().__init__("Node & Topology Checker", parent)
        self.iface = iface
        self.setObjectName("NodeTopologyCheckerDock")

        self.result_manager = ResultLayerManager()
        self.task = None            # งานตรวจสอบที่กำลังรัน
        self.update_task = None     # งานตรวจสอบเวอร์ชัน
        self.install_task = None    # งานติดตั้งอัปเดต
        self._result_crs = None
        self._last_transform_drops = 0

        self._build_ui()

    # ==================================================================
    # สร้าง UI
    # ==================================================================
    def _build_ui(self):
        container = QWidget()
        container.setObjectName("ntcContainer")
        container.setStyleSheet(DOCK_QSS)
        root = QVBoxLayout(container)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ---- กลุ่ม: เลือกชั้นข้อมูล ----
        layer_group = QGroupBox("เลือกชั้นข้อมูลสำหรับตรวจสอบ")
        grid = QGridLayout(layer_group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.addWidget(QLabel("ชั้นข้อมูล POINT:"), 0, 0)
        self.point_combo = QgsMapLayerComboBox()
        self.point_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.point_combo.setAllowEmptyLayer(True)
        grid.addWidget(self.point_combo, 0, 1)

        grid.addWidget(QLabel("ชั้นข้อมูล POLYGON:"), 1, 0)
        self.polygon_combo = QgsMapLayerComboBox()
        self.polygon_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.polygon_combo.setAllowEmptyLayer(True)
        grid.addWidget(self.polygon_combo, 1, 1)
        root.addWidget(layer_group)

        # ---- กลุ่ม: ตั้งค่าการตรวจสอบ ----
        setting_group = QGroupBox("ตั้งค่าการตรวจสอบ")
        sv = QVBoxLayout(setting_group)

        # ค่าคลาดเคลื่อนสำหรับ Overlap/Gap (กรองเศษ sliver)
        tol_row = QHBoxLayout()
        tol_row.addWidget(QLabel("ค่าคลาดเคลื่อน Overlap/Gap:"))
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)  # ช่องกรอกธรรมดา ไม่มีลูกศรขึ้น/ลง
        self.tolerance_spin.setDecimals(6)
        self.tolerance_spin.setRange(0.0, 1000000.0)
        self.tolerance_spin.setSingleStep(0.001)
        self.tolerance_spin.setValue(0.005)
        self.tolerance_spin.setMinimumWidth(130)
        self.tolerance_spin.setToolTip(
            "เศษทับซ้อน/ช่องว่างที่บางกว่าค่านี้จะไม่ถูกรายงาน (แก้ปัญหา false positive)")
        tol_row.addWidget(self.tolerance_spin)
        tol_row.addWidget(QLabel("หน่วยแผนที่"))
        tol_row.addStretch(1)
        sv.addLayout(tol_row)

        # ระยะยอมรับสำหรับการตรวจ Node/หมุด (แยกต่างหาก เพราะหมุดมักห่าง vertex มากกว่าเศษ sliver)
        node_tol_row = QHBoxLayout()
        node_tol_row.addWidget(QLabel("ระยะยอมรับหมุด (Node):"))
        self.node_tolerance_spin = QDoubleSpinBox()
        self.node_tolerance_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)  # ช่องกรอกธรรมดา ไม่มีลูกศรขึ้น/ลง
        self.node_tolerance_spin.setDecimals(4)
        self.node_tolerance_spin.setRange(0.0, 1000000.0)
        self.node_tolerance_spin.setSingleStep(0.01)
        self.node_tolerance_spin.setValue(0.10)
        self.node_tolerance_spin.setMinimumWidth(130)
        self.node_tolerance_spin.setToolTip(
            "ถ้ามีหมุด POINT อยู่ห่าง vertex ไม่เกินค่านี้ ถือว่า \"ตรงกัน\"\n"
            "ดู \"ระยะถึงหมุดใกล้สุด\" ในตารางผลลัพธ์ แล้วตั้งค่านี้ให้สูงกว่าระยะที่ยอมรับได้")
        node_tol_row.addWidget(self.node_tolerance_spin)
        node_tol_row.addWidget(QLabel("หน่วยแผนที่"))
        node_tol_row.addStretch(1)
        sv.addLayout(node_tol_row)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("ขอบเขต:"))
        self.scope_all = QRadioButton("ตรวจทั้งหมด")
        self.scope_window = QRadioButton("เฉพาะหน้าต่างปัจจุบัน")
        self.scope_all.setChecked(True)
        self.scope_group = QButtonGroup(self)
        self.scope_group.addButton(self.scope_all)
        self.scope_group.addButton(self.scope_window)
        scope_row.addWidget(self.scope_all)
        scope_row.addWidget(self.scope_window)
        scope_row.addStretch(1)
        sv.addLayout(scope_row)

        sv.addWidget(QLabel("รายการที่ต้องการตรวจ:"))
        self.chk_overlap = QCheckBox("ตรวจการทับซ้อน (Overlap)")
        self.chk_gap = QCheckBox("ตรวจช่องว่าง (Gap)")
        self.chk_node = QCheckBox("ตรวจ Node/Vertex กับ POINT")
        self.chk_overlap.setChecked(True)
        self.chk_gap.setChecked(True)
        self.chk_node.setChecked(True)
        sv.addWidget(self.chk_overlap)
        sv.addWidget(self.chk_gap)
        sv.addWidget(self.chk_node)
        root.addWidget(setting_group)

        # ---- ปุ่มสั่งตรวจ ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_run = QPushButton("▶ ตรวจสอบ Topology/Node")
        self.btn_run.setStyleSheet(BTN_BLUE)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.clicked.connect(self.on_run)
        self.btn_clear = QPushButton("ล้างผลลัพธ์")
        self.btn_clear.setStyleSheet(BTN_GRAY)
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self.on_clear)
        self.btn_cancel = QPushButton("ยกเลิก")
        self.btn_cancel.setStyleSheet(BTN_OUTLINE)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.on_cancel)
        self.btn_cancel.setEnabled(False)
        btn_row.addWidget(self.btn_run, 2)
        btn_row.addWidget(self.btn_clear, 1)
        btn_row.addWidget(self.btn_cancel, 1)
        root.addLayout(btn_row)

        # ---- progress + สรุป ----
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.summary_label = QLabel("ยังไม่ได้ตรวจสอบ")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "font-size: 11pt; font-weight: bold; color: #495057;"
            " background-color: #eef4ff; border: 1px solid #cfe2ff;"
            " border-radius: 6px; padding: 8px 10px;")
        root.addWidget(self.summary_label)

        # ---- ตารางผลลัพธ์ ----
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ประเภท", "FID", "รายละเอียด", "พิกัด"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setToolTip("ดับเบิลคลิกที่แถวเพื่อซูมไปยังตำแหน่งที่ผิดพลาด")
        self.table.cellDoubleClicked.connect(self.on_row_double_clicked)
        root.addWidget(self.table, 1)

        # ---- เส้นคั่น + ส่วนอัปเดต ----
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        upd_row = QHBoxLayout()
        self.btn_update = QPushButton("อัปเดตปลั๊กอิน")
        self.btn_update.setStyleSheet(BTN_RED)
        self.btn_update.setCursor(Qt.PointingHandCursor)
        self.btn_update.clicked.connect(self.on_check_update)
        upd_row.addWidget(self.btn_update)
        upd_row.addStretch(1)
        root.addLayout(upd_row)

        version = update_checker.read_local_version(PLUGIN_DIR)
        self.version_label = QLabel("เวอร์ชันปัจจุบัน: {}".format(version))
        self.version_label.setStyleSheet("font-size: 9pt; color: #868e96;")
        root.addWidget(self.version_label)

        # ใส่ container ลงใน scroll area เผื่อหน้าต่างแคบ
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        self.setWidget(scroll)

    # ==================================================================
    # การตรวจสอบ Topology
    # ==================================================================
    def on_run(self):
        if self.task is not None:
            self.iface.messageBar().pushMessage(
                "กำลังตรวจสอบอยู่", "โปรดรอให้งานปัจจุบันเสร็จก่อน", level=Qgis.Info, duration=4)
            return

        poly_layer = self.polygon_combo.currentLayer()
        point_layer = self.point_combo.currentLayer()

        do_overlap = self.chk_overlap.isChecked()
        do_gap = self.chk_gap.isChecked()
        do_node = self.chk_node.isChecked()

        if not (do_overlap or do_gap or do_node):
            self._warn("กรุณาเลือกรายการตรวจอย่างน้อย 1 อย่าง")
            return
        if poly_layer is None:
            self._warn("กรุณาเลือกชั้นข้อมูล POLYGON")
            return
        if do_node and point_layer is None:
            self._warn("การตรวจ Node ต้องเลือกชั้นข้อมูล POINT ด้วย")
            return

        tolerance = self.tolerance_spin.value()
        node_tolerance = self.node_tolerance_spin.value()

        # เตรียม request ตามขอบเขต
        poly_request = QgsFeatureRequest()
        try:
            poly_request.setNoAttributes()
        except Exception:  # noqa: BLE001
            pass

        if self.scope_window.isChecked():
            rect = self._canvas_rect_in_crs(poly_layer.crs())
            if rect is not None:
                poly_request.setFilterRect(rect)

        polygon_features = self._extract_features(poly_layer, poly_request)
        if not polygon_features:
            self._warn("ไม่พบข้อมูลโพลิกอนในขอบเขตที่เลือก")
            return

        point_features = []
        if do_node:
            transform = None
            if point_layer.crs() != poly_layer.crs():
                transform = QgsCoordinateTransform(
                    point_layer.crs(), poly_layer.crs(), QgsProject.instance())
            pt_request = QgsFeatureRequest()
            try:
                pt_request.setNoAttributes()
            except Exception:  # noqa: BLE001
                pass
            if self.scope_window.isChecked():
                # สำคัญ: กรองหมุดด้วย "ขอบเขตของแปลงที่ถูกดึงมาตรวจ" ไม่ใช่กรอบหน้าต่าง
                # เพราะแปลงที่คาบเกี่ยวขอบหน้าต่างมี vertex อยู่นอกกรอบ — ถ้ากรองหมุด
                # ด้วยกรอบหน้าต่าง หมุดของ vertex เหล่านั้นจะหายไปและถูกฟ้องผิด
                rect = self._features_extent(
                    polygon_features, margin=max(node_tolerance * 2.0, 1.0))
                if rect is not None and point_layer.crs() != poly_layer.crs():
                    try:
                        back = QgsCoordinateTransform(
                            poly_layer.crs(), point_layer.crs(), QgsProject.instance())
                        rect = back.transformBoundingBox(rect)
                    except Exception:  # noqa: BLE001
                        rect = None  # แปลงกรอบไม่ได้ -> ไม่กรอง (ดึงหมุดทั้งหมด ปลอดภัยกว่า)
                if rect is not None:
                    pt_request.setFilterRect(rect)
            point_features = self._extract_features(point_layer, pt_request, transform)

            # แจ้งเตือนกรณีหมุดหายทั้งหมด (เช่น แปลง CRS ไม่สำเร็จ) เพื่อไม่ให้ผลตรวจหลอก
            if self._last_transform_drops > 0:
                self._warn("หมุด POINT จำนวน {} จุด แปลงพิกัด (CRS) ไม่สำเร็จ และถูกข้าม "
                           "— ผลตรวจ Node อาจฟ้องเกินจริง".format(self._last_transform_drops))
            if not point_features:
                self._warn("ไม่พบหมุด POINT ในขอบเขตที่ตรวจ — ทุก Vertex จะถูกรายงานว่าไม่ตรง "
                           "(ตรวจสอบชั้นข้อมูล POINT และ CRS)")

        self._result_crs = poly_layer.crs()

        # เริ่มงาน background
        self.task = TopologyCheckTask(
            polygon_features, point_features, tolerance, node_tolerance,
            do_overlap, do_gap, do_node)
        self.task.set_callback(self.on_check_finished)
        # ใช้ bound method เพื่อให้ Qt เลือก QueuedConnection อัตโนมัติ (progress มาจาก worker thread)
        self.task.progressChanged.connect(self._on_task_progress)

        self._set_running(True)
        QgsApplication.taskManager().addTask(self.task)

    def on_check_finished(self, success, task):
        self._set_running(False)
        current = self.task
        self.task = None

        if not success:
            if task.isCanceled():
                self.summary_label.setText("ยกเลิกการตรวจสอบแล้ว")
            else:
                msg = task.error_message or "ไม่ทราบสาเหตุ"
                self._warn("ตรวจสอบไม่สำเร็จ: {}".format(msg))
                self.summary_label.setText("เกิดข้อผิดพลาด")
            return

        results = task.results
        self.result_manager.build(results, self._result_crs)
        self._populate_table(results)

        s = task.summary
        self.summary_label.setText(
            "พบข้อผิดพลาด: ทับซ้อน {} | ช่องว่าง {} | Node {}  (รวม {} รายการ)".format(
                s["overlap"], s["gap"], s["node"], len(results)))

        if results:
            self.iface.messageBar().pushMessage(
                "ตรวจสอบเสร็จ",
                "พบ {} จุดที่ต้องแก้ไข — ดับเบิลคลิกที่แถวในตารางเพื่อซูม".format(len(results)),
                level=Qgis.Warning, duration=6)
        else:
            self.iface.messageBar().pushMessage(
                "ตรวจสอบเสร็จ", "ไม่พบข้อผิดพลาด ✔", level=Qgis.Success, duration=5)

    def _on_task_progress(self, value):
        self.progress.setValue(int(value))

    def on_cancel(self):
        if self.task is not None:
            self.task.cancel()

    def on_clear(self):
        self.result_manager.clear()
        self.table.setRowCount(0)
        self.summary_label.setText("ล้างผลลัพธ์แล้ว")

    # ==================================================================
    # ตาราง + ซูม
    # ==================================================================
    def _populate_table(self, results):
        self.table.setRowCount(0)
        for item in results:
            row = self.table.rowCount()
            self.table.insertRow(row)

            type_item = QTableWidgetItem(TYPE_LABEL.get(item["type"], item["type"]))
            # เก็บ geometry (CRS ของผลลัพธ์) ไว้ใช้ซูม
            geom = item["geometry"]
            type_item.setData(GEOM_ROLE, QgsGeometry(geom) if geom else None)

            fids = ", ".join(str(x) for x in item.get("fids", ()))
            coord = self._coord_text(item)

            self.table.setItem(row, 0, type_item)
            self.table.setItem(row, 1, QTableWidgetItem(fids))
            self.table.setItem(row, 2, QTableWidgetItem(item.get("detail", "")))
            self.table.setItem(row, 3, QTableWidgetItem(coord))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

    def _coord_text(self, item):
        if "x" in item and "y" in item:
            return "{:.3f}, {:.3f}".format(item["x"], item["y"])
        geom = item.get("geometry")
        if geom is not None and not geom.isEmpty():
            c = geom.centroid().asPoint()
            return "{:.3f}, {:.3f}".format(c.x(), c.y())
        return ""

    def on_row_double_clicked(self, row, _column):
        type_item = self.table.item(row, 0)
        if type_item is None:
            return
        geom = type_item.data(GEOM_ROLE)
        if geom is None or geom.isEmpty() or self._result_crs is None:
            return

        canvas = self.iface.mapCanvas()
        dest_crs = canvas.mapSettings().destinationCrs()

        display_geom = QgsGeometry(geom)
        if self._result_crs != dest_crs:
            xform = QgsCoordinateTransform(self._result_crs, dest_crs, QgsProject.instance())
            try:
                display_geom.transform(xform)
            except Exception:  # noqa: BLE001
                return

        bbox = display_geom.boundingBox()
        if bbox.width() < 1e-9 and bbox.height() < 1e-9:
            # จุดเดี่ยว: ทำกรอบเล็ก ๆ รอบจุด (สัมพัทธ์กับมุมมองปัจจุบัน)
            cur = canvas.extent()
            margin = max(cur.width() * 0.03, 1e-6)
            c = bbox.center()
            bbox = QgsRectangle(c.x() - margin, c.y() - margin,
                                c.x() + margin, c.y() + margin)
        else:
            bbox.scale(1.6)

        canvas.setExtent(bbox)
        canvas.refresh()
        # ไฮไลต์กะพริบสีแดงที่ตำแหน่ง
        try:
            canvas.flashGeometries([QgsGeometry(geom)], self._result_crs)
        except Exception:  # noqa: BLE001
            pass

    # ==================================================================
    # ตรวจสอบ / อัปเดตปลั๊กอิน
    # ==================================================================
    def on_check_update(self):
        if self.update_task is not None or self.install_task is not None:
            return
        if not update_checker.is_repo_configured():
            QMessageBox.information(
                self, "ยังไม่ได้ตั้งค่า repository",
                "ระบบอัปเดตยังไม่ได้กำหนด GitHub repository\n"
                "ผู้ดูแลต้องแก้ค่า DEFAULT_REPO ในไฟล์ update_checker.py "
                "ให้เป็น owner/repository ของโครงการ")
            return

        self.btn_update.setEnabled(False)
        self.btn_update.setText("กำลังตรวจสอบ...")
        self.update_task = update_checker.UpdateCheckTask(PLUGIN_DIR)
        self.update_task.set_callback(self.on_update_checked)
        QgsApplication.taskManager().addTask(self.update_task)

    def on_update_checked(self, success, task):
        self.btn_update.setEnabled(True)
        self.btn_update.setText("ตรวจสอบอัปเดตปลั๊กอิน")
        self.update_task = None

        if not success:
            QMessageBox.warning(
                self, "ตรวจสอบอัปเดตไม่สำเร็จ",
                "ไม่สามารถเชื่อมต่อ GitHub ได้\n\nรายละเอียด: {}".format(
                    task.error_message or "ไม่ทราบสาเหตุ"))
            return

        if task.has_update():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("มีเวอร์ชันใหม่")
            box.setText(
                "มีเวอร์ชันใหม่ให้อัปเดต\n\nเวอร์ชันปัจจุบัน: {}\nเวอร์ชันล่าสุด: {}".format(
                    task.local_version, task.remote_version))
            btn_update = box.addButton("อัปเดตเลย", QMessageBox.AcceptRole)
            btn_web = box.addButton("เปิดหน้า GitHub", QMessageBox.ActionRole)
            box.addButton("ปิด", QMessageBox.RejectRole)
            box.exec_()

            clicked = box.clickedButton()
            if clicked == btn_update:
                self._start_install(task.resolved_branch)
            elif clicked == btn_web:
                self._open_web(update_checker.repo_web_url())
        else:
            QMessageBox.information(
                self, "ใช้เวอร์ชันล่าสุดแล้ว",
                "คุณกำลังใช้ปลั๊กอินเวอร์ชันล่าสุดแล้ว ({})".format(task.local_version))

    def _start_install(self, branch):
        self.install_task = update_checker.UpdateInstallTask(PLUGIN_DIR, branch)
        self.install_task.set_callback(self.on_update_installed)
        self.btn_update.setEnabled(False)
        self.btn_update.setText("กำลังดาวน์โหลด...")
        QgsApplication.taskManager().addTask(self.install_task)

    def on_update_installed(self, success, task):
        self.btn_update.setEnabled(True)
        self.btn_update.setText("ตรวจสอบอัปเดตปลั๊กอิน")
        self.install_task = None

        if success:
            QMessageBox.information(
                self, "อัปเดตเสร็จแล้ว",
                "ดาวน์โหลดและติดตั้งเวอร์ชันใหม่เรียบร้อย\n\n"
                "กรุณาปิดและเปิด QGIS ใหม่ เพื่อเริ่มใช้งานเวอร์ชันล่าสุด")
        else:
            QMessageBox.warning(
                self, "อัปเดตไม่สำเร็จ",
                "ไม่สามารถติดตั้งอัปเดตได้\n\nรายละเอียด: {}".format(
                    task.error_message or "ไม่ทราบสาเหตุ"))

    # ==================================================================
    # ตัวช่วย
    # ==================================================================
    def _extract_features(self, layer, request, transform=None):
        """ดึง (fid, QgsGeometry) ออกจาก layer (คัดลอก geometry ออกมา แปลง CRS ถ้าจำเป็น)

        นับจำนวน feature ที่แปลงพิกัดไม่สำเร็จไว้ใน self._last_transform_drops
        เพื่อให้ผู้เรียกแจ้งเตือนได้ (การทิ้งเงียบ ๆ ทำให้ผลตรวจ Node หลอก)
        """
        out = []
        self._last_transform_drops = 0
        for feat in layer.getFeatures(request):
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            g = QgsGeometry(geom)
            if transform is not None:
                try:
                    g.transform(transform)
                except Exception:  # noqa: BLE001
                    self._last_transform_drops += 1
                    continue
            out.append((feat.id(), g))
        return out

    def _features_extent(self, features, margin):
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

    def _canvas_rect_in_crs(self, dest_crs):
        """คืนกรอบมุมมองแผนที่ปัจจุบัน แปลงเข้าสู่ CRS ที่ต้องการ"""
        canvas = self.iface.mapCanvas()
        extent = canvas.extent()
        src_crs = canvas.mapSettings().destinationCrs()
        if src_crs == dest_crs:
            return extent
        try:
            xform = QgsCoordinateTransform(src_crs, dest_crs, QgsProject.instance())
            return xform.transformBoundingBox(extent)
        except Exception:  # noqa: BLE001
            return None

    def _set_running(self, running):
        self.btn_run.setEnabled(not running)
        self.btn_clear.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.progress.setVisible(running)
        if running:
            self.progress.setValue(0)
            self.summary_label.setText("กำลังตรวจสอบ...")

    def _open_web(self, url):
        from qgis.PyQt.QtGui import QDesktopServices
        from qgis.PyQt.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    def _warn(self, message):
        self.iface.messageBar().pushMessage(
            "แจ้งเตือน", message, level=Qgis.Warning, duration=5)

    # ==================================================================
    # cleanup (เรียกตอน unload ปลั๊กอิน)
    # ==================================================================
    def cleanup(self):
        if self.task is not None:
            try:
                self.task.cancel()
            except Exception:  # noqa: BLE001
                pass
        if self.update_task is not None:
            try:
                self.update_task.cancel()
            except Exception:  # noqa: BLE001
                pass
        if self.install_task is not None:
            try:
                self.install_task.cancel()
            except Exception:  # noqa: BLE001
                pass
