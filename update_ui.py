"""PySide6 업데이트 확인·다운로드 다이얼로그."""

from __future__ import annotations

import os
import tempfile
import threading
import urllib.error
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QProgressBar, QVBoxLayout, QWidget

from paths import APP_NAME, EXE_NAME
from updater import (
    UpdateInfo,
    can_auto_update,
    check_for_update,
    download_file_with_fallbacks,
    fetch_version_payload,
    format_network_error,
    get_update_log_path,
    schedule_apply_update,
    validate_zip_file,
)


class _UpdateSignals(QObject):
    """워커 스레드 → 메인 스레드 UI 갱신용."""

    show_dialog = Signal(object)
    progress = Signal(int, int)
    download_done = Signal(str, str)
    download_failed = Signal(str)
    check_failed = Signal(str)
    up_to_date = Signal()


def schedule_update_check(
    parent: QWidget,
    *,
    version_url: str,
    current_version: str,
    app_name: str = APP_NAME,
    exe_name: str = EXE_NAME,
    delay_ms: int = 2000,
    zip_inner_folder: str | None = None,
    log_callback=None,
    silent: bool = True,
) -> None:
    if not version_url.strip():
        return

    bridge = _UpdateSignals(parent)

    def log(msg: str) -> None:
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass

    @Slot()
    def on_up_to_date() -> None:
        if not silent:
            QMessageBox.information(parent, "업데이트", "현재 최신 버전입니다.")

    @Slot(str)
    def on_check_failed(msg: str) -> None:
        if not silent:
            QMessageBox.warning(parent, "업데이트", msg)
        log(f"[업데이트] 확인 오류: {msg}")

    @Slot(object)
    def on_show_dialog(info: object) -> None:
        _show_dialog(
            parent,
            info,
            current_version,
            app_name,
            exe_name,
            zip_inner_folder,
            log,
        )

    bridge.show_dialog.connect(on_show_dialog)
    bridge.up_to_date.connect(on_up_to_date)
    bridge.check_failed.connect(on_check_failed)

    def worker() -> None:
        try:
            info = check_for_update(version_url, current_version, app_name=app_name)
        except Exception as exc:
            bridge.check_failed.emit(str(exc))
            return
        if info is not None:
            bridge.show_dialog.emit(info)
        elif not silent:
            bridge.up_to_date.emit()
        else:
            payload = fetch_version_payload(version_url, f"{app_name}/{current_version}")
            if payload is None:
                log("[업데이트] version.json 조회 실패 (네트워크 또는 GitHub 접근 확인)")

    QTimer.singleShot(delay_ms, lambda: threading.Thread(target=worker, daemon=True).start())


def check_update_manual(parent: QWidget, **kwargs) -> None:
    schedule_update_check(parent, silent=False, delay_ms=0, **kwargs)


def _show_dialog(
    parent: QWidget,
    info: UpdateInfo,
    current_version: str,
    app_name: str,
    exe_name: str,
    zip_inner_folder: str | None,
    log,
) -> None:
    message = f"새 버전 {info.version}이 있습니다.\n(현재: {current_version})"
    if info.notes:
        message += f"\n\n{info.notes}"

    if can_auto_update() and info.url:
        message += "\n\n「예」= 자동 업데이트 후 재실행\n「아니오」= 브라우저에서 받기"
        reply = QMessageBox.question(
            parent,
            "업데이트",
            message,
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Yes:
            _auto_update(parent, info, app_name, exe_name, zip_inner_folder, log)
        elif reply == QMessageBox.No:
            webbrowser.open(info.url)
        return

    message += "\n\nzip을 받아 설치 폴더에 덮어쓴 뒤 다시 실행하세요.\n다운로드 페이지를 열까요?"
    if QMessageBox.question(parent, "업데이트", message) == QMessageBox.Yes and info.url:
        webbrowser.open(info.url)


def _auto_update(parent: QWidget, info: UpdateInfo, app_name: str, exe_name: str, zip_inner_folder, log):
    dialog = QDialog(parent)
    dialog.setWindowTitle("업데이트 중")
    dialog.setFixedSize(400, 130)
    dialog.setWindowModality(Qt.ApplicationModal)

    layout = QVBoxLayout(dialog)
    status = QLabel("다운로드 중...")
    layout.addWidget(status)
    bar = QProgressBar()
    bar.setRange(0, 100)
    layout.addWidget(bar)

    bridge = _UpdateSignals(dialog)

    @Slot(int, int)
    def on_progress(done: int, total: int) -> None:
        if total > 0:
            pct = min(int(done * 100 / total), 100)
            bar.setValue(pct)
            status.setText(f"다운로드 {pct}%")
        else:
            status.setText("다운로드 중...")

    @Slot(str, str)
    def on_download_done(zip_path_str: str, used_url: str) -> None:
        zip_path = Path(zip_path_str)
        log_path = get_update_log_path()
        try:
            status.setText("설치 준비 중... 잠시 후 다시 실행됩니다.")
            dialog.repaint()
            schedule_apply_update(
                zip_path,
                exe_name=exe_name,
                zip_inner_folder=zip_inner_folder,
                app_slug=app_name,
            )
            log(
                f"[업데이트] 다운로드 완료 ({zip_path.stat().st_size // 1024 // 1024} MB) via {used_url}"
            )
            log(f"[업데이트] 설치 스크립트 실행 (로그: {log_path})")
        except (RuntimeError, OSError) as exc:
            QMessageBox.critical(parent, "업데이트 실패", str(exc))
            dialog.reject()
            log(f"[업데이트] 설치 준비 실패: {exc}")
            return

        dialog.accept()
        QTimer.singleShot(300, lambda: os._exit(0))

    @Slot(str)
    def on_download_failed(detail: str) -> None:
        dialog.reject()
        QMessageBox.critical(
            parent,
            "업데이트 실패",
            f"다운로드 실패:\n{detail}\n\n브라우저에서 직접 받아 주세요.",
        )
        log(f"[업데이트] 다운로드 실패: {detail}")

    bridge.progress.connect(on_progress)
    bridge.download_done.connect(on_download_done)
    bridge.download_failed.connect(on_download_failed)

    def worker() -> None:
        zip_path = Path(tempfile.gettempdir()) / f"{app_name}-{info.version}.zip"
        try:
            log(f"[업데이트] 다운로드 시작: {info.version}")
            urls = list(info.download_urls) if info.download_urls else [info.url]

            def on_progress_cb(done: int, total: int) -> None:
                bridge.progress.emit(done, total)

            used_url = download_file_with_fallbacks(
                urls,
                zip_path,
                user_agent=f"{app_name}/{info.version}",
                on_progress=on_progress_cb,
            )
            validate_zip_file(zip_path, min_bytes=1024 * 1024)
            bridge.download_done.emit(str(zip_path), used_url)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            bridge.download_failed.emit(format_network_error(exc))

    threading.Thread(target=worker, daemon=True).start()
    dialog.exec()
