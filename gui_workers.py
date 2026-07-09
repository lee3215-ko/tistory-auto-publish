"""GUI 백그라운드 워커 (티스토리 배포·벨로그 로그인)."""

from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from src.article_parser import parse_article


class VelogLoginWorker(QThread):
    log_signal = Signal(str)

    def __init__(self, user_id: str, email: str, headless: bool = False):
        super().__init__()
        self.user_id = user_id
        self.email = email
        self.headless = headless

    def run(self):
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                page = context.new_page()

                self.log_signal.emit("→ https://velog.io/ 접속 중...")
                page.goto("https://velog.io/", wait_until="networkidle", timeout=15000)
                page.wait_for_timeout(1000)

                login_btn = page.locator('button:has-text("로그인")').first
                if login_btn.count() == 0:
                    login_btn = page.locator("text=로그인").first
                if login_btn.count() == 0:
                    raise RuntimeError("로그인 버튼을 찾을 수 없습니다.")
                self.log_signal.emit("→ 로그인 버튼 클릭")
                login_btn.click()
                page.wait_for_timeout(1500)

                email_input = page.locator('input[placeholder*="이메일"]').first
                if email_input.count() == 0:
                    email_input = page.locator('input[type="email"]').first
                if email_input.count() == 0:
                    raise RuntimeError("이메일 입력칸을 찾을 수 없습니다.")
                self.log_signal.emit(f"→ 이메일 입력: {self.email}")
                email_input.fill(self.email)
                page.wait_for_timeout(500)

                submit = page.locator('button:has-text("로그인")').first
                if submit.count() == 0:
                    submit = page.locator('form button[type="submit"]').first
                if submit.count() == 0:
                    raise RuntimeError("로그인 제출 버튼을 찾을 수 없습니다.")
                self.log_signal.emit("→ 인증 메일 요청 중...")
                submit.click()
                page.wait_for_timeout(3000)

                self.log_signal.emit("✓ 인증 메일이 발송되었습니다.")
                self.log_signal.emit(f"  이메일 주소({self.email})의 수신함을 확인하세요.")
                browser.close()
        except Exception as e:
            self.log_signal.emit(f"[오류] {e}")


class PosterWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int)
    done_signal = Signal()
    account_done_signal = Signal(int, str, str, str)

    def __init__(
        self,
        accounts,
        image_path,
        image_folder=None,
        headless=False,
        test_mode=False,
        openai_api_key=None,
    ):
        super().__init__()
        self.accounts = accounts
        self.image_path = image_path
        self.image_folder = image_folder
        self.headless = headless
        self.test_mode = test_mode
        self.openai_api_key = openai_api_key
        self._stop_flag = {"stop": False}

    def stop(self):
        self._stop_flag["stop"] = True

    def _append_log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_signal.emit(f"[{ts}] {msg}")

    def run(self):
        total = len(self.accounts)
        if total == 0:
            self._append_log("[오류] 계정이 없습니다.")
            self.done_signal.emit()
            return

        self._append_log("[시작] 글 배포를 시작합니다...")
        self._append_log("=" * 60)
        prev_id = None
        poster = None

        for idx, acc in enumerate(self.accounts, 1):
            if self._stop_flag["stop"]:
                self._append_log("[중단] 사용자에 의해 중단되었습니다.")
                break

            source_row = getattr(acc, "_source_row", idx - 1)
            self._append_log(f"\n[{idx}/{total}] 계정: {acc.id} | 블로그: {acc.blog_url}\n")

            try:
                if prev_id is None or acc.id != prev_id:
                    if poster is not None:
                        try:
                            poster.close()
                        except Exception:
                            pass
                    poster = None

                if poster is None:
                    from src.tistory_poster import TistoryPoster

                    poster = TistoryPoster(
                        headless=self.headless,
                        on_log=lambda msg: None if self._stop_flag["stop"] else self._append_log(msg),
                        openai_api_key=self.openai_api_key,
                    )
                    self._append_log("  → 새 로그인 세션 생성")
                else:
                    self._append_log("  → 같은 세트 계정: 기존 로그인 세션 유지")

                img = self.image_path
                if self.image_folder:
                    folder = Path(self.image_folder)
                    images = [
                        p
                        for p in folder.glob("*")
                        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp")
                    ]
                    if images:
                        img = str(random.choice(images))

                if self.test_mode:
                    poster.test_login(acc.blog_url, acc.id, acc.password)
                else:
                    article_path = getattr(acc, "article_path", "")
                    if not article_path:
                        raise RuntimeError("원고 파일이 지정되지 않았습니다.")
                    p = Path(article_path)
                    if not p.exists():
                        raise RuntimeError(f"원고 파일이 존재하지 않습니다: {p}")
                    parts = parse_article(p.read_text(encoding="utf-8"))
                    if parts.tags:
                        self._append_log(f"  → 태그 {len(parts.tags)}개 인식: {', '.join(parts.tags)}")
                    url = poster.post(
                        acc.blog_url,
                        acc.id,
                        acc.password,
                        parts.title,
                        parts.body,
                        img,
                        tags=parts.tags,
                    )
                    if not url:
                        raise RuntimeError(
                            "발행 완료 URL을 확인하지 못했습니다. "
                            "CAPTCHA/발행 확인 단계에서 멈췄을 수 있습니다."
                        )
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    self.account_done_signal.emit(source_row, url, now, "")

                prev_id = acc.id
            except Exception as e:
                err = str(e)
                self._append_log(f"[오류] {acc.id}: {err}")
                self.account_done_signal.emit(source_row, "", "", err)
                prev_id = None
                if poster is not None:
                    try:
                        poster.close()
                    except Exception:
                        pass
                    poster = None

            self.progress_signal.emit(int((idx / total) * 100))

        if poster is not None:
            try:
                poster.close()
            except Exception:
                pass

        self._append_log("\n[완료] 모든 배포 작업이 종료되었습니다.\n")
        self.done_signal.emit()
