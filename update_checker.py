# -*- coding: utf-8 -*-
"""
update_checker.py — ตรวจสอบเวอร์ชันและอัปเดตปลั๊กอินจาก GitHub

การทำงาน:
  1) อ่านเวอร์ชันปัจจุบันจาก metadata.txt (local)
  2) ดึงเวอร์ชันล่าสุดจาก raw metadata.txt บน branch หลักของ repo (remote)
  3) เทียบเวอร์ชัน:
       - remote ใหม่กว่า -> แจ้ง "มีเวอร์ชันใหม่" + เปิดให้กด "อัปเดตเลย"
       - เท่ากัน/local ใหม่กว่า -> แจ้ง "ใช้เวอร์ชันล่าสุดแล้ว"
  4) อัปเดต: ดาวน์โหลด zip ของ repo -> แตกไฟล์ทับโฟลเดอร์ปลั๊กอิน -> ให้ปิด/เปิด QGIS ใหม่

ผู้ใช้ต้องตั้งค่า GitHub repo ของตนเองก่อน (ผ่านปุ่มตั้งค่าในหน้าต่าง หรือแก้ DEFAULT_REPO)
รูปแบบ repo: "owner/repository" เช่น "phakphum/QGIS_Node_TopologyChecker"

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

import os
import re
import shutil
import ssl
import tempfile
import zipfile
from urllib.request import Request, urlopen

from qgis.core import QgsTask, QgsMessageLog, Qgis

# ---- ค่า repository ของโครงการ (ฝังตายตัว ผู้ใช้ทั่วไปไม่ต้องตั้งค่า) ----------
DEFAULT_REPO = "PARKPHUM/CHK_Node-Topo"
DEFAULT_BRANCH = "main"

_HTTP_TIMEOUT = 20  # วินาที
_USER_AGENT = "QGIS-Node-Topology-Checker"


# ===================================================================
# repo/branch — ใช้ค่าคงที่ที่ฝังไว้เสมอ (ปุ่มตั้งค่าถูกตัดออกแล้ว)
# ===================================================================
def get_repo():
    return DEFAULT_REPO


def get_branch():
    return DEFAULT_BRANCH


def is_repo_configured():
    repo = (get_repo() or "").strip()
    return bool(repo) and "CHANGE_ME" not in repo and "/" in repo


def repo_web_url():
    return "https://github.com/{}".format(get_repo())


# ===================================================================
# เวอร์ชัน
# ===================================================================
def parse_version(text):
    """แปลงสตริงเวอร์ชันเป็น tuple ของตัวเลข เช่น 'v1.2.3' -> (1, 2, 3)"""
    if not text:
        return (0,)
    text = str(text).strip().lstrip("vV")
    parts = re.split(r"[.\-_]", text)
    numbers = []
    for p in parts:
        m = re.match(r"^\d+", p.strip())
        numbers.append(int(m.group()) if m else 0)
    return tuple(numbers) if numbers else (0,)


def _extract_version_from_metadata(text):
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("version="):
            return line.split("=", 1)[1].strip()
    return None


def read_local_version(plugin_dir):
    """อ่านเวอร์ชันจาก metadata.txt ในโฟลเดอร์ปลั๊กอิน"""
    path = os.path.join(plugin_dir, "metadata.txt")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return _extract_version_from_metadata(fh.read()) or "0.0.0"
    except Exception:  # noqa: BLE001
        return "0.0.0"


def _open_url(url):
    """เปิด URL คืนข้อความ (bytes) — พยายาม verify SSL ก่อน ถ้าไม่ได้ค่อย fallback"""
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return resp.read()
    except ssl.SSLError:
        # บางเครื่อง QGIS มีปัญหาใบรับรอง SSL — fallback แบบไม่ verify
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urlopen(req, timeout=_HTTP_TIMEOUT, context=ctx) as resp:
            return resp.read()


def fetch_remote_version(repo, branch):
    """ดึงเวอร์ชันล่าสุดจาก raw metadata.txt (ลองทั้ง branch ที่ตั้งไว้และ master)"""
    branches = [branch] if branch else []
    for b in ("main", "master"):
        if b not in branches:
            branches.append(b)

    last_error = None
    for b in branches:
        url = "https://raw.githubusercontent.com/{}/{}/metadata.txt".format(repo, b)
        try:
            data = _open_url(url)
            version = _extract_version_from_metadata(data.decode("utf-8", "ignore"))
            if version:
                return version, b
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("ไม่พบ metadata.txt บน repo")


# ===================================================================
# Task: ตรวจสอบเวอร์ชัน (network ใน background)
# ===================================================================
class UpdateCheckTask(QgsTask):
    def __init__(self, plugin_dir):
        super().__init__("ตรวจสอบอัปเดตปลั๊กอิน", QgsTask.CanCancel)
        self.plugin_dir = plugin_dir
        self.repo = get_repo()
        self.branch = get_branch()
        self.local_version = read_local_version(plugin_dir)
        self.remote_version = None
        self.resolved_branch = None
        self.error_message = None
        self._on_done = None

    def set_callback(self, callback):
        self._on_done = callback

    def run(self):
        try:
            version, branch = fetch_remote_version(self.repo, self.branch)
            self.remote_version = version
            self.resolved_branch = branch
            return True
        except Exception as exc:  # noqa: BLE001
            self.error_message = str(exc)
            return False

    def has_update(self):
        if not self.remote_version:
            return False
        return parse_version(self.remote_version) > parse_version(self.local_version)

    def finished(self, result):
        if self._on_done is not None:
            self._on_done(result, self)


# ===================================================================
# Task: ดาวน์โหลดและติดตั้ง
# ===================================================================
class UpdateInstallTask(QgsTask):
    def __init__(self, plugin_dir, branch):
        super().__init__("กำลังดาวน์โหลดและติดตั้งอัปเดต", QgsTask.CanCancel)
        self.plugin_dir = plugin_dir
        self.repo = get_repo()
        self.branch = branch or get_branch()
        self.success = False
        self.error_message = None
        self._on_done = None

    def set_callback(self, callback):
        self._on_done = callback

    def run(self):
        tmp_dir = None
        try:
            self.setProgress(5)
            zip_url = "https://codeload.github.com/{}/zip/refs/heads/{}".format(
                self.repo, self.branch)
            data = _open_url(zip_url)
            if self.isCanceled():
                return False
            self.setProgress(50)

            tmp_dir = tempfile.mkdtemp(prefix="ntc_update_")
            zip_path = os.path.join(tmp_dir, "update.zip")
            with open(zip_path, "wb") as fh:
                fh.write(data)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)
            self.setProgress(75)

            # หาโฟลเดอร์ราก (repo-branch) ในไฟล์ที่แตกออกมา
            extracted_root = None
            for name in os.listdir(tmp_dir):
                full = os.path.join(tmp_dir, name)
                if os.path.isdir(full):
                    extracted_root = full
                    break
            if extracted_root is None:
                raise RuntimeError("ไฟล์อัปเดตไม่ถูกต้อง (ไม่พบโฟลเดอร์)")

            _copy_over(extracted_root, self.plugin_dir)
            self.setProgress(100)
            self.success = True
            return True

        except Exception as exc:  # noqa: BLE001
            self.error_message = str(exc)
            QgsMessageLog.logMessage(
                "UpdateInstallTask error: {}".format(exc),
                "Node & Topology Checker", Qgis.Critical)
            return False
        finally:
            if tmp_dir and os.path.isdir(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def finished(self, result):
        if self._on_done is not None:
            self._on_done(result, self)


def _copy_over(src_dir, dst_dir):
    """คัดลอกไฟล์จาก src_dir ทับ dst_dir (เขียนทับไฟล์เดิม สร้างโฟลเดอร์ที่ขาด)"""
    for root, dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        target_root = dst_dir if rel == "." else os.path.join(dst_dir, rel)
        os.makedirs(target_root, exist_ok=True)
        for fname in files:
            shutil.copy2(os.path.join(root, fname), os.path.join(target_root, fname))
