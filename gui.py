# gui.py
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui_workers import PosterWorker, VelogLoginWorker
from paths import APP_NAME, APP_VERSION, EXE_NAME, UPDATE_VERSION_URL, get_icon_path, is_admin_mode
from src.account_manager import Account, AccountManager
from src.article_file import move_article_after_publish
from ui_theme import COLORS, apply_theme
from update_ui import check_update_manual, schedule_update_check


class GroupSeparatorDelegate(QStyledItemDelegate):
    def __init__(self, table):
        super().__init__(table)
        self.table = table

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.row() > 0:
            prev_id = self.table.item(index.row() - 1, 1)
            curr_id = self.table.item(index.row(), 1)
            if prev_id and curr_id and prev_id.text() != curr_id.text():
                painter.save()
                pen = painter.pen()
                pen.setWidth(2)
                pen.setColor(QColor(80, 80, 80))
                painter.setPen(pen)
                painter.drawLine(option.rect.topLeft(), option.rect.topRight())
                painter.restore()


class TistoryPosterApp(QMainWindow):
    _test_worker = None
    _post_worker = None

    def __init__(self):
        super().__init__()
        self.is_admin_mode = is_admin_mode()
        title_suffix = "관리자" if self.is_admin_mode else "배포"
        self.setWindowTitle(f"{APP_NAME} — 티스토리/벨로그 자동 글 배포 v{APP_VERSION} ({title_suffix})")
        self.setMinimumSize(1450, 900)

        self.acc_mgr = AccountManager()
        self.settings = QSettings(APP_NAME, APP_NAME)
        self._build_ui()
        self._load_accounts()
        self._load_saved_paths()
        self._set_status("준비 완료 — 계정을 추가한 뒤 「배포 시작」을 누르세요.")
        schedule_update_check(
            self,
            version_url=UPDATE_VERSION_URL,
            current_version=APP_VERSION,
            app_name=APP_NAME,
            exe_name=EXE_NAME,
            zip_inner_folder="TistoryPoster",
            log_callback=self._append_log,
        )

    def _append_log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        text = str(msg)
        # 이미 [HH:MM:SS] 형태의 타임스탬프가 붙어 있으면 중복 추가하지 않음
        stripped = text.lstrip("\n")
        if len(stripped) >= 10 and stripped[0] == "[" and stripped[3] == ":" and stripped[6] == ":" and stripped[9] == "]":
            self.log_view.appendPlainText(text)
        else:
            self.log_view.appendPlainText(f"[{ts}] {text}")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 14, 14, 10)
        main_layout.setSpacing(10)

        main_layout.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tistory_tab = QWidget()
        self.velog_tab = QWidget()
        self.tabs.addTab(self.tistory_tab, "  티스토리  ")
        self.tabs.addTab(self.velog_tab, "  벨로그  ")
        main_layout.addWidget(self.tabs, stretch=1)

        self._build_tistory_tab()
        self._build_velog_tab()

        self.status_label = QLabel()
        self.status_label.setObjectName("StatusBar")
        main_layout.addWidget(self.status_label)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("AppHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(4, 0, 4, 0)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("티스토리 · 벨로그 자동 글 배포")
        title.setObjectName("AppTitle")
        subtitle = QLabel("계정별 원고를 자동으로 티스토리에 발행합니다")
        subtitle.setObjectName("AppSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        row.addLayout(title_col)
        row.addStretch()

        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("VersionLabel")
        row.addWidget(version, alignment=Qt.AlignVCenter)
        return header

    def _set_status(self, text: str):
        self.status_label.setText(text)

    def _build_tistory_tab(self):
        layout = QVBoxLayout(self.tistory_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # === 상단: 계정 관리 ===
        acc_group = QGroupBox("계정 관리")
        acc_v = QVBoxLayout(acc_group)

        # 검색칸
        search_h = QHBoxLayout()
        self.inp_search_id = QLineEdit()
        self.inp_search_id.setPlaceholderText("아이디 검색...")
        self.inp_search_id.textChanged.connect(self._filter_accounts)
        search_h.addWidget(QLabel("검색"))
        search_h.addWidget(self.inp_search_id, stretch=1)
        acc_v.addLayout(search_h)

        self.acc_table = QTableWidget()
        self.acc_table.setColumnCount(7)
        self.acc_table.setHorizontalHeaderLabels(["상태", "아이디", "비밀번호", "블로그 주소", "원고 파일", "완료일시", "발행 URL"])
        self.acc_table.setMinimumHeight(360)
        self.acc_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.acc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.acc_table.setColumnWidth(1, 230)
        self.acc_table.setColumnWidth(2, 110)
        self.acc_table.setColumnWidth(3, 260)
        self.acc_table.setColumnWidth(4, 320)
        self.acc_table.setColumnWidth(5, 160)
        self.acc_table.setColumnWidth(6, 320)
        self.acc_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.acc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.acc_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.acc_table.cellDoubleClicked.connect(self._open_published_url)
        self.acc_table.setItemDelegate(GroupSeparatorDelegate(self.acc_table))
        self.acc_table.installEventFilter(self)
        acc_v.addWidget(self.acc_table)

        acc_form = QHBoxLayout()
        self.inp_id = QLineEdit()
        self.inp_id.setPlaceholderText("아이디")
        self.inp_pw = QLineEdit()
        self.inp_pw.setPlaceholderText("비밀번호")
        self.inp_pw.setEchoMode(QLineEdit.Password)
        self.inp_urls = QPlainTextEdit()
        self.inp_urls.setPlaceholderText("블로그 주소를 줄마다 입력하세요.\n기본 5개 세트 가능, 4개만 입력하면 4개가 한 세트로 추가됩니다.")
        self.inp_urls.setFixedHeight(74)
        self.inp_article = QLineEdit()
        self.inp_article.setPlaceholderText("계정별 원고 파일 (선택)")
        btn_article = QPushButton("원고 선택")
        btn_article.clicked.connect(self._select_account_article)
        btn_folder_article = QPushButton("폴더 선택")
        btn_folder_article.clicked.connect(self._set_folder_articles_for_selected)
        btn_sel_article = QPushButton("선택한 계정 원고")
        btn_sel_article.clicked.connect(self._set_selected_account_articles_multi)
        btn_load_selected = QPushButton("선택행 불러오기")
        btn_load_selected.clicked.connect(self._load_selected_account_to_form)
        btn_update_selected = QPushButton("선택행 수정")
        btn_update_selected.clicked.connect(self._update_selected_accounts)
        btn_add = QPushButton("추가")
        btn_add.clicked.connect(self._add_account)
        btn_del = QPushButton("삭제")
        btn_del.clicked.connect(self._del_account)
        acc_form.addWidget(QLabel("아이디"))
        acc_form.addWidget(self.inp_id, 2)
        acc_form.addWidget(QLabel("비밀번호"))
        acc_form.addWidget(self.inp_pw, 2)
        acc_form.addWidget(QLabel("블로그 주소들"))
        acc_form.addWidget(self.inp_urls, 4)
        acc_form.addWidget(QLabel("원고"))
        acc_form.addWidget(self.inp_article, 3)
        acc_form.addWidget(btn_article)
        acc_form.addWidget(btn_folder_article)
        acc_form.addWidget(btn_sel_article)
        acc_form.addWidget(btn_load_selected)
        acc_form.addWidget(btn_update_selected)
        acc_form.addWidget(btn_add)
        acc_form.addWidget(btn_del)
        acc_v.addLayout(acc_form)

        layout.addWidget(acc_group, stretch=3)

        # === 중앙: 원고/이미지 설정 + 로그 ===
        center_splitter = QSplitter(Qt.Horizontal)
        settings_widget = QWidget()
        settings_v = QVBoxLayout(settings_widget)
        settings_v.setContentsMargins(0, 0, 0, 0)

        img_h = QHBoxLayout()
        self.inp_image = QLineEdit()
        self.inp_image.setPlaceholderText("본문에 첨부할 이미지 경로 (선택)")
        btn_img = QPushButton("이미지 선택")
        btn_img.clicked.connect(self._select_image)
        self.inp_image_folder = QLineEdit()
        self.inp_image_folder.setPlaceholderText("랜덤 이미지 폴더 (선택 — 폴더 지정 시 우선 사용)")
        btn_img_folder = QPushButton("폴더 선택")
        btn_img_folder.clicked.connect(self._select_image_folder)
        img_h.addWidget(QLabel("본문 이미지"))
        img_h.addWidget(self.inp_image, stretch=1)
        img_h.addWidget(btn_img)
        img_h.addWidget(QLabel("이미지 폴더"))
        img_h.addWidget(self.inp_image_folder, stretch=1)
        img_h.addWidget(btn_img_folder)
        settings_v.addLayout(img_h)

        # 오른쪽: 로그 & 진행률
        log_widget = QWidget()
        log_v = QVBoxLayout(log_widget)
        log_v.setContentsMargins(0, 0, 0, 0)

        log_v.addWidget(QLabel("실행 로그"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 10))
        self.log_view.setMinimumHeight(200)
        log_v.addWidget(self.log_view, stretch=1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        log_v.addWidget(QLabel("전체 진행률"))
        log_v.addWidget(self.progress)

        center_splitter.addWidget(settings_widget)
        center_splitter.addWidget(log_widget)
        center_splitter.setSizes([620, 780])
        layout.addWidget(center_splitter, stretch=2)

        # === 하단: API 키 + 실행 버튼 ===
        api_h = QHBoxLayout()
        api_h.addWidget(QLabel("OpenAI API 키"))
        self.inp_openai_key = QLineEdit()
        self.inp_openai_key.setPlaceholderText("sk-... (CAPTCHA 자동 해결용, 선택)")
        self.inp_openai_key.setEchoMode(QLineEdit.Password)
        saved_key = self.settings.value("openai_api_key", "") or self.settings.value("gemini_api_key", "")
        self.inp_openai_key.setText(saved_key)
        api_h.addWidget(self.inp_openai_key, stretch=1)
        layout.addLayout(api_h)

        guide_lbl = QLabel(
            "<b>안내:</b> OpenAI API 키는 CAPTCHA 해결에만 사용되며 이 PC에만 저장됩니다. "
            "프로그램 실행 시 GitHub에서 자동으로 업데이트를 확인합니다."
        )
        guide_lbl.setObjectName("GuideLabel")
        layout.addWidget(guide_lbl)

        ctrl_h = QHBoxLayout()
        self.chk_headless = QCheckBox("헤드리스 모드 (브라우저 숨김)")
        self.chk_headless.setChecked(self.settings.value("headless", False, type=bool))
        btn_test = QPushButton("로그인 테스트")
        btn_test.clicked.connect(self._test_login)
        btn_update = QPushButton("업데이트 확인")
        btn_update.clicked.connect(self._check_update)
        btn_stop = QPushButton("중단")
        btn_stop.setObjectName("DangerButton")
        btn_stop.clicked.connect(self._stop_posting)
        btn_start = QPushButton("배포 시작")
        btn_start.setObjectName("PrimaryButton")
        btn_start.clicked.connect(self._start_posting)
        ctrl_h.addWidget(self.chk_headless)
        ctrl_h.addStretch()
        ctrl_h.addWidget(btn_test)
        ctrl_h.addWidget(btn_update)
        ctrl_h.addWidget(btn_stop)
        ctrl_h.addWidget(btn_start)
        layout.addLayout(ctrl_h)

    def _build_velog_tab(self):
        layout = QVBoxLayout(self.velog_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 아이디 입력
        id_row = QHBoxLayout()
        id_row.addWidget(QLabel("아이디:"))
        self.velog_inp_id = QLineEdit()
        self.velog_inp_id.setPlaceholderText("벨로그 아이디를 입력하세요")
        id_row.addWidget(self.velog_inp_id)
        layout.addLayout(id_row)

        # 이메일 주소 입력
        email_row = QHBoxLayout()
        email_row.addWidget(QLabel("이메일 주소:"))
        self.velog_inp_email = QLineEdit()
        self.velog_inp_email.setPlaceholderText("인증받을 이메일 주소를 입력하세요")
        email_row.addWidget(self.velog_inp_email)
        layout.addLayout(email_row)

        # 로그인 버튼
        btn_login = QPushButton("로그인 / 인증 메일 받기")
        btn_login.setObjectName("AccentButton")
        btn_login.clicked.connect(self._velog_login)
        layout.addWidget(btn_login)

        # 상태 로그
        self.velog_log = QTextEdit()
        self.velog_log.setReadOnly(True)
        self.velog_log.setMaximumHeight(120)
        layout.addWidget(self.velog_log)

        layout.addStretch()

    def _velog_login(self):
        user_id = self.velog_inp_id.text().strip()
        email = self.velog_inp_email.text().strip()
        if not user_id:
            QMessageBox.warning(self, "입력 오류", "아이디를 입력하세요.")
            return
        if not email:
            QMessageBox.warning(self, "입력 오류", "이메일 주소를 입력하세요.")
            return
        self.velog_log.append(f"[시작] 벨로그 로그인 시도: {user_id}")
        # 백그라운드 워커로 실행
        self._velog_worker = VelogLoginWorker(user_id, email)
        self._velog_worker.log_signal.connect(lambda msg: self.velog_log.append(msg))
        self._velog_worker.finished.connect(lambda: self.velog_log.append("[완료]"))
        self._velog_worker.start()

    def _filter_accounts(self):
        search_text = self.inp_search_id.text().strip().lower()
        for row in range(self.acc_table.rowCount()):
            item = self.acc_table.item(row, 1)
            if item:
                id_text = item.text().lower()
                match = search_text in id_text if search_text else True
                self.acc_table.setRowHidden(row, not match)

    def _load_saved_paths(self):
        self.inp_image.setText(self.settings.value("image_path", ""))
        self.inp_image_folder.setText(self.settings.value("image_folder", ""))

    def _load_accounts(self):
        accounts = self.acc_mgr.load()
        self.acc_table.setRowCount(len(accounts))
        prev_id = None
        for i, acc in enumerate(accounts):
            published_url = getattr(acc, "published_url", "")
            published_at = getattr(acc, "published_at", "")
            publish_error = getattr(acc, "publish_error", "")
            if published_url:
                status_text = "✓"
            elif publish_error:
                status_text = "✗"
            else:
                status_text = ""
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.acc_table.setItem(i, 0, status_item)
            self.acc_table.setItem(i, 1, QTableWidgetItem(acc.id))
            # 보안상 비밀번호는 마스킹 표시
            self.acc_table.setItem(i, 2, QTableWidgetItem("*" * 6))
            self.acc_table.setItem(i, 3, QTableWidgetItem(acc.blog_url))
            article_path = getattr(acc, "article_path", "")
            article_item = QTableWidgetItem(Path(article_path).name if article_path else "")
            if article_path:
                article_item.setToolTip(article_path)
            self.acc_table.setItem(i, 4, article_item)
            self.acc_table.setItem(i, 5, QTableWidgetItem(published_at))
            url_item = QTableWidgetItem(published_url)
            if published_url:
                url_item.setToolTip("더블클릭하면 발행된 글을 엽니다.")
            self.acc_table.setItem(i, 6, url_item)
            if published_url:
                self._mark_account_row(i, published_url, published_at)
            elif publish_error:
                self._mark_account_row_failed(i, publish_error)
            if prev_id is not None and acc.id != prev_id:
                self._set_row_separator(i, True)
            prev_id = acc.id
        if accounts:
            self._append_log(f"[계정] {len(accounts)}개 계정 로드 완료")

    def _reset_row_style(self, row: int):
        for col in range(self.acc_table.columnCount()):
            item = self.acc_table.item(row, col)
            if item:
                item.setBackground(QColor(COLORS["surface"]))
                item.setForeground(QColor(COLORS["text"]))

    def _clear_publish_failure(self, acc: Account):
        acc.publish_error = ""

    def _reset_article_publish_state(self, acc: Account):
        """원고 변경 시 발행·실패 상태를 초기화해 재시도 가능하게 함."""
        acc.published_url = ""
        acc.published_at = ""
        self._clear_publish_failure(acc)

    def _add_account(self):
        aid = self.inp_id.text().strip()
        apw = self.inp_pw.text().strip()
        urls = [line.strip() for line in self.inp_urls.toPlainText().splitlines() if line.strip()]
        article_path = self.inp_article.text().strip()
        if not aid or not apw or not urls:
            QMessageBox.warning(self, "입력 오류", "아이디, 비밀번호, 블로그 URL을 입력하세요.\n블로그 주소는 줄마다 여러 개 입력할 수 있습니다.")
            return
        accounts = self.acc_mgr.load()
        for idx, url in enumerate(urls):
            accounts.append(Account(id=aid, password=apw, blog_url=url, article_path=article_path))
        self.acc_mgr.save(accounts)
        self._load_accounts()
        self.inp_id.clear()
        self.inp_pw.clear()
        self.inp_urls.clear()
        self.inp_article.clear()
        self._append_log(f"[계정 세트] 추가됨: {aid} / 블로그 {len(urls)}개")

    def _del_account(self):
        sel = self.acc_table.selectedItems()
        if not sel:
            QMessageBox.warning(self, "선택 오류", "삭제할 계정 행을 선택하세요.")
            return
        row = sel[0].row()
        self.acc_mgr.delete(row)
        self._load_accounts()
        self._append_log(f"[계정] {row+1}번 행 삭제됨")

    def _load_selected_account_to_form(self):
        selected_rows = sorted({item.row() for item in self.acc_table.selectedItems()})
        if not selected_rows:
            QMessageBox.warning(self, "선택 오류", "불러올 계정 행을 선택하세요.")
            return
        accounts = self.acc_mgr.load()
        row = selected_rows[0]
        if not (0 <= row < len(accounts)):
            return
        acc = accounts[row]
        self.inp_id.setText(acc.id)
        self.inp_pw.setText(acc.password)
        # 같은 아이디를 가진 모든 계정의 URL 수집
        same_id_urls = [a.blog_url for a in accounts if a.id == acc.id]
        self.inp_urls.setPlainText("\n".join(same_id_urls))
        self.inp_article.setText(getattr(acc, "article_path", ""))
        self._append_log(f"[계정] {acc.id} 정보를 입력 폼에 불러옴")

    def _update_selected_accounts(self):
        selected_rows = sorted({item.row() for item in self.acc_table.selectedItems()})
        if not selected_rows:
            QMessageBox.warning(self, "선택 오류", "수정할 계정 행을 선택하세요.")
            return
        accounts = self.acc_mgr.load()
        new_id = self.inp_id.text().strip()
        new_pw = self.inp_pw.text().strip()
        new_urls = [line.strip() for line in self.inp_urls.toPlainText().splitlines() if line.strip()]
        new_article = self.inp_article.text().strip()
        if not new_id or not new_pw:
            QMessageBox.warning(self, "입력 오류", "아이디와 비밀번호를 입력하세요.")
            return
        changed = False
        for row in selected_rows:
            if not (0 <= row < len(accounts)):
                continue
            old_acc = accounts[row]
            # 같은 아이디를 가진 모든 계정을 한 번에 수정
            for acc in accounts:
                if acc.id == old_acc.id:
                    acc.id = new_id
                    acc.password = new_pw
                    if new_article:
                        acc.article_path = new_article
                        self._reset_article_publish_state(acc)
                    changed = True
            # 블로그 URL 변경: 기존 계정 삭제 후 새 URL로 재생성
            if new_urls:
                # 기존 계정 제거
                accounts = [a for a in accounts if a.id != old_acc.id or a.blog_url in new_urls]
                # 새 URL 추가
                for url in new_urls:
                    if not any(a.id == new_id and a.blog_url == url for a in accounts):
                        accounts.append(Account(id=new_id, password=new_pw, blog_url=url, article_path=new_article))
                changed = True
        if changed:
            self.acc_mgr.save(accounts)
            self._load_accounts()
            self._append_log(f"[계정] {len(selected_rows)}개 행 수정 완료")

    def _set_folder_articles_for_selected(self):
        """선택한 계정들에만 폴 더 내 원고 파일을 개수에 맞게 배분."""
        selected_rows = sorted({item.row() for item in self.acc_table.selectedItems()})
        if not selected_rows:
            QMessageBox.warning(self, "선택 오류", "원고를 지정할 계정 행을 선택하세요.")
            return
        folder = QFileDialog.getExistingDirectory(self, "원고 파일이 있는 폴 더 선택")
        if not folder:
            return
        folder_path = Path(folder)
        txt_files = sorted([p for p in folder_path.glob("*.txt")])
        if not txt_files:
            QMessageBox.warning(self, "파일 없음", "선택한 폴 더에 .txt 원고 파일이 없습니다.")
            return
        if len(txt_files) < len(selected_rows):
            QMessageBox.warning(self, "파일 부족", f"선택한 계정 {len(selected_rows)}개에 필요한 원고 파일이 {len(txt_files)}개로 부족합니다.")
            return
        accounts = self.acc_mgr.load()
        for idx, row in enumerate(selected_rows):
            if 0 <= row < len(accounts):
                accounts[row].article_path = str(txt_files[idx])
                self._reset_article_publish_state(accounts[row])
        self.acc_mgr.save(accounts)
        self._load_accounts()
        self._append_log(f"[계정] 선택한 {len(selected_rows)}개 계정에 원고 자동 배정 완료 및 발행 상태 초기화 ({folder_path})")

    def _set_selected_account_articles_multi(self):
        """선택한 계정 개수만큼 원고 파일을 직접 선택."""
        selected_rows = sorted({item.row() for item in self.acc_table.selectedItems()})
        if not selected_rows:
            QMessageBox.warning(self, "선택 오류", "원고를 지정할 계정 행을 선택하세요.")
            return
        count = len(selected_rows)
        paths, _ = QFileDialog.getOpenFileNames(self, f"원고 파일 선택 ({count}개)", "", "텍스트 파일 (*.txt)")
        if not paths:
            return
        if len(paths) != count:
            QMessageBox.warning(self, "개수 불일치", f"선택한 계정은 {count}개인데 원고 파일은 {len(paths)}개를 선택했습니다.\n정확히 {count}개를 선택해주세요.")
            return
        accounts = self.acc_mgr.load()
        for idx, row in enumerate(selected_rows):
            if 0 <= row < len(accounts):
                accounts[row].article_path = paths[idx]
                self._reset_article_publish_state(accounts[row])
        self.acc_mgr.save(accounts)
        self._load_accounts()
        self._append_log(f"[계정] 선택한 {count}개 계정에 원고 지정 완료 및 발행 상태 초기화")

    def _select_account_article(self):
        path, _ = QFileDialog.getOpenFileName(self, "원고 파일 선택", "", "텍스트 파일 (*.txt)")
        if path:
            self.inp_article.setText(path)

    def _select_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "이미지 선택", "", "이미지 파일 (*.png *.jpg *.jpeg *.gif *.webp)")
        if path:
            self.inp_image.setText(path)
            self.settings.setValue("image_path", path)

    def _select_image_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "랜덤 이미지 폴더 선택")
        if folder:
            self.inp_image_folder.setText(folder)
            self.settings.setValue("image_folder", folder)

    def _start_posting(self):
        self._stop_posting()
        self.settings.setValue("openai_api_key", self.inp_openai_key.text().strip())
        self.settings.sync()
        accounts = self.acc_mgr.load()
        if not accounts:
            QMessageBox.warning(self, "계정 없음", "계정을 먼저 추가하세요.")
            return
        pending_entries = []
        completed_entries = []
        skipped_failed_entries = []
        for i, acc in enumerate(accounts):
            if getattr(acc, "published_url", ""):
                completed_entries.append((i, acc))
            elif getattr(acc, "publish_error", ""):
                skipped_failed_entries.append((i, acc))
            else:
                pending_entries.append((i, acc))
        if not pending_entries:
            if skipped_failed_entries:
                QMessageBox.information(
                    self,
                    "건너뜀",
                    f"실패한 계정 {len(skipped_failed_entries)}개가 남아 있습니다.\n"
                    "원고를 변경한 뒤 다시 시도하세요.",
                )
            else:
                QMessageBox.information(self, "완료", "모든 계정이 이미 발행 완료 상태입니다.")
            return
        if skipped_failed_entries:
            self._skipped_failed_count = len(skipped_failed_entries)
        else:
            self._skipped_failed_count = 0
        pending_accounts = []
        for original_row, acc in pending_entries:
            setattr(acc, "_source_row", original_row)
            pending_accounts.append(acc)
        for acc in pending_accounts:
            article_path = getattr(acc, "article_path", "")
            if not article_path:
                QMessageBox.warning(self, "원고 없음", f"{acc.id} 계정의 원고 파일이 지정되지 않았습니다.\n원고 열을 더블클릭하여 원고 파일을 선택해주세요.")
                return
            p = Path(article_path)
            if not p.exists():
                QMessageBox.warning(self, "원고 파일 없음", f"{acc.id} 계정의 원고 파일이 존재하지 않습니다.\n{p}")
                return
        self.progress.setValue(0)
        self.log_view.clear()
        if getattr(self, "_skipped_failed_count", 0):
            self._append_log(
                f"[건너뜀] 실패 표시 계정 {self._skipped_failed_count}개 — 원고 변경 전까지 재시도하지 않습니다."
            )
        self._append_log("[시작] 글 배포를 시작합니다...")
        self._post_worker = PosterWorker(
            accounts=pending_accounts,
            image_path=self.inp_image.text().strip(),
            image_folder=self.inp_image_folder.text().strip() or None,
            headless=self.chk_headless.isChecked(),
            openai_api_key=self.inp_openai_key.text().strip() or None,
        )
        self._post_worker.log_signal.connect(self._append_log)
        self._post_worker.progress_signal.connect(self.progress.setValue)
        self._post_worker.done_signal.connect(self._on_post_done)
        self._post_worker.account_done_signal.connect(self._on_account_done)
        self._post_worker.start()

    def _test_login(self):
        self._stop_posting()
        self.settings.setValue("openai_api_key", self.inp_openai_key.text().strip())
        self.settings.sync()
        accounts = self.acc_mgr.load()
        if not accounts:
            QMessageBox.warning(self, "계정 없음", "계정을 먼저 추가하세요.")
            return
        self.log_view.clear()
        self._append_log("[테스트] 첫 번째 계정 로그인 테스트 시작...")
        self._test_worker = PosterWorker(
            accounts=[accounts[0]],
            image_path="",
            headless=self.chk_headless.isChecked(),
            test_mode=True,
            openai_api_key=self.inp_openai_key.text().strip() or None,
        )
        self._test_worker.log_signal.connect(self._append_log)
        self._test_worker.done_signal.connect(self._on_post_done)
        self._test_worker.start()

    def _stop_posting(self):
        if self._post_worker and self._post_worker.isRunning():
            self._post_worker.stop()
            self._post_worker.wait(3000)
            self._append_log("[중단] 배포 작업이 중단되었습니다.")
        if self._test_worker and self._test_worker.isRunning():
            self._test_worker.stop()
            self._test_worker.wait(3000)
            self._append_log("[중단] 테스트 작업이 중단되었습니다.")

    def _on_post_done(self):
        self._append_log("[완료] 작업 종료")

    def _on_account_done(self, row, url, published_at, error):
        accounts = self.acc_mgr.load()
        if 0 <= row < len(accounts):
            acc = accounts[row]
            article_path = getattr(acc, "article_path", "")
            if article_path:
                try:
                    moved = move_article_after_publish(
                        article_path,
                        success=not error and bool(url),
                    )
                    if moved and moved != article_path:
                        acc.article_path = moved
                        label = "발행완료" if not error and url else "발행실패"
                        self._append_log(f"[원고 이동] #{row+1} → {label} 폴더: {Path(moved).name}")
                except OSError as exc:
                    self._append_log(f"[원고 이동 실패] #{row+1}: {exc}")

            if not error and url:
                acc.published_url = url
                acc.published_at = published_at or datetime.now().strftime("%Y-%m-%d %H:%M")
                self._clear_publish_failure(acc)
                self.acc_mgr.save(accounts)
                self._load_accounts()
                self._append_log(f"[계정 완료] #{row+1} → 발행 URL: {acc.published_url}")
            elif error:
                acc.publish_error = error
                self.acc_mgr.save(accounts)
                self._load_accounts()
                self._mark_account_row_failed(row, error)
                self._append_log(f"[계정 실패] #{row+1} → {error}")

    def _check_update(self):
        check_update_manual(
            self,
            version_url=UPDATE_VERSION_URL,
            current_version=APP_VERSION,
            app_name=APP_NAME,
            exe_name=EXE_NAME,
            zip_inner_folder="TistoryPoster",
            log_callback=self._append_log,
        )

    def _open_published_url(self, row, col):
        # col 6 = 발행 URL 열: 더블클릭 시 브라우저 열기
        if col == 6:
            item = self.acc_table.item(row, col)
            if not item:
                return
            url = item.text().strip()
            if url:
                webbrowser.open(url)
            return
        # col 4 = 원고 파일 열: 더블클릭 시 파일 선택
        if col == 4:
            path, _ = QFileDialog.getOpenFileName(self, "원고 파일 선택", "", "텍스트 파일 (*.txt)")
            if path:
                # 계정 데이터에도 즉시 반영
                accounts = self.acc_mgr.load()
                if 0 <= row < len(accounts):
                    accounts[row].article_path = path
                    self._reset_article_publish_state(accounts[row])
                    self.acc_mgr.save(accounts)
                    self._load_accounts()
                    self._append_log(f"[계정] #{row+1} 원고 변경 및 발행 상태 초기화: {path}")
            return

    def _set_row_separator(self, row, enabled):
        for col in range(self.acc_table.columnCount()):
            item = self.acc_table.item(row, col)
            if item:
                if enabled:
                    item.setData(Qt.UserRole, "separator")
                else:
                    item.setData(Qt.UserRole, None)

    def _reset_publish_status(self, row):
        accounts = self.acc_mgr.load()
        if 0 <= row < len(accounts):
            self._reset_article_publish_state(accounts[row])
            self.acc_mgr.save(accounts)
        self._reset_row_style(row)
        status_item = self.acc_table.item(row, 0)
        if status_item:
            status_item.setText("")
        date_item = self.acc_table.item(row, 5)
        if date_item:
            date_item.setText("")
        url_item = self.acc_table.item(row, 6)
        if url_item:
            url_item.setText("")
            url_item.setToolTip("")

    def _reset_all_publish_status(self, reason: str):
        accounts = self.acc_mgr.load()
        changed = False
        for acc in accounts:
            if getattr(acc, "published_url", "") or getattr(acc, "publish_error", ""):
                acc.published_url = ""
                acc.published_at = ""
                acc.publish_error = ""
                changed = True
        if changed:
            self.acc_mgr.save(accounts)
            self._load_accounts()
            self._append_log(f"[계정] 발행 상태 초기화: {reason}")

    def _copy_selected_urls(self):
        selected_indexes = self.acc_table.selectionModel().selectedRows(6)
        if not selected_indexes:
            return False
        urls = []
        for idx in selected_indexes:
            item = self.acc_table.item(idx.row(), 6)
            text = (item.text() if item else "").strip()
            if text:
                urls.append(text)
        if not urls:
            return False
        QApplication.clipboard().setText("\n".join(urls))
        self._append_log(f"[발행 URL] {len(urls)}개 복사 완료")
        return True

    def eventFilter(self, watched, event):
        if watched is self.acc_table and event.type() == QEvent.KeyPress:
            if event.matches(QKeySequence.Copy):
                if self._copy_selected_urls():
                    return True
        return super().eventFilter(watched, event)

    def _mark_account_row_failed(self, row: int, error: str = ""):
        red = QColor(COLORS["row_failed"])
        for col in range(self.acc_table.columnCount()):
            item = self.acc_table.item(row, col)
            if item:
                item.setBackground(red)
        status_item = self.acc_table.item(row, 0) or QTableWidgetItem()
        status_item.setText("✗")
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setBackground(red)
        status_item.setForeground(QColor(COLORS["danger"]))
        status_item.setToolTip(error)
        self.acc_table.setItem(row, 0, status_item)
        url_item = self.acc_table.item(row, 6) or QTableWidgetItem()
        if error:
            url_item.setToolTip(error)
        url_item.setBackground(red)
        self.acc_table.setItem(row, 6, url_item)

    def _mark_account_row(self, row: int, published_url: str = "", published_at: str = ""):
        blue = QColor(COLORS["row_done"])
        for col in range(self.acc_table.columnCount()):
            item = self.acc_table.item(row, col)
            if item:
                item.setBackground(blue)
        status_item = self.acc_table.item(row, 0) or QTableWidgetItem()
        status_item.setText("✓")
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setBackground(blue)
        self.acc_table.setItem(row, 0, status_item)
        if published_at:
            date_item = self.acc_table.item(row, 5) or QTableWidgetItem()
            date_item.setText(published_at)
            date_item.setBackground(blue)
            self.acc_table.setItem(row, 5, date_item)
        if published_url:
            url_item = self.acc_table.item(row, 6) or QTableWidgetItem()
            url_item.setText(published_url)
            url_item.setBackground(blue)
            url_item.setForeground(QColor(0, 90, 200))
            url_item.setToolTip("더블클릭하면 발행된 글을 엽니다.")
            self.acc_table.setItem(row, 6, url_item)

    def closeEvent(self, event):
        self.settings.setValue("openai_api_key", self.inp_openai_key.text().strip())
        self.settings.sync()
        self._stop_posting()
        event.accept()


def main():
    app = QApplication(sys.argv)
    apply_theme(app)
    icon_path = get_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))
    win = TistoryPosterApp()
    if icon_path:
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
