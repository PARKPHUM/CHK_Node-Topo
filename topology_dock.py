# -*- coding: utf-8 -*-
"""
topology_dock.py — หน้าต่าง (Dock) หลักของปลั๊กอิน สร้าง UI ด้วยโค้ด (ภาษาไทย)

รวมทุกฟีเจอร์: เลือกชั้น POINT/POLYGON, ตั้ง tolerance, เลือกขอบเขต (ทั้งหมด/หน้าต่าง),
เลือกรายการตรวจ (Overlap/Gap/Node), ตารางผลลัพธ์ (ดับเบิลคลิกเพื่อซูม+ไฮไลต์กะพริบ),
เครื่องมือวาดเส้น (สร้าง Layer เส้น + digitize) และปุ่มตรวจสอบ/อัปเดตปลั๊กอินจาก GitHub

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

import os

from qgis.PyQt.QtCore import QEvent, QObject, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateTransform,
    QgsEditFormConfig,
    QgsFeatureRequest,
    QgsGeometry,
    QgsLineSymbol,
    QgsMapLayerProxyModel,
    QgsProject,
    QgsRectangle,
    QgsSnappingConfig,
    QgsTolerance,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerFeatureSource,
)
from qgis.gui import (
    QgsAdvancedDigitizingDockWidget,
    QgsDockWidget,
    QgsMapLayerComboBox,
)

from .check_task import TopologyCheckTask
from . import update_checker

PLUGIN_DIR = os.path.dirname(__file__)

TYPE_LABEL = {
    "overlap": "ทับซ้อน (Overlap)",
    "gap": "ช่องว่าง (Gap)",
    "node": "Node ไม่ตรงหมุด",
}

GEOM_ROLE = Qt.UserRole + 1

# ค่า tolerance ตายตัว (หน่วยเมตร) — งานอยู่บน CRS หน่วยเมตร เช่น EPSG:24047 UTM Zone 47N
# ตั้งเป็นค่า default ในโค้ด จึงไม่ต้องมีช่องกรอกบนหน้าต่าง
DEFAULT_TOLERANCE = 0.001       # ค่าคลาดเคลื่อน Overlap/Gap
DEFAULT_NODE_TOLERANCE = 0.001  # ระยะยอมรับหมุด (Node)

# ==================================================================
# ชุดสี/สไตล์ — โทน Bootstrap ให้เข้าชุดกับปลั๊กอิน Filter_PATH
#   น้ำเงิน #007bff | แดง #dc3545 | เทา #6c757d
#   พื้นอ่อน #f8f9fa | ตัวหนังสือ #333 | ขอบ #ced4da
# ==================================================================
# ขนาด/สไตล์อ้างอิงตามปุ่ม "อัปเดตปลั๊กอิน" ของ Filter_PATH:
#   font-size 10pt, ตัวหนา, padding 6px, border-radius 4px
_BTN_BASE = (
    "QPushButton {{"
    " background-color: {bg}; color: white; border: none;"
    " border-radius: 4px; padding: 6px; font-size: 10pt; font-weight: bold; }}"
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
# ปุ่ม "สร้าง Layer เส้น" — สีเขียว (Bootstrap success)
BTN_GREEN = _BTN_BASE.format(bg="#28a745", hover="#34ce57", pressed="#1e7e34")

# ปุ่ม "ยกเลิก" — แบบเส้นขอบ (outline) ให้ดูเบากว่า ไม่แย่งความสนใจ
BTN_OUTLINE = (
    "QPushButton {"
    " background-color: #ffffff; color: #dc3545;"
    " border: 1px solid #dc3545; border-radius: 4px;"
    " padding: 6px; font-size: 10pt; font-weight: bold; }"
    "QPushButton:hover:enabled { background-color: #fdeaec; }"
    "QPushButton:pressed:enabled { background-color: #f8d7da; }"
    "QPushButton:disabled { color: #ced4da; border-color: #e9ecef; background-color: #ffffff; }"
)

# สไตล์รวมของหน้าต่าง — โทน/ขนาดฟอนต์อ้างอิงตาม Filter_PATH (Bootstrap)
#   QLabel 10pt ตัวหนา #333 | QComboBox 10pt (ลูกศร ▼ แบบ native) | ช่องกรอก 11pt
DOCK_QSS = """
#ntcContainer { background-color: #f8f9fa; }

QLabel { font-size: 10pt; font-weight: bold; color: #333; }

QGroupBox {
    font-size: 10pt;
    font-weight: bold;
    color: #2c3e50;
    background-color: #ffffff;
    border: 1px solid #e3e6ea;
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 2px 8px;
    color: #007bff;
}

/* Dropdown ใช้สไตล์เดียวกับ Filter_PATH เป๊ะ ๆ:
   กำหนดแค่ font/padding/min-height เท่านั้น ปล่อยให้เป็น combobox แบบ native
   (ไม่ตีกรอบ ไม่ทำลูกศรเอง) จะได้ลูกศร ▼ แบบเรียบ ไม่มีกรอบสี่เหลี่ยมครอบ */
QComboBox { font-size: 10pt; padding: 3px; min-height: 24px; }

QCheckBox, QRadioButton { font-size: 10pt; font-weight: bold; color: #333; spacing: 7px; padding: 2px 0; }

QTableWidget {
    font-size: 10pt;
    background-color: #ffffff;
    color: #333;
    border: 1px solid #e3e6ea;
    border-radius: 6px;
    gridline-color: #eef1f4;
}
QTableWidget::item { padding: 3px; }
QTableWidget::item:selected { background-color: #cfe2ff; color: #1a1a1a; }
QHeaderView::section {
    background-color: #eef1f4;
    color: #495057;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #dee2e6;
    font-weight: bold;
    font-size: 10pt;
}

QProgressBar {
    font-size: 9pt;
    color: #333;
    background-color: #e9ecef;
    border: none;
    border-radius: 5px;
    text-align: center;
    min-height: 16px;
}
QProgressBar::chunk { background-color: #007bff; border-radius: 5px; }

QFrame[frameShape="4"] { color: #e3e6ea; }
"""


def _lock_mode(name):
    """คืนค่า enum LockMode ตามชื่อ — รองรับตำแหน่ง enum ที่ต่างกันตามรุ่น QGIS

    QGIS บางรุ่นวาง enum ไว้ที่ CadConstraint ตรง ๆ บางรุ่นซ้อนใน LockMode อีกชั้น
    """
    constraint_cls = QgsAdvancedDigitizingDockWidget.CadConstraint
    holder = getattr(constraint_cls, "LockMode", constraint_cls)
    return getattr(holder, name, None)


class _ShiftAngleFilter(QObject):
    """ดักปุ่ม Shift บนแผนที่ เพื่อเปิด/ปิดการล็อกมุมระหว่างวาดเส้น

    ใช้ event filter แทนการเขียน map tool เอง — จึงยังได้พฤติกรรมมาตรฐานของ
    เครื่องมือ Add Feature ครบ (คลิกขวาจบเส้น, undo, snapping)
    """

    def __init__(self, dock):
        super().__init__(dock)
        self._dock = dock

    def eventFilter(self, obj, event):  # noqa: N802 (ชื่อกำหนดโดย Qt)
        try:
            etype = event.type()
            if etype == QEvent.KeyPress and event.key() == Qt.Key_Shift:
                self._dock.apply_angle_lock(True)
            elif etype == QEvent.KeyRelease and event.key() == Qt.Key_Shift:
                self._dock.apply_angle_lock(False)
        except Exception:  # noqa: BLE001 - ห้ามให้ event filter พังจนคลิกแผนที่ไม่ได้
            pass
        return False  # ส่ง event ต่อเสมอ ไม่กลืน


class TopologyCheckerDock(QgsDockWidget):
    """หน้าต่างหลักของปลั๊กอิน"""

    def __init__(self, iface, parent=None):
        version = update_checker.read_local_version(PLUGIN_DIR)
        super().__init__("Node & Topology Checker  Version {}".format(version), parent)
        self.iface = iface
        self.setObjectName("NodeTopologyCheckerDock")

        self.task = None            # งานตรวจสอบที่กำลังรัน
        self.update_task = None     # งานตรวจสอบเวอร์ชัน
        self.install_task = None    # งานติดตั้งอัปเดต
        self._result_crs = None
        self.line_layer_id = None   # ชั้นเส้นที่วาด (บังคับมีได้ชั้นเดียว)

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
        grid.addWidget(QLabel("Layer หมุด (POINT):"), 0, 0)
        self.point_combo = QgsMapLayerComboBox()
        self.point_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.point_combo.setAllowEmptyLayer(True)
        grid.addWidget(self.point_combo, 0, 1)

        grid.addWidget(QLabel("Layer แปลง (POLYGON):"), 1, 0)
        self.polygon_combo = QgsMapLayerComboBox()
        self.polygon_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.polygon_combo.setAllowEmptyLayer(True)
        grid.addWidget(self.polygon_combo, 1, 1)
        root.addWidget(layer_group)

        # ---- กลุ่ม: เครื่องมือวาดเส้น (Line) ----
        # สร้างชั้นเส้น (สีเหลือง) ได้ชั้นเดียว แล้ววาด feature ลงในชั้นนั้น
        line_group = QGroupBox("เครื่องมือวาดเส้น (Line)")
        lv = QVBoxLayout(line_group)
        lv.setSpacing(8)
        lg = QHBoxLayout()
        lg.setSpacing(8)
        self.btn_new_line = QPushButton("สร้าง Layer เส้น")
        self.btn_new_line.setStyleSheet(BTN_GREEN)
        self.btn_new_line.setCursor(Qt.PointingHandCursor)
        self.btn_new_line.clicked.connect(self.on_new_line_layer)
        self.btn_draw_line = QPushButton("✎ วาดเส้น")
        self.btn_draw_line.setStyleSheet(BTN_BLUE)
        self.btn_draw_line.setCursor(Qt.PointingHandCursor)
        self.btn_draw_line.clicked.connect(self.on_draw_line)
        self.btn_draw_line.setEnabled(False)
        self.btn_draw_line.setToolTip(
            "คลิกซ้ายเพื่อลงจุด, คลิกขวาเพื่อจบเส้น (วาดได้หลายเส้น)\n"
            "เปิด snapping แบบ Vertex ให้อัตโนมัติ — เคอร์เซอร์จะดูดเข้าหามุม/หมุด")
        lg.addWidget(self.btn_new_line, 1)
        lg.addWidget(self.btn_draw_line, 1)
        lv.addLayout(lg)

        # เปิด/ปิดแถบ "ดิจิไทซ์ขั้นสูง" ของ QGIS — ใช้ล็อกมุม/ระยะขณะวาดเส้น
        # (ไม่เด้งเอง ผู้ใช้กดเปิดเมื่อต้องการ แล้วพิมพ์องศาในแถบได้เอง)
        self.chk_cad = QCheckBox("ล็อกมุม/ระยะ (แถบดิจิไทซ์ขั้นสูง)")
        self.chk_cad.setToolTip(
            "เปิดแถบ 'ดิจิไทซ์ขั้นสูง' ของ QGIS สำหรับล็อกแนวเส้น\n"
            "• ช่อง a = มุม (พิมพ์เองได้ เช่น 30, 45, 90) แล้วกดแม่กุญแจเพื่อล็อก\n"
            "• ช่อง d = ระยะ (พิมพ์ความยาวเป๊ะ ๆ ได้)\n"
            "• หรือเลือกองศามาตรฐานจาก dropdown ในแถบ")
        self.chk_cad.toggled.connect(self.on_toggle_cad)
        lv.addWidget(self.chk_cad)

        # ---- ล็อกมุมด้วยปุ่ม Shift ----
        angle_row = QHBoxLayout()
        angle_row.setSpacing(8)
        self.chk_shift_lock = QCheckBox("กด Shift ค้างเพื่อล็อกมุม")
        self.chk_shift_lock.setChecked(True)
        self.chk_shift_lock.setToolTip(
            "ระหว่างวาดเส้น กดปุ่ม Shift ค้างไว้ = ล็อกมุมตามองศาที่ตั้ง\n"
            "ปล่อย Shift = กลับมาลากอิสระเหมือนเดิม")
        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setRange(0.0, 360.0)
        self.spin_angle.setDecimals(1)
        self.spin_angle.setSingleStep(15.0)
        self.spin_angle.setValue(90.0)   # ค่าเริ่มต้น: ตั้งฉากกับช่วงก่อนหน้า
        self.spin_angle.setSuffix(" °")
        self.spin_angle.setFixedWidth(90)
        self.spin_angle.setToolTip("องศาที่จะล็อกเมื่อกด Shift (เทียบกับเส้นช่วงก่อนหน้า)")
        angle_row.addWidget(self.chk_shift_lock, 1)
        angle_row.addWidget(self.spin_angle)
        lv.addLayout(angle_row)
        root.addWidget(line_group)

        # ดักปุ่ม Shift บน canvas (ติดตั้งครั้งเดียว ถอดตอน unload)
        self._shift_filter = _ShiftAngleFilter(self)
        try:
            self.iface.mapCanvas().installEventFilter(self._shift_filter)
        except Exception:  # noqa: BLE001
            self._shift_filter = None

        # ---- กลุ่ม: ตั้งค่าการตรวจสอบ ----
        # ค่า tolerance ใช้ค่า default ตายตัวในโค้ด (Overlap/Gap = Node = 0.001 ม.)
        # จึงไม่มีช่องกรอกบนหน้าต่าง เพื่อให้พื้นที่ตารางผลลัพธ์สูงขึ้น
        setting_group = QGroupBox("ตั้งค่าการตรวจสอบ")
        sv = QVBoxLayout(setting_group)

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
        self.chk_gap.setToolTip(
            "Gap ตรวจทั้งชั้นเสมอเพื่อความถูกต้อง (ไม่จำกัดตามหน้าต่าง)")
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
            "font-size: 10pt; font-weight: bold; color: #495057;"
            " background-color: #eef4ff; border: 1px solid #cfe2ff;"
            " border-radius: 4px; padding: 7px 9px;")
        root.addWidget(self.summary_label)

        # ---- ตารางผลลัพธ์ ----
        # Node = ระยะห่างจากหมุดใกล้สุด (เมตร) | Overlap/Gap = พื้นที่ (ตร.ม.)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ประเภท", "FID", "ระยะห่าง / พื้นที่"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
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

        self.setWidget(container)

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

        window_scope = self.scope_window.isChecked()

        # เตรียม request ของ POLYGON (ตัด attribute ออก — ลดข้อมูลที่ดึงจากฐานข้อมูล)
        poly_request = QgsFeatureRequest()
        poly_request.setNoAttributes()
        # กรอบหน้าต่างใน CRS ของ POLYGON — ใช้กรอง Overlap/Node ตามหน้าต่าง
        window_rect = None
        if window_scope:
            window_rect = self._canvas_rect_in_crs(poly_layer.crs())
            # Gap ต้องเห็นแปลงที่ล้อมรอบช่องว่างครบ จึงตรวจทั้งชั้นเสมอ:
            # ถ้าเลือก Gap → ไม่กรอง fetch (ดึงทั้งชั้น) แล้วไปกรอง Overlap/Node
            # ในหน่วยความจำที่ฝั่ง task; ถ้าไม่ได้เลือก Gap → กรองที่ fetch เหมือนเดิม
            if not do_gap and window_rect is not None:
                poly_request.setFilterRect(window_rect)

        # เตรียม request + transform ของ POINT (การดึงจริงทำใน background)
        point_source = None
        point_request = None
        point_transform = None
        rect_back_transform = None
        if do_node:
            point_source = QgsVectorLayerFeatureSource(point_layer)
            point_request = QgsFeatureRequest()
            point_request.setNoAttributes()
            if point_layer.crs() != poly_layer.crs():
                point_transform = QgsCoordinateTransform(
                    point_layer.crs(), poly_layer.crs(), QgsProject.instance())
                rect_back_transform = QgsCoordinateTransform(
                    poly_layer.crs(), point_layer.crs(), QgsProject.instance())

        self._result_crs = poly_layer.crs()

        # เริ่มงาน background — การดึง feature (รวมชั้นจาก PostgreSQL/PostGIS)
        # ทำในเธรดงานผ่าน QgsVectorLayerFeatureSource จึงไม่บล็อกหน้าจอ QGIS
        self.task = TopologyCheckTask(
            QgsVectorLayerFeatureSource(poly_layer), poly_request,
            DEFAULT_TOLERANCE, DEFAULT_NODE_TOLERANCE,
            do_overlap, do_gap, do_node,
            point_source=point_source, point_request=point_request,
            point_transform=point_transform, rect_back_transform=rect_back_transform,
            window_scope=window_scope, window_rect=window_rect,
            poly_count_hint=max(poly_layer.featureCount(), 0),
            point_count_hint=max(point_layer.featureCount(), 0) if point_layer else 0)
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

        if task.polygon_count == 0:
            self._warn("ไม่พบข้อมูลโพลิกอนในขอบเขตที่เลือก")
            self.summary_label.setText("ไม่พบข้อมูลโพลิกอนในขอบเขตที่เลือก")
            return

        # แจ้งเตือนปัญหาข้อมูลหมุดที่พบระหว่างดึงข้อมูลใน background
        if task.do_node:
            if task.transform_drops > 0:
                self._warn("หมุด POINT จำนวน {} จุด แปลงพิกัด (CRS) ไม่สำเร็จ และถูกข้าม "
                           "— ผลตรวจ Node อาจฟ้องเกินจริง".format(task.transform_drops))
            if task.point_count == 0:
                self._warn("ไม่พบหมุด POINT ในขอบเขตที่ตรวจ — ทุก Vertex จะถูกรายงานว่าไม่ตรง "
                           "(ตรวจสอบชั้นข้อมูล POINT และ CRS)")

        results = task.results
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
        self.table.setRowCount(0)
        self.summary_label.setText("ล้างผลลัพธ์แล้ว")

    # ==================================================================
    # เครื่องมือวาดเส้น (Line)
    # ==================================================================
    def _line_layer(self):
        """คืนชั้นเส้นที่วาดไว้ (ถ้ายังอยู่ในโปรเจกต์) หรือ None"""
        if self.line_layer_id is None:
            return None
        return QgsProject.instance().mapLayer(self.line_layer_id)

    def on_new_line_layer(self):
        """สร้างชั้นเส้น (memory) สีเหลือง — บังคับให้มีได้ชั้นเดียว"""
        existing = self._line_layer()
        if existing is not None:
            self.iface.setActiveLayer(existing)
            self._warn("มี Layer เส้นอยู่แล้ว — วาดเส้นลงในชั้นเดิมได้เลย")
            self.btn_draw_line.setEnabled(True)
            return

        # ใช้ CRS ของโปรเจกต์ (ตรงกับพิกัดบนจอ) — fallback EPSG:4326
        project_crs = QgsProject.instance().crs()
        authid = project_crs.authid() if project_crs and project_crs.authid() else "EPSG:4326"
        layer = QgsVectorLayer(
            "LineString?crs={}".format(authid), "เส้นที่วาด (Line)", "memory")
        if not layer.isValid():
            self._warn("สร้างชั้นเส้นไม่สำเร็จ")
            return
        if project_crs and project_crs.isValid():
            layer.setCrs(project_crs)

        # สไตล์เส้นสีเหลือง หนา 0.8
        symbol = QgsLineSymbol.createSimple({
            "line_color": "255,255,0,255",
            "line_width": "0.8",
            "capstyle": "round",
            "joinstyle": "round",
        })
        renderer = layer.renderer()
        if renderer is not None:
            renderer.setSymbol(symbol)

        # ปิดฟอร์ม attribute ตอนจบเส้น (ชั้นนี้ไม่มีฟิลด์ให้กรอกอยู่แล้ว)
        cfg = layer.editFormConfig()
        cfg.setSuppress(QgsEditFormConfig.SuppressOn)
        layer.setEditFormConfig(cfg)

        QgsProject.instance().addMapLayer(layer)
        self.line_layer_id = layer.id()
        self.btn_draw_line.setEnabled(True)
        self.iface.setActiveLayer(layer)
        self.iface.messageBar().pushMessage(
            "สร้าง Layer เส้นแล้ว",
            "กด '✎ วาดเส้น' เพื่อเริ่มวาด (คลิกขวาเพื่อจบเส้น)",
            level=Qgis.Info, duration=5)

    def _enable_vertex_snapping(self):
        """เปิด snapping แบบ Vertex ทุกชั้น — เคอร์เซอร์จะดูดเข้าหามุม/หมุด
        และ QGIS จะวาดตัวชี้ (snap indicator) ตรงตำแหน่ง vertex ที่จะ snap ให้เอง
        """
        project = QgsProject.instance()
        config = project.snappingConfig()
        config.setEnabled(True)
        config.setMode(QgsSnappingConfig.AllLayers)
        # QGIS ใหม่ใช้ flag enum (setTypeFlag) ส่วนรุ่นเก่าใช้ setType
        try:
            config.setTypeFlag(QgsSnappingConfig.VertexFlag)
        except (AttributeError, TypeError):
            config.setType(QgsSnappingConfig.Vertex)
        config.setTolerance(12)
        config.setUnits(QgsTolerance.Pixels)
        project.setSnappingConfig(config)

    def _apply_cad(self, enabled):
        """เปิด/ปิดแถบดิจิไทซ์ขั้นสูงของ QGIS (ล็อกมุม/ระยะ)

        ใช้ enableAction() ซึ่งเป็นปุ่มสลับ "เปิดเครื่องมือดิจิไทซ์ขั้นสูง" ของ QGIS เอง
        จึงได้พฤติกรรมตรงกับที่ผู้ใช้กดเองในโปรแกรม
        """
        cad = self.iface.cadDockWidget()
        if cad is None:
            return False
        action = cad.enableAction()
        if action is not None and action.isEnabled() and action.isChecked() != enabled:
            action.trigger()
        cad.setVisible(enabled)
        return True

    def apply_angle_lock(self, locked):
        """ล็อก/ปลดล็อกมุมของการวาดเส้น (เรียกจากตัวดักปุ่ม Shift)

        ใช้ระบบ constraint ของแถบดิจิไทซ์ขั้นสูง: ตั้งมุมแบบ "สัมพัทธ์กับช่วงก่อนหน้า"
        แล้วสั่ง HardLock — QGIS จะบังคับแนวเส้นให้เอง พร้อมแสดงเส้นประบอกแนว
        """
        if not self.chk_shift_lock.isChecked():
            return
        # ล็อกมุมต้องมีชั้นเส้นที่กำลังแก้ไขอยู่ ไม่งั้นไปกวนการวาดชั้นอื่นของผู้ใช้
        layer = self._line_layer()
        if layer is None or not layer.isEditable():
            return

        cad = self.iface.cadDockWidget()
        if cad is None:
            return
        constraint = cad.constraintAngle()
        if constraint is None:
            return

        if locked:
            # CAD ต้องเปิดก่อน constraint ถึงจะมีผล
            if not cad.cadEnabled():
                self._apply_cad(True)
                self.chk_cad.blockSignals(True)
                self.chk_cad.setChecked(True)
                self.chk_cad.blockSignals(False)
            constraint.setRelative(True)
            constraint.setValue(float(self.spin_angle.value()), True)
            mode = _lock_mode("HardLock")
        else:
            mode = _lock_mode("NoLock")
        if mode is not None:
            constraint.setLockMode(mode)

    def on_toggle_cad(self, checked):
        """ผู้ใช้กดเปิด/ปิดช่อง 'ล็อกมุม/ระยะ'"""
        try:
            ok = self._apply_cad(checked)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok and checked:
            self._warn("เปิดแถบดิจิไทซ์ขั้นสูงไม่สำเร็จ — เปิดเองได้ที่เมนู "
                       "มุมมอง > แผงหน้าต่าง > ดิจิไทซ์ขั้นสูง")

    def on_draw_line(self):
        """เริ่มวาดเส้นลงในชั้นเส้น: เปิด snapping + editing + เครื่องมือ Add Feature"""
        layer = self._line_layer()
        if layer is None:
            self.line_layer_id = None
            self.btn_draw_line.setEnabled(False)
            self._warn("กรุณาสร้าง Layer เส้นก่อน")
            return

        # เปิด snapping ก่อน เพื่อให้เคอร์เซอร์ดูดเข้าหา vertex พร้อมตัวชี้ตำแหน่ง
        try:
            self._enable_vertex_snapping()
        except Exception:  # noqa: BLE001 - ตั้ง snapping ไม่ได้ ก็ยังวาดเส้นได้ตามปกติ
            pass
        self.iface.setActiveLayer(layer)
        if not layer.isEditable():
            layer.startEditing()
        # เครื่องมือ Add Feature มาตรฐาน: คลิกซ้ายลงจุด, คลิกขวาจบเส้น (ฟรี)
        self.iface.actionAddFeature().trigger()
        # ถ้าผู้ใช้ติ๊ก "ล็อกมุม/ระยะ" ไว้ ให้แน่ใจว่าแถบยังเปิดอยู่หลังสลับเครื่องมือ
        # (ต้องทำหลัง trigger เพราะ CAD ผูกกับ map tool ที่กำลังใช้งาน)
        if self.chk_cad.isChecked():
            try:
                self._apply_cad(True)
            except Exception:  # noqa: BLE001
                pass

    # ==================================================================
    # ตาราง + ซูม
    # ==================================================================
    def _populate_table(self, results):
        dist_abbr, area_abbr = self._unit_abbr()
        self.table.setRowCount(0)
        for item in results:
            row = self.table.rowCount()
            self.table.insertRow(row)

            type_item = QTableWidgetItem(TYPE_LABEL.get(item["type"], item["type"]))
            # เก็บ geometry (CRS ของผลลัพธ์) ไว้ใช้ซูม
            geom = item["geometry"]
            type_item.setData(GEOM_ROLE, QgsGeometry(geom) if geom else None)

            fids = ", ".join(str(x) for x in item.get("fids", ()))
            measure = self._measure_text(item, dist_abbr, area_abbr)

            self.table.setItem(row, 0, type_item)
            self.table.setItem(row, 1, QTableWidgetItem(fids))
            self.table.setItem(row, 2, QTableWidgetItem(measure))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _measure_text(self, item, dist_abbr, area_abbr):
        """คอลัมน์ 'ระยะห่าง / พื้นที่':
        Node = ระยะจาก vertex ถึงหมุดใกล้สุด (หน่วยระยะทาง)
        Overlap/Gap = พื้นที่ที่ผิดพลาด (หน่วยพื้นที่)
        """
        if item.get("type") == "node":
            d = item.get("distance")
            if d is None:
                return "ไม่มีหมุดใกล้เคียง"
            return "{:.3f} {}".format(d, dist_abbr)
        return "{:.3f} {}".format(item.get("area", 0.0), area_abbr)

    def _unit_abbr(self):
        """คืน (ตัวย่อหน่วยระยะ, ตัวย่อหน่วยพื้นที่) ตาม CRS ของผลลัพธ์"""
        crs = self._result_crs
        if crs is not None and crs.mapUnits() == QgsUnitTypes.DistanceMeters:
            return "ม.", "ตร.ม."
        if crs is not None and crs.mapUnits() == QgsUnitTypes.DistanceDegrees:
            return "°", "ตร.°"
        if crs is not None and crs.mapUnits() == QgsUnitTypes.DistanceFeet:
            return "ฟุต", "ตร.ฟุต"
        return "หน่วย", "ตร.หน่วย"

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
        self.btn_update.setText("อัปเดตปลั๊กอิน")
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
            box.setWindowTitle("พบเวอร์ชันใหม่")
            box.setText(
                "🎉 พบเวอร์ชันใหม่บน GitHub แล้ว!\n\n"
                "เวอร์ชันใหม่ : {}\n"
                "เวอร์ชันของคุณ : {}\n\n"
                "ต้องการดาวน์โหลดและติดตั้งเลยหรือไม่?\n"
                "(หลังติดตั้งเสร็จ ต้องปิดและเปิด QGIS ใหม่)".format(
                    task.remote_version, task.local_version))
            btn_update = box.addButton("อัปเดตเลย", QMessageBox.AcceptRole)
            box.addButton("ไว้ก่อน", QMessageBox.RejectRole)
            box.setDefaultButton(btn_update)
            box.exec_()

            if box.clickedButton() == btn_update:
                self._start_install(task.resolved_branch)
        elif (update_checker.parse_version(task.local_version)
                > update_checker.parse_version(task.remote_version)):
            # เครื่องนักพัฒนา: โค้ดในเครื่องใหม่กว่าที่ push ขึ้น GitHub
            # (แยกข้อความออกมา ไม่งั้นจะอ่านว่า "ล่าสุดแล้ว" ทั้งที่ยังไม่ได้เผยแพร่)
            QMessageBox.information(
                self, "เวอร์ชันในเครื่องใหม่กว่า GitHub",
                "ไม่มีอะไรให้อัปเดต — เครื่องคุณใหม่กว่าบน GitHub\n\n"
                "เวอร์ชันในเครื่อง : {}\n"
                "เวอร์ชันบน GitHub : {}\n\n"
                "ถ้าต้องการเผยแพร่เวอร์ชันนี้ ให้ commit + push ขึ้น GitHub ก่อน".format(
                    task.local_version, task.remote_version))
        else:
            QMessageBox.information(
                self, "ใช้เวอร์ชันล่าสุดแล้ว",
                "คุณกำลังใช้ปลั๊กอินเวอร์ชันล่าสุดแล้ว ✔\n\n"
                "เวอร์ชันในเครื่อง : {}\n"
                "เวอร์ชันบน GitHub : {}".format(
                    task.local_version, task.remote_version))

    def _start_install(self, branch):
        self.install_task = update_checker.UpdateInstallTask(PLUGIN_DIR, branch)
        self.install_task.set_callback(self.on_update_installed)
        self.btn_update.setEnabled(False)
        self.btn_update.setText("กำลังดาวน์โหลด...")
        QgsApplication.taskManager().addTask(self.install_task)

    def on_update_installed(self, success, task):
        self.btn_update.setEnabled(True)
        self.btn_update.setText("อัปเดตปลั๊กอิน")
        self.install_task = None

        if success:
            # ใช้ไอคอนเตือน (ไม่ใช่ information) เพราะถ้าไม่รีสตาร์ท
            # ปลั๊กอินจะยังรันโค้ดเดิมในหน่วยความจำ — ผู้ใช้มักพลาดจุดนี้
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("อัปเดตเสร็จแล้ว — ต้องปิด/เปิด QGIS ใหม่")
            box.setText(
                "ดาวน์โหลดและติดตั้งเวอร์ชันใหม่เรียบร้อยแล้ว ✔\n\n"
                "⚠ กรุณา \"ปิดโปรแกรม QGIS แล้วเปิดใหม่\" ตอนนี้\n\n"
                "เวอร์ชันใหม่จะเริ่มทำงานหลังเปิด QGIS ใหม่เท่านั้น\n"
                "ถ้ายังไม่ปิด/เปิดใหม่ ปลั๊กอินจะยังทำงานด้วยโค้ดเวอร์ชันเดิมอยู่")
            box.exec_()
        else:
            QMessageBox.warning(
                self, "อัปเดตไม่สำเร็จ",
                "ไม่สามารถติดตั้งอัปเดตได้\n\nรายละเอียด: {}".format(
                    task.error_message or "ไม่ทราบสาเหตุ"))

    # ==================================================================
    # ตัวช่วย
    # ==================================================================
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

    def _warn(self, message):
        self.iface.messageBar().pushMessage(
            "แจ้งเตือน", message, level=Qgis.Warning, duration=5)

    # ==================================================================
    # cleanup (เรียกตอน unload ปลั๊กอิน)
    # ==================================================================
    def cleanup(self):
        # ถอดตัวดักปุ่ม Shift ออกจาก canvas ไม่งั้นค้างหลัง unload ปลั๊กอิน
        if getattr(self, "_shift_filter", None) is not None:
            try:
                self.iface.mapCanvas().removeEventFilter(self._shift_filter)
            except Exception:  # noqa: BLE001
                pass
            self._shift_filter = None
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
