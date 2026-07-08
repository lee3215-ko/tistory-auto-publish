"""티스토리 글 자동 배포기

가장 중요한 버그 수정:
- goto 실패 후 except: pass 로 page 가 about:blank 가 되면
  "이미 로그인 상태"라는 거짓말이 뜨는 현상 방지.
- goto 실패 시 즉시 재시도, 3회 실패 시 확실한 예외 발생.
"""

import os
import sys
import time
from playwright.sync_api import sync_playwright
from src.captcha_solver import CaptchaSolver


class TistoryPoster:
    def __init__(self, headless=True, on_log=None, openai_api_key=None):
        self.headless = headless
        self.on_log = on_log or (lambda msg: None)
        self.openai_api_key = openai_api_key
        self.captcha_solver = CaptchaSolver(openai_api_key=openai_api_key, on_log=self._log)
        self._pw = None
        self._browser = None
        self._pw = sync_playwright().start()
        try:
            self._browser = self._launch_browser(headless=headless)
        except Exception:
            if self._pw:
                self._pw.stop()
                self._pw = None
            raise
        self.page = self._browser.new_context(viewport={"width": 1600, "height": 900}).new_page()

    def _log(self, msg):
        self.on_log(msg)

    def _launch_browser(self, headless=True):
        launch_options = {"headless": headless}

        if getattr(sys, "frozen", False):
            for channel_name, display_name in (("chrome", "Chrome"), ("msedge", "Edge")):
                try:
                    self._log(f"  → {display_name} 브라우저로 실행")
                    return self._pw.chromium.launch(channel=channel_name, **launch_options)
                except Exception as e:
                    self._log(f"  → {display_name} 실행 실패: {type(e).__name__}")

        try:
            self._log("  → Playwright Chromium으로 실행")
            return self._pw.chromium.launch(**launch_options)
        except Exception as e:
            raise RuntimeError(
                "브라우저 실행 실패: Chrome 또는 Edge를 설치한 뒤 다시 실행해주세요. "
                "개발 환경에서는 playwright install 명령이 필요할 수 있습니다."
            ) from e

    def _navigate(self, url: str):
        """goto 실패 시 about:blank 로 남지 않도록 재시도 후 확실한 예외"""
        page = self.page
        last_err = None
        for attempt in range(1, 4):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                break
            except Exception as e:
                last_err = e
                self._log(f"  → 이동 재시도 {attempt}/3 ({type(e).__name__})")
                time.sleep(1)
        else:
            # 3회 모두 실패
            raise RuntimeError(f"페이지 이동 실패 (3회): {url} | {last_err}")

        time.sleep(2)
        current = page.url
        self._log(f"  → 현재 URL: {current}")
        if "about:blank" in current or current.strip() == "":
            raise RuntimeError(f"페이지가 about:blank — 이동 실패: {url}")

    def post(self, blog_url: str, user_id: str, password: str,
             title: str, content: str, image_path=None, stop_signal=None, skip_login=False):
        if stop_signal is None:
            stop_signal = {}

        def stopped():
            return bool(stop_signal.get("stop"))

        if stopped():
            return

        # 로그인
        if skip_login:
            self._log("[1/7] 로그인 재사용 (같은 계정 세션)")
        else:
            self._log("[1/7] 로그인...")
            self._do_login(user_id, password)
            self._log("[1/7] 로그인 성공")
        if stopped():
            return

        # 글쓰기
        url = blog_url.rstrip("/") + "/manage/newpost"
        self._log(f"[2/7] 글쓰기 이동: {url}")
        self._navigate(url)
        if stopped():
            return

        self._log("[3/7] HTML 모드 전환...")
        self._switch_html()
        self._log("[3/7] HTML 모드 완료")
        if stopped():
            return

        self._log("[4/7] 제목 입력...")
        self._fill_title(title)
        self._log("[4/7] 제목 완료")
        if stopped():
            return

        self._log("[5/7] 내용 입력...")
        self._fill_content(content)
        self._log("[5/7] 내용 완료")
        if image_path and os.path.exists(image_path):
            self._log("[5/7] 기본모드 전환...")
            self._switch_basic_mode()
            self._log("[5/7] 기본모드 전환 완료")
            self._log("[5/7] 본문 이미지 업로드...")
            self._upload_image(image_path)
            self._log("[5/7] 본문 이미지 업로드 완료")
            self._log("[5/7] 대표 이미지 설정...")
            self._set_represent_image()
            self._log("[5/7] 대표 이미지 설정 완료")
        if stopped():
            return

        self._log("[6/7] 발행...")
        published_url = self._publish(title)
        self._log("[6/7] 발행 완료")
        return published_url

    # ──────────────────────────────
    # 로그인
    # ──────────────────────────────

    def _do_login(self, user_id: str, password: str):
        page = self.page

        # (1) 티스토리 중간 페이지
        self._log("  → 티스토리 로그인 페이지 접속")
        self._navigate("https://www.tistory.com/auth/login")
        if "accounts.kakao.com" not in page.url and "auth/login" not in page.url:
            self._log("  → 이미 로그인 상태")
            return

        # (2) 카카오 버튼 클릭 — href="#" 이라 JS가 동적 리다이렉트 → expect_navigation 으로 잡음
        self._log("  → 카카오 버튼 클릭 (navigation 대기)")
        kakao_btn = page.locator("a.link_kakao_id").first
        if kakao_btn.count() == 0:
            kakao_btn = page.locator('a:has-text("카카오")').first

        with page.expect_navigation(url="**/accounts.kakao.com/**", timeout=15_000):
            kakao_btn.click()

        self._log("  → 카카오 페이지 도착")
        time.sleep(2)
        if "accounts.kakao.com" not in page.url:
            raise RuntimeError(f"카카오 로그인 페이지 도착 실패: 현재 URL = {page.url}")

        # (4) 아이디 / 비번 입력
        self._log("  → 아이디/비번 입력")
        page.locator('input[name="loginId"]').fill(user_id, timeout=8_000)
        time.sleep(0.3)
        page.locator('input[name="password"], input#password, input[type="password"]').fill(password, timeout=8_000)
        time.sleep(0.3)

        # (5) 로그인 버튼 클릭
        self._log("  → 로그인 버튼 클릭")
        page.evaluate("""
            var b = document.querySelector('button[type="submit"]') || document.querySelector('button.btn_g');
            if (b) b.click();
        """)
        time.sleep(5)

        # (6) 티스토리 복귀 (동의 화면 포함)
        self._log("  → 티스토리 복귀 대기...")
        for _ in range(20):
            if "accounts.kakao.com" not in page.url:
                self._log("  → 티스토리 복귀 성공")
                time.sleep(1)
                return
            self._handle_login_dkaptcha_if_needed()
            self._handle_kakao_consent()
            time.sleep(0.5)
        raise RuntimeError("티스토리 복귀 실패 (동의화면 또는 리다이렉트 지연)")

    def _handle_login_dkaptcha_if_needed(self):
        page = self.page
        detected = False
        try:
            page.locator("iframe[src*='dkaptcha'], [id*='dkaptcha'], [class*='dkaptcha']").first.wait_for(state="visible", timeout=700)
            detected = True
        except Exception:
            try:
                page.locator("text=안전한 서비스 이용").first.wait_for(state="visible", timeout=700)
                detected = True
            except Exception:
                pass

        if not detected:
            return False

        self._log("=" * 50)
        self._log("[LOGIN CAPTCHA] 카카오 자동로그인 방지 감지!")

        if not self.captcha_solver.enabled():
            self._log("[LOGIN CAPTCHA] CAPTCHA 중계 서버 미설정 → 수동 입력 필요")
            page.bring_to_front()
            return False

        for attempt in range(1, 4):
            try:
                target = self._get_login_dkaptcha_target()
                if attempt > 1:
                    self._refresh_dkaptcha(target)
                    target = self._get_login_dkaptcha_target()

                result = self._solve_login_dkaptcha_with_ai(target)
                solve_type = result.get("type", "")
                if solve_type == "click":
                    self._log(f"[LOGIN CAPTCHA] 위치 클릭 풀이 시도 ({attempt}/3): x={result.get('x')} y={result.get('y')}")
                    if self._submit_login_dkaptcha_click(target, result):
                        self._log("[LOGIN CAPTCHA] 자동 처리 성공!")
                        return True
                elif solve_type == "input":
                    self._log(f"[LOGIN CAPTCHA] 입력 풀이 시도 ({attempt}/3): '{result.get('answer', '')}'")
                    if self._submit_dkaptcha_answer(target, result.get("answer", "")):
                        self._log("[LOGIN CAPTCHA] 자동 처리 성공!")
                        return True
                else:
                    self._log(f"[LOGIN CAPTCHA] 알 수 없는 풀이 유형: {solve_type}")
            except Exception as e:
                self._log(f"[LOGIN CAPTCHA] AI 처리 오류({attempt}/3): {e}")

        self._log("[LOGIN CAPTCHA] 자동 처리 실패 → 브라우저에서 수동으로 완료해주세요.")
        page.bring_to_front()
        return False

    def _handle_kakao_consent(self):
        for t in ["계속", "동의하고", "확인", "동의"]:
            try:
                b = self.page.locator(f'button:has-text("{t}")').first
                if b.is_visible(timeout=500):
                    b.click(timeout=3_000)
                    time.sleep(1)
                    return
            except Exception:
                pass

    # ──────────────────────────────
    # 글쓰기
    # ──────────────────────────────

    def _switch_html(self):
        page = self.page

        self._log("  → 에디터 로딩 대기...")
        self._wait_editor_toolbar()
        time.sleep(2)

        page.bring_to_front()
        time.sleep(0.3)

        # confirm 팝업 자동 승인 (브라우저 기본 confirm 무력화)
        page.evaluate("window.confirm = function() { return true; }")
        self._log("  → confirm 자동 승인 설정")

        # 드롭다운 버튼 클릭
        self._log("  → 드롭다운 열기")
        btn = page.locator("#editor-mode-layer-btn-open")
        btn.scroll_into_view_if_needed()
        btn_box = btn.bounding_box()
        page.mouse.click(btn_box["x"] + btn_box["width"] / 2, btn_box["y"] + btn_box["height"] / 2)
        time.sleep(1)

        # HTML 항목 클릭 — force=True 로 가시성 검사 무시하고 강제 클릭
        html_item = page.locator("#editor-mode-html")
        clicked = False
        try:
            html_item.click(force=True, timeout=3_000)
            self._log("  → HTML 항목 force 클릭")
            clicked = True
        except Exception as e:
            self._log(f"  → force 클릭 실패({e}), JS 폴백")

        if not clicked:
            # JS 이벤트 폴백: 드롭다운 열기 → HTML 클릭
            page.evaluate("""
                (function(){
                    var btn = document.getElementById('editor-mode-layer-btn-open');
                    if (btn) btn.click();
                    setTimeout(function(){
                        var item = document.getElementById('editor-mode-html');
                        if (item) {
                            ['mousedown','mouseup','click'].forEach(function(t){
                                item.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true}));
                            });
                        }
                    }, 400);
                })()
            """)
            self._log("  → JS 이벤트 발생")
            time.sleep(1.5)

        time.sleep(1)

        # 커스텀 확인 팝업 처리 (Enter 키 사용)
        try:
            confirm_btn = page.locator("button:has-text('확인')")
            confirm_btn.wait_for(state="visible", timeout=3_000)
            page.keyboard.press("Enter")
            self._log("  → 확인 팝업 Enter 처리")
            time.sleep(1.5)
        except Exception:
            self._log("  → 확인 팝업 없음")

        # HTML 모드 확인: .mce-txt 텍스트 OR CodeMirror visible
        time.sleep(2)
        mode_confirmed = False

        # 방법 1: 버튼 텍스트
        try:
            mode_text = page.locator("#editor-mode-layer-btn-open .mce-txt").text_content(timeout=3_000)
            self._log(f"  → 현재 모드 텍스트: {mode_text}")
            if "HTML" in (mode_text or ""):
                mode_confirmed = True
        except Exception:
            pass

        # 방법 2: CodeMirror 에디터가 보이면 HTML 모드
        if not mode_confirmed:
            try:
                page.locator(".CodeMirror").first.wait_for(state="visible", timeout=4_000)
                self._log("  → CodeMirror 확인 → HTML 모드 성공")
                mode_confirmed = True
            except Exception:
                pass

        if not mode_confirmed:
            raise RuntimeError("HTML 모드 전환 실패 (CodeMirror 미검출)")

    def _switch_basic_mode(self):
        page = self.page

        self._log("  → 기본모드 전환")
        self._wait_editor_toolbar()
        time.sleep(1)
        page.bring_to_front()
        time.sleep(0.3)
        page.evaluate("window.confirm = function() { return true; }")

        self._log("  → 드롭다운 열기")
        mode_button_box = page.evaluate(
            """
            () => {
                const visible = el => {
                    const style = getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' &&
                           rect.width > 0 && rect.height > 0;
                };

                const buttons = Array.from(document.querySelectorAll(
                    '#editor-mode-layer-btn-open, .mce-tistory-mode button, button'
                ));
                const button = buttons.find(btn => {
                    const text = (btn.innerText || btn.textContent || '').trim();
                    return visible(btn) && text.includes('HTML') && btn.querySelector('.mce-caret');
                }) || buttons.find(btn => {
                    const text = (btn.innerText || btn.textContent || '').trim();
                    return visible(btn) && text.includes('HTML');
                }) || buttons.find(btn => {
                    const text = (btn.innerText || btn.textContent || '').trim();
                    return visible(btn) && text.includes('기본모드') && btn.querySelector('.mce-caret');
                });

                if (!button) return null;
                const rect = button.getBoundingClientRect();
                return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, text: (button.innerText || button.textContent || '').trim() };
            }
            """
        )
        if not mode_button_box:
            raise RuntimeError("현재 모드 드롭다운 버튼을 찾지 못했습니다.")

        self._log(f"  → 현재 모드 버튼: {mode_button_box.get('text')}")
        page.mouse.click(
            mode_button_box["x"] + mode_button_box["width"] / 2,
            mode_button_box["y"] + mode_button_box["height"] / 2,
        )
        time.sleep(1)

        basic_box = None
        for _ in range(20):
            basic_box = page.evaluate(
                """
                () => {
                    const visible = el => {
                        const style = getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' &&
                               rect.width > 0 && rect.height > 0;
                    };
                    const candidates = Array.from(document.querySelectorAll(
                        '#editor-mode-kakao-tistory, #editor-mode-kakao, #editor-mode-kakao-text, .mce-menu-item, .mce-tistory-mode-item'
                    ))
                        .map(el => {
                            if (el.id === 'editor-mode-kakao-text') return el.closest('#editor-mode-kakao');
                            if (el.classList.contains('mce-text')) return el.closest('.mce-menu-item, .mce-tistory-mode-item');
                            return el;
                        })
                        .filter(Boolean);
                    const item = candidates.find(el => {
                        const text = (el.innerText || el.textContent || '').trim();
                        return visible(el) && text.includes('기본모드');
                    });
                    if (!item) return null;
                    const rect = item.getBoundingClientRect();
                    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                }
                """
            )
            if basic_box:
                break
            time.sleep(0.25)

        if not basic_box:
            raise RuntimeError("기본모드 메뉴 항목을 찾지 못했습니다.")

        self._log(f"  → 기본모드 메뉴 위치: x={basic_box['x']:.0f} y={basic_box['y']:.0f}")
        page.mouse.click(
            basic_box["x"] + basic_box["width"] / 2,
            basic_box["y"] + basic_box["height"] / 2,
        )
        self._log("  → 기본모드 항목 클릭")

        time.sleep(1)
        try:
            confirm_btn = page.locator("button:has-text('확인')").first
            if confirm_btn.is_visible(timeout=3_000):
                confirm_btn.click(timeout=3_000)
                self._log("  → 모드 변경 확인 클릭")
                time.sleep(2)
        except Exception:
            try:
                page.keyboard.press("Enter")
                self._log("  → 모드 변경 확인 Enter")
                time.sleep(2)
            except Exception:
                pass

        time.sleep(3)
        mode_text = ""
        try:
            mode_text = page.locator("#editor-mode-layer-btn-open .mce-txt").text_content(timeout=3_000) or ""
        except Exception:
            pass
        self._log(f"  → 현재 모드 텍스트: {mode_text}")
        if "기본" not in mode_text:
            raise RuntimeError(f"기본모드 전환 실패. 현재 모드: {mode_text}")

    def _set_represent_image(self):
        page = self.page

        self._log("  → 대표 이미지 버튼 탐색")
        for _ in range(30):
            try:
                box = page.evaluate(
                    """
                    () => {
                        const visible = el => {
                            const style = getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== 'none' && style.visibility !== 'hidden' &&
                                   rect.width > 0 && rect.height > 0;
                        };

                        const images = Array.from(document.querySelectorAll('.mce-content-body img, img'))
                            .filter(visible);
                        const image = images[0];
                        if (image) {
                            image.scrollIntoView({ block: 'center', inline: 'center' });
                            const rect = image.getBoundingClientRect();
                            image.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 }));
                            image.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 }));
                        }

                        const buttons = Array.from(document.querySelectorAll('.mce-represent-image-btn'));
                        const button = buttons.find(visible) || buttons[0];
                        if (!button) return null;
                        const btnRect = button.getBoundingClientRect();
                        if (btnRect.width <= 0 || btnRect.height <= 0) return null;
                        return { x: btnRect.x, y: btnRect.y, width: btnRect.width, height: btnRect.height };
                    }
                    """
                )
                if box:
                    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    self._log("  → 대표 이미지 버튼 클릭")
                    time.sleep(1)
                    return
            except Exception:
                pass

            try:
                button = page.locator(".mce-represent-image-btn").first
                if button.is_visible(timeout=500):
                    box = button.bounding_box()
                    if box:
                        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        self._log("  → 대표 이미지 버튼 클릭")
                        time.sleep(1)
                        return
            except Exception:
                pass

            try:
                image = page.locator(".mce-content-body img, iframe[id*='editor'] >> img").first
                if image.is_visible(timeout=500):
                    image.click(timeout=2_000)
                    time.sleep(0.8)
            except Exception:
                pass
            time.sleep(0.5)

        raise RuntimeError("대표 이미지 버튼(.mce-represent-image-btn)을 찾지 못했습니다.")

    def _wait_editor_toolbar(self):
        page = self.page
        for attempt in range(1, 4):
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
            except Exception:
                pass

            for _ in range(60):
                try:
                    has_toolbar = page.locator("#editor-mode-layer-btn-open").count() > 0
                    has_title = page.locator("#post-title-inp").count() > 0
                    has_editor = page.locator(".CodeMirror").count() > 0
                    if has_toolbar:
                        self._log(f"  → 에디터 툴바 감지 (시도 {attempt}/3)")
                        return
                    if has_title and has_editor:
                        self._log("  → 에디터는 감지됨, 모드 버튼 추가 대기...")
                except Exception:
                    pass
                time.sleep(0.5)

            if attempt < 3:
                self._log(f"  → 에디터 툴바 미로딩, 페이지 새로고침 재시도 {attempt}/3")
                try:
                    page.reload(wait_until="domcontentloaded", timeout=20_000)
                except Exception:
                    pass
                time.sleep(5)

        raise RuntimeError(
            f"에디터 툴바 로딩 실패: #editor-mode-layer-btn-open 없음 | 현재 URL={page.url}"
        )

    def _fill_title(self, title):
        self.page.locator("#post-title-inp").fill(title, timeout=10_000)
        time.sleep(0.3)

    def _fill_content(self, content):
        self.page.locator(".CodeMirror, textarea#post-content, textarea[name='content']").first.wait_for(
            state="attached", timeout=10_000
        )
        res = self.page.evaluate(
            """
            (content) => {
                const mirrors = Array.from(document.querySelectorAll('.CodeMirror'));
                const htmlMirror = mirrors.find(el => el.CodeMirror && el.className.includes('tistory-html'));
                const visibleMirror = mirrors.find(el => el.CodeMirror && el.offsetParent !== null);
                const mirror = htmlMirror || visibleMirror || mirrors.find(el => el.CodeMirror);
                if (mirror && mirror.CodeMirror) {
                    const cm = mirror.CodeMirror;
                    cm.focus();
                    cm.operation(() => {
                        cm.setValue('');
                        cm.replaceRange(content, { line: 0, ch: 0 });
                    });
                    cm.refresh();
                    cm.save();
                    cm.setCursor(cm.lineCount(), 0);
                    cm.getInputField().dispatchEvent(new Event('input', { bubbles: true }));
                    cm.getInputField().dispatchEvent(new Event('change', { bubbles: true }));
                    const textarea = cm.getTextArea();
                    if (textarea) {
                        textarea.value = content;
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                        textarea.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    if (window.tinymce && tinymce.activeEditor) {
                        try {
                            tinymce.activeEditor.setContent(content);
                            tinymce.activeEditor.save();
                            tinymce.activeEditor.fire('change');
                        } catch (e) {}
                    }
                    return { method: 'codemirror', length: cm.getValue().length };
                }

                if (window.tinymce && tinymce.activeEditor) {
                    tinymce.activeEditor.setContent(content);
                    tinymce.activeEditor.save();
                    tinymce.activeEditor.fire('change');
                    return { method: 'tinymce', length: tinymce.activeEditor.getContent().length };
                }

                const textarea = document.querySelector('textarea#post-content, textarea[name="content"], textarea');
                if (textarea) {
                    textarea.value = content;
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    textarea.dispatchEvent(new Event('change', { bubbles: true }));
                    return { method: 'textarea', length: textarea.value.length };
                }

                return { method: 'not-found', length: 0 };
            }
            """,
            content,
        )
        self._log(f"  → 내용 삽입: {res.get('method')} / {res.get('length')}자")
        if res.get("length", 0) <= 0:
            raise RuntimeError("원고 내용 입력 실패 — 에디터에 내용이 들어가지 않았습니다.")
        time.sleep(1)

    def _upload_image(self, path):
        page = self.page
        if not os.path.exists(path):
            raise RuntimeError(f"이미지 파일이 없습니다: {path}")

        self._log("  → 본문 이미지 첨부 메뉴 열기")
        opened = page.evaluate(
            """
            () => {
                const visible = el => {
                    const style = getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' &&
                           rect.width > 0 && rect.height > 0;
                };
                const buttons = Array.from(document.querySelectorAll(
                    '#mceu_0-open, #attach-layer-btn, button'
                ));
                const btn = buttons.find(el => {
                    const text = (el.innerText || el.textContent || '').trim();
                    return visible(el) &&
                           (el.id === 'mceu_0-open' ||
                            el.id === 'attach-layer-btn' ||
                            el.querySelector('.mce-i-image') ||
                            text.includes('첨부'));
                });
                if (!btn) return false;
                btn.click();
                return true;
            }
            """
        )
        if not opened:
            raise RuntimeError("본문 이미지 첨부 버튼을 찾지 못했습니다.")
        time.sleep(1)

        try:
            with page.expect_file_chooser(timeout=5_000) as chooser_info:
                clicked_photo = page.evaluate(
                    """
                    () => {
                        const visible = el => {
                            const style = getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== 'none' && style.visibility !== 'hidden' &&
                                   rect.width > 0 && rect.height > 0;
                        };
                        const items = Array.from(document.querySelectorAll(
                            '#attach-image, #attach-image-text, .mce-menu-item'
                        ));
                        const item = items.map(el => {
                            if (el.id === 'attach-image-text') return el.closest('#attach-image');
                            return el;
                        }).find(el => {
                            const text = (el.innerText || el.textContent || '').trim();
                            return visible(el) &&
                                   (el.id === 'attach-image' || text.includes('사진'));
                        });
                        if (!item) return false;
                        item.click();
                        return true;
                    }
                    """
                )
                if not clicked_photo:
                    raise RuntimeError("사진 메뉴 항목을 찾지 못했습니다.")
            chooser_info.value.set_files(path)
            self._log(f"  → 본문 이미지 선택 완료(file chooser): {path}")
            time.sleep(5)
            return
        except Exception as e:
            self._log(f"  → 사진 메뉴 file chooser 실패, input 직접 탐색: {e}")

        try:
            page.evaluate(
                """
                () => {
                    const items = Array.from(document.querySelectorAll('[id="attach-image"], input[type="file"][accept*="image"], input[type="file"]'));
                    const input = items.find(el => el.tagName === 'INPUT') || items[0];
                    if (input) input.style.display = 'block';
                }
                """
            )
            time.sleep(1)
        except Exception:
            pass

        selectors = [
            "input[id='attach-image']",
            "input[type='file'][accept*='image']",
            "input[type='file']",
        ]
        last_error = None
        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
                for index in range(count):
                    file_input = locator.nth(index)
                    try:
                        file_input.wait_for(state="attached", timeout=2_000)
                        file_input.set_input_files(path, timeout=5_000)
                        self._log(f"  → 본문 이미지 선택 완료({selector} #{index+1}): {path}")
                        time.sleep(5)
                        return
                    except Exception as e:
                        last_error = e
                        continue
                file_input.wait_for(state="attached", timeout=5_000)
                file_input.set_input_files(path, timeout=5_000)
                self._log(f"  → 본문 이미지 선택 완료({selector}): {path}")
                time.sleep(5)
                return
            except Exception as e:
                last_error = e

        raise RuntimeError(f"본문 이미지 업로드 실패 — 파일 input을 찾지 못했습니다: {last_error}")

    def _publish(self, title: str = "", thumbnail_path=None):
        page = self.page

        # 발행 버튼 클릭 (팝업 열기)
        self._log("  → 발행 버튼 클릭")
        page.locator("#publish-layer-btn, button:has-text('발행'), button:has-text('완료')").first.click(timeout=10_000)
        time.sleep(1.5)

        # 발행 팝업 대기
        self._log("  → 발행 팝업 대기...")
        page.locator(".ReactModal__Content, .inner_editor_layer, [role='dialog']").first.wait_for(state="visible", timeout=10_000)
        time.sleep(0.5)

        # 공개 라디오 선택 (#open20)
        self._log("  → 공개 설정")
        try:
            pub_radio = page.locator("#open20")
            pub_radio.check(timeout=5_000)
            self._log("  → 공개 선택 완료")
        except Exception as e:
            self._log(f"  → 공개 설정 실패: {e}")

        # 공개 발행 버튼 클릭 (#publish-btn)
        self._log("  → 공개 발행 클릭")
        page.locator("#publish-btn").click(timeout=10_000)
        time.sleep(1)

        self._wait_publish_result_or_captcha()
        url = self._get_published_url(title)
        if not url:
            raise RuntimeError("발행 완료 URL을 확인하지 못했습니다. CAPTCHA/발행 확인이 남아 있으면 브라우저에서 직접 완료해주세요.")
        return url

    def _get_published_url(self, title: str = ""):
        page = self.page
        target_title = (title or "").strip()
        for _ in range(30):
            time.sleep(0.5)
            current_url = page.url or ""
            if "/entry/" in current_url and "/manage/newpost" not in current_url:
                self._log(f"  → 발행 URL 확인: {current_url}")
                return current_url

            try:
                canonical = page.locator("link[rel='canonical']").first.get_attribute("href", timeout=500)
                if canonical and "/entry/" in canonical and "/manage/" not in canonical:
                    self._log(f"  → 발행 URL 확인: {canonical}")
                    return canonical
            except Exception:
                pass

            try:
                url = page.evaluate(
                    """
                    (targetTitle) => {
                        const normalize = text => (text || '').replace(/\\s+/g, ' ').trim();
                        const title = normalize(targetTitle);
                        const isPublicPostUrl = href => {
                            if (!href) return false;
                            if (href.startsWith('javascript:')) return false;
                            if (href.includes('/manage/')) return false;
                            if (href.includes('/admin/')) return false;
                            if (href.includes('/auth/')) return false;
                            if (href === 'https://www.tistory.com/' || href === 'https://www.tistory.com') return false;
                            if (/^https?:\\/\\/www\\.tistory\\.com\\/?$/.test(href)) return false;
                            return href.includes('/entry/');
                        };
                        const anchors = Array.from(document.querySelectorAll('a[href]'));
                        const titleMatches = anchors
                            .map(a => ({ href: a.href || '', text: normalize(a.innerText || a.textContent || '') }))
                            .filter(item => isPublicPostUrl(item.href) && item.text.length > 0)
                            .filter(item => {
                                if (!title) return false;
                                return item.text === title || item.text.includes(title) || title.includes(item.text);
                            });
                        if (titleMatches.length) return titleMatches[0].href;

                        const publicLinks = anchors
                            .map(a => ({ href: a.href || '', text: normalize(a.innerText || a.textContent || '') }))
                            .filter(item => isPublicPostUrl(item.href) && item.text.length >= 2);
                        return publicLinks.length ? publicLinks[0].href : '';
                    }
                    """,
                    target_title,
                )
                if url:
                    self._log(f"  → 공개 발행 URL 확인: {url}")
                    return url
            except Exception:
                pass

        self._log("  → 공개 발행 URL 자동 확인 실패")
        return ""

    def _wait_publish_result_or_captcha(self):
        page = self.page
        blocker_sel = "iframe[src*='dkaptcha'], #dkaptcha, [id*='dkaptcha'], [class*='dkaptcha'], .layer_body iframe, button.btn_close"
        for i in range(60):
            time.sleep(1)
            current_url = page.url or ""
            if "/entry/" in current_url and "/manage/newpost" not in current_url:
                self._log("  → 발행 완료 URL 감지")
                return
            try:
                if self._is_dkaptcha_visible(blocker_sel):
                    break
            except Exception:
                pass
            if (i + 1) % 10 == 0:
                self._log(f"  → 발행 완료/CAPTCHA 대기 중... ({i+1}초)")
        else:
            return

        self._log("=" * 50)
        self._log("[발행 확인] 추가 확인/CAPTCHA 화면이 감지되었습니다.")
        if self.captcha_solver.enabled():
            self._log("[발행 확인] OpenAI로 자동 풀이를 시도합니다.")
            for attempt in range(1, 4):
                try:
                    if attempt > 1:
                        self._refresh_dkaptcha(self._get_dkaptcha_frame())
                    captcha_frame = self._get_dkaptcha_frame()
                    answer = self._solve_dkaptcha_with_ai(captcha_frame)
                    if answer and self._submit_dkaptcha_answer(captcha_frame, answer):
                        self._log("[발행 확인] CAPTCHA 자동 처리 완료")
                        time.sleep(2)
                        return
                except Exception as e:
                    self._log(f"[발행 확인] CAPTCHA 자동 처리 오류({attempt}/3): {e}")
            self._log("[발행 확인] 자동 처리 실패 → 수동 입력으로 전환")
        else:
            self._log("[발행 확인] OpenAI API 키가 없어 수동 입력으로 전환")
        self._log("[발행 확인] 브라우저에서 직접 완료해주세요. 완료 URL이 확인될 때까지 대기합니다.")
        self._log("=" * 50)
        page.bring_to_front()

        for i in range(300):
            time.sleep(1)
            current_url = page.url or ""
            if "/entry/" in current_url and "/manage/newpost" not in current_url:
                self._log("[발행 확인] 완료 URL 감지 — 계속 진행합니다.")
                return
            if not self._is_dkaptcha_visible(blocker_sel):
                time.sleep(1)
                return
            if (i + 1) % 30 == 0:
                self._log(f"[발행 확인] 수동 완료 대기 중... ({i+1}초)")

        raise RuntimeError("발행 확인/CAPTCHA 수동 처리 시간이 초과되었습니다.")

    def _is_dkaptcha_visible(self, selector=None) -> bool:
        page = self.page
        selectors = [
            selector or "",
            "iframe[src*='dkaptcha']",
            "#dkaptcha iframe",
            "#dkaptcha",
            ".layer_body iframe",
        ]
        for sel in selectors:
            if not sel:
                continue
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    return True
            except Exception:
                pass
        return False

    def _wait_captcha_if_needed(self):
        """DKAPTCHA 감지 시 GPT-4o Vision 으로 자동 풀이, 실패 시 수동 대기"""
        page = self.page

        # CAPTCHA 존재 여부 확인 (3초)
        captcha_sel = "a[href*='dkaptcha'], [class*='dkaptcha'], [id*='dkaptcha']"
        try:
            page.locator(captcha_sel).first.wait_for(state="visible", timeout=3_000)
        except Exception:
            return  # CAPTCHA 없음 → 바로 반환

        self._log("=" * 50)
        self._log("[CAPTCHA] DKAPTCHA 감지!")

        captcha_frame = self._get_dkaptcha_frame()

        # API 키 있으면 GPT-4o 자동 풀이 시도 (최대 3회)
        if self.captcha_solver.enabled():
            mode_text = "OpenAI GPT-4o"
            self._log(f"[CAPTCHA] {mode_text}로 자동 풀이 시도...")
            for attempt in range(1, 4):
                try:
                    if attempt > 1:
                        self._refresh_dkaptcha(captcha_frame)
                        captcha_frame = self._get_dkaptcha_frame()

                    answer = self._solve_dkaptcha_with_ai(captcha_frame)
                    if answer:
                        self._log(f"[CAPTCHA] AI 답변: '{answer}' (시도 {attempt}/3)")
                        if self._submit_dkaptcha_answer(captcha_frame, answer):
                            self._log("[CAPTCHA] 자동 풀이 성공!")
                            return
                        self._log(f"[CAPTCHA] 제출 후 팝업 유지 — 재시도 {attempt}/3")
                except Exception as e:
                    self._log(f"[CAPTCHA] AI 풀이 오류({attempt}/3): {e}")

            self._log("[CAPTCHA] AI 자동 처리 실패 → 수동 입력으로 전환")
        else:
            self._log("[CAPTCHA] CAPTCHA 중계 서버 미설정 → 수동 입력 필요")

        # 수동 대기 폴백
        self._log("[CAPTCHA] 브라우저에서 직접 정답 입력 후 '답변 제출'을 눌러주세요.")
        self._log("[CAPTCHA] 최대 5분 대기...")
        self._log("=" * 50)
        page.bring_to_front()

        for i in range(300):
            time.sleep(1)
            try:
                if not page.locator(captcha_sel).first.is_visible():
                    self._log("[CAPTCHA] 완료 — 계속 진행합니다.")
                    return
            except Exception:
                self._log("[CAPTCHA] 완료 — 계속 진행합니다.")
                return
            if (i + 1) % 30 == 0:
                self._log(f"[CAPTCHA] 수동 대기 중... ({i+1}초)")

        self._log("[CAPTCHA] 5분 초과 — 강제 진행합니다.")

    def _get_dkaptcha_frame(self):
        page = self.page
        try:
            if page.locator("iframe[src*='dkaptcha']").count() > 0:
                return page.frame_locator("iframe[src*='dkaptcha']").first
        except Exception:
            pass
        try:
            if page.locator("#dkaptcha iframe").count() > 0:
                return page.frame_locator("#dkaptcha iframe").first
        except Exception:
            pass
        return page

    def _get_login_dkaptcha_target(self):
        page = self.page
        try:
            if page.locator("iframe[src*='dkaptcha']").count() > 0:
                return page.frame_locator("iframe[src*='dkaptcha']").first
        except Exception:
            pass
        return page

    def _get_frame_offset(self):
        try:
            box = self.page.locator("iframe[src*='dkaptcha']").first.bounding_box(timeout=1_000)
            if box:
                return {"x": box["x"], "y": box["y"]}
        except Exception:
            pass
        return {"x": 0, "y": 0}

    def _refresh_dkaptcha(self, captcha_frame):
        target = captcha_frame or self.page
        try:
            target.locator("button[aria-label*='새로'], button:has-text('새로'), button").first.click(timeout=2_000)
            self._log("  → CAPTCHA 새 문제 요청")
            time.sleep(1.5)
        except Exception:
            pass

    def _solve_login_dkaptcha_with_ai(self, captcha_frame=None) -> dict:
        import base64
        import json

        page = self.page
        target = captcha_frame or page

        screenshot_bytes = None
        frame_offset = {"x": 0, "y": 0}
        for sel in ["body", "[class*='dkaptcha']", "[id*='dkaptcha']", ".box_captcha", ".cont_captcha"]:
            try:
                el = target.locator(sel).first
                if el.is_visible():
                    screenshot_bytes = el.screenshot()
                    frame_offset = self._get_frame_offset() if target is not page else {"x": 0, "y": 0}
                    break
            except Exception:
                pass
        if not screenshot_bytes:
            screenshot_bytes = page.screenshot()

        b64_img = base64.b64encode(screenshot_bytes).decode("utf-8")

        prompt = (
            "이 이미지는 카카오 로그인 자동방지 DKAPTCHA입니다.\n"
            "반드시 질문 문장을 먼저 읽고, 질문의 의도에 맞게 아래 4가지 중 하나로 풀이하세요.\n\n"
            "유형 A — 아이콘 장소명 입력형:\n"
            "- 질문 문장: '아래 그림에 해당하는 장소를 입력해주세요'\n"
            "- 아래쪽 작은 이모티콘/아이콘과 같은 아이콘이 지도 안의 어느 장소명 옆에 있는지 찾습니다.\n"
            "- 이 유형은 클릭이 아닙니다. 그 아이콘에 해당하는 장소의 전체 명칭을 answer에 입력해야 합니다.\n"
            "- 예: 아래 그림이 집/건물 아이콘이고 지도에서 같은 아이콘이 '파인센트럴빌' 옆에 있으면 answer='파인센트럴빌'입니다.\n"
            "- 예: 아래 그림이 네모/정지 모양 아이콘이고 지도에서 같은 아이콘이 '미업티 디자인랩' 옆에 있으면 answer='미업티디자인랩' 또는 화면의 전체 장소명입니다.\n\n"
            "유형 B — 장소명 클릭형:\n"
            "- 질문 문장: '아래 장소를 지도에서 눌러주세요'\n"
            "- 아래 파란 글자로 장소명이 제시됩니다. 예: '장군집'\n"
            "- 이 유형은 입력이 아닙니다. 지도 위에서 해당 장소명/마커의 중심을 클릭해야 합니다.\n"
            "- x,y는 제공된 스크린샷 이미지 기준으로 지도 안의 해당 장소 중심 좌표를 반환하세요.\n\n"
            "유형 C — 아이콘 위치 클릭형:\n"
            "- 질문 문장: '아래 그림이 보이는 곳을 지도에서 눌러주세요'\n"
            "- 아래쪽 작은 이모티콘/아이콘과 같은 아이콘을 지도 안에서 찾아 클릭해야 합니다.\n"
            "- 이 유형은 입력이 아닙니다. 지도 안에서 같은 아이콘의 중심 좌표를 x,y로 반환하세요.\n"
            "- 반드시 아래쪽 예시 아이콘 자체가 아니라, 지도 이미지 안에 있는 같은 아이콘을 클릭해야 합니다.\n\n"
            "유형 D — 빈칸 문자 입력형:\n"
            "- 질문 문장: '빈칸에 들어갈 글자를 입력해주세요'\n"
            "- 파란색 퀴즈 글자의 ___ 빈칸을 지도 장소명에서 찾아 answer에 입력합니다.\n"
            "- 이 유형은 클릭이 아닙니다.\n\n"
            "좌표 규칙:\n"
            "- x,y는 제공된 스크린샷 이미지 기준 픽셀 좌표입니다. 왼쪽 위가 x=0,y=0입니다.\n"
            "- 클릭형(type='click')일 때만 x,y를 의미 있게 반환합니다.\n"
            "- 입력형(type='input')일 때는 x=0,y=0으로 두고 answer만 정확히 반환합니다.\n\n"
            "가장 중요한 구분:\n"
            "- '입력해주세요'가 있으면 type='input'입니다.\n"
            "- '눌러주세요'가 있으면 type='click'입니다.\n"
            "- '아래 그림에 해당하는 장소를 입력'은 아이콘을 보고 장소명을 입력하는 문제입니다. 클릭하지 마세요.\n"
            "- '아래 그림이 보이는 곳을 지도에서 눌러'는 아이콘 위치를 지도에서 클릭하는 문제입니다. 입력하지 마세요.\n\n"
            "JSON만 출력하세요. 설명 금지.\n"
            "{\"type\":\"input 또는 click\", \"question_type\":\"icon_name_input/place_click/icon_click/blank_input\", \"x\":0, \"y\":0, \"answer\":\"정답 또는 빈 문자열\"}"
        )

        data = self.captcha_solver.solve_login(b64_img, prompt)
        solve_type = str(data.get("type", "")).strip()
        question_type = str(data.get("question_type", "")).strip()
        answer = str(data.get("answer", "")).strip()
        x = int(float(data.get("x", 0) or 0))
        y = int(float(data.get("y", 0) or 0))
        if question_type in {"icon_name_input", "blank_input", "name_input"}:
            solve_type = "input"
        elif question_type in {"place_click", "icon_click", "map_click"}:
            solve_type = "click"
        page_x = x + int(frame_offset["x"])
        page_y = y + int(frame_offset["y"])
        self._log(f"  → 로그인 CAPTCHA AI 해석: type={solve_type}, question_type={question_type}, x={x}, y={y}, answer='{answer}'")
        return {"type": solve_type, "question_type": question_type, "x": page_x, "y": page_y, "answer": answer}

    def _submit_login_dkaptcha_click(self, captcha_frame, result: dict) -> bool:
        page = self.page
        target = captcha_frame or page
        x = int(result.get("x", 0) or 0)
        y = int(result.get("y", 0) or 0)
        if x <= 0 or y <= 0:
            raise RuntimeError("위치 클릭형 CAPTCHA 좌표가 비어 있습니다.")

        page.mouse.click(x, y)

        self._log("  → 지도 위치 클릭 완료")
        time.sleep(0.8)

        clicked = False
        submit_candidates = [
            "#btn_dkaptcha_submit",
            "button:has-text('답변 제출')",
            "button[type='submit']",
        ]
        for selector in submit_candidates:
            try:
                button = target.locator(selector).first
                button.wait_for(state="attached", timeout=1_000)
                try:
                    button.click(timeout=2_000)
                except Exception:
                    button.evaluate("btn => { if (!btn.disabled) btn.click(); }")
                self._log(f"  → 로그인 CAPTCHA 제출 클릭: {selector}")
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            try:
                target.locator("#btn_dkaptcha_submit").evaluate("btn => { if (btn) btn.click(); }")
                clicked = True
            except Exception:
                pass

        for _ in range(10):
            time.sleep(1)
            if self._is_dkaptcha_completed() or "accounts.kakao.com" not in page.url:
                return True

        return False

    def _submit_dkaptcha_answer(self, captcha_frame, answer: str) -> bool:
        page = self.page
        target = captcha_frame or page

        if not answer:
            raise RuntimeError("DKAPTCHA 정답이 비어 있습니다.")

        input_candidates = [
            "#inpDkaptcha",
            "input[placeholder*='정답']",
            "input[placeholder*='입력']",
            "input:not([type])",
            "input[placeholder*='정답']",
            "input[type='text']",
        ]
        submitted = False

        for selector in input_candidates:
            try:
                inp = target.locator(selector).first
                inp.wait_for(state="visible", timeout=3_000)
                inp.click(timeout=3_000)
                inp.press("Control+A")
                inp.press("Backspace")
                inp.type(answer, delay=120)
                self._log(f"  → CAPTCHA 입력 완료: {selector}")
                submitted = True
                break
            except Exception:
                continue

        if not submitted:
            raise RuntimeError("DKAPTCHA 입력칸을 찾지 못했습니다.")

        # 버튼 활성화 대기: disabled 제거 + inner_submit_btn on 클래스
        enabled = False
        for _ in range(20):
            time.sleep(0.25)
            try:
                enabled = target.locator("#btn_dkaptcha_submit").evaluate(
                    """btn => {
                        const inner = document.getElementById('inner_submit_btn');
                        return !!btn && !btn.disabled && !btn.getAttribute('disabled') &&
                               !!inner && inner.classList.contains('on');
                    }"""
                )
                if enabled:
                    self._log("  → 답변 제출 버튼 활성화 확인")
                    break
            except Exception:
                pass

        if not enabled:
            self._log("  → 제출 버튼 비활성 상태 — 이벤트 강제 발생")
            try:
                target.locator("#inpDkaptcha, input[placeholder*='정답'], input[type='text']").first.evaluate(
                    """inp => {
                        inp.focus();
                        ['keydown','keypress','keyup','input','change'].forEach(type => {
                            inp.dispatchEvent(new Event(type, {bubbles:true, cancelable:true}));
                        });
                    }"""
                )
                time.sleep(0.5)
            except Exception:
                pass

        clicked = False
        try:
            clicked = target.locator("#btn_dkaptcha_submit").evaluate(
                """btn => {
                    if (!btn || btn.disabled || btn.getAttribute('disabled')) return false;
                    btn.click();
                    return true;
                }"""
            )
            if clicked:
                self._log("  → CAPTCHA 제출 클릭: #btn_dkaptcha_submit")
        except Exception:
            clicked = False

        if not clicked:
            try:
                target.locator("#inpDkaptcha, input[placeholder*='정답'], input[type='text']").first.press("Enter")
                self._log("  → CAPTCHA Enter 제출")
            except Exception:
                self._log("  → CAPTCHA 제출 버튼/Enter 모두 실패")

        for _ in range(10):
            time.sleep(1)
            if self._is_dkaptcha_completed():
                return True

        return False

    def _is_dkaptcha_completed(self) -> bool:
        page = self.page
        try:
            if page.locator("iframe[src*='dkaptcha']").count() == 0:
                return True
            if page.locator("iframe[src*='dkaptcha']").first.is_hidden(timeout=500):
                return True
        except Exception:
            return True

        try:
            current_url = page.url or ""
            if "/entry/" in current_url and "/manage/newpost" not in current_url:
                return True
        except Exception:
            pass

        return False

    def _solve_dkaptcha_with_ai(self, captcha_frame=None) -> str:
        """GPT-4o Vision으로 DKAPTCHA 정답 추출"""
        import base64

        page = self.page
        target = captcha_frame or page

        # 힌트 텍스트 추출 — 모든 텍스트 노드에서 ___ 패턴 찾기
        hint = ""
        for sel in ["body", "#labDkaptcha", "label[for='inpDkaptcha']", ".txt", "strong", ".tit"]:
            try:
                els = target.locator(sel).all()
                for el in els:
                    t = el.text_content() or ""
                    if "___" in t or "__" in t:
                        hint = t.strip()
                        break
                if hint:
                    break
            except Exception:
                pass

        # CAPTCHA 팝업 영역 스크린샷
        screenshot_bytes = None
        for sel in ["body", "[class*='dkaptcha']", "[id*='dkaptcha']", ".ReactModal__Content"]:
            try:
                el = target.locator(sel).first
                if el.is_visible():
                    screenshot_bytes = el.screenshot()
                    break
            except Exception:
                pass
        if not screenshot_bytes:
            screenshot_bytes = page.screenshot()

        b64_img = base64.b64encode(screenshot_bytes).decode("utf-8")

        prompt = (
            "이 이미지는 한국 블로그 DKAPTCHA 퀴즈입니다.\n"
            "반드시 아래 규칙대로 풀어야 합니다.\n\n"
        )
        if hint:
            prompt += f"퀴즈 문장 OCR 후보: {hint}\n\n"
        prompt += (
            "규칙:\n"
            "1. 먼저 화면 아래쪽 파란색 퀴즈 글자와 문장을 읽습니다.\n"
            "2. 유형을 판단합니다.\n"
            "   - 빈칸형: 퀴즈 글자에 ___ 또는 __가 있으면 빈칸형입니다. 예: 에덴___파트\n"
            "   - 전체명칭형: 문장에 '전체 명칭' 또는 '전체명칭'이 있고 퀴즈 글자가 단어 일부이면 전체명칭형입니다. 예: '마트의 전체 명칭' + 퀴즈 '마트'\n"
            "3. 빈칸형이면 ___ 앞(prefix), ___ 뒤(suffix)를 분리하고 지도에서 prefix로 시작하고 suffix로 끝나는 장소명을 찾아, 그 사이 글자만 answer로 반환합니다.\n"
            "   - suffix가 비어 있으면 지도에서 prefix로 시작하는 전체 장소명을 찾고, prefix 뒤에 남는 글자만 answer로 반환합니다.\n"
            "4. 전체명칭형이면 지도에서 퀴즈 단어가 포함된 장소의 전체 이름을 찾아 전체 이름을 answer로 반환합니다.\n\n"
            "중요:\n"
            "- 지도에 여러 장소명이 있어도 퀴즈의 prefix/suffix와 정확히 맞는 장소명만 사용하세요.\n"
            "- 예: 퀴즈가 에덴___파트이고 지도에 에덴아파트가 있으면 answer는 아 입니다.\n"
            "- 예: 퀴즈가 전___차충전소이고 지도에 전기차충전소가 있으면 answer는 기 입니다.\n"
            "- 예: 퀴즈가 배스킨___스이고 지도에 배스킨라빈스가 있으면 answer는 라빈 입니다.\n\n"
            "- 예: 퀴즈가 한빛내과의___이고 지도에 한빛내과의원이 있으면 answer는 원 입니다.\n\n"
            "전체명칭형 예시:\n"
            "- 문장: '지도에 있는 마트의 전체 명칭을 입력해주세요', 퀴즈: '마트', 지도: '하나로마트' → answer는 하나로마트 입니다. 마트나 하나로가 아닙니다.\n"
            "- 문장: '지도에 있는 교회의 전체 명칭을 입력해주세요', 퀴즈: '교회', 지도: '광명교회' → answer는 광명교회 입니다. 광명이 아닙니다.\n\n"
            "숫자 주의:\n"
            "- 퀴즈 뒤쪽(suffix)이 숫자로 시작하면, 그 숫자는 장소명과 겹치는 기준 글자일 수 있지만 정답 입력에는 포함될 수 있습니다.\n"
            "- 예: 퀴즈가 대림빌___0차이고 지도에 대림빌라10차가 있으면 answer는 라10 입니다. 라1이 아닙니다.\n\n"
            "JSON만 출력하세요. 설명 금지.\n"
            "{\"type\":\"blank 또는 full_name\", \"quiz\":\"읽은 퀴즈\", \"place\":\"지도에서 찾은 전체 장소명\", \"answer\":\"정답\"}"
        )

        try:
            data = self.captcha_solver.solve_publish(b64_img, prompt, hint=hint)
            quiz_type = str(data.get("type", "")).strip()
            quiz = str(data.get("quiz", "")).strip()
            place = str(data.get("place", "")).strip()
            answer = str(data.get("answer", "")).strip()
            fixed_answer = self._derive_answer_from_quiz_place(quiz, place, quiz_type)
            if fixed_answer:
                answer = fixed_answer
            self._log(f"  → AI 해석: 유형='{quiz_type}' | 퀴즈='{quiz}' | 장소='{place}' | 정답='{answer}'")
            return answer.strip(".,!?\"'")
        except Exception:
            raise

    def _derive_answer_from_quiz_place(self, quiz: str, place: str, quiz_type: str = "") -> str:
        if not quiz or not place:
            return ""

        import re

        compact_quiz = re.sub(r"\s+", "", quiz).strip()
        compact_place = re.sub(r"\s+", "", place).strip()
        if not compact_quiz or not compact_place:
            return ""

        if quiz_type == "full_name" and compact_quiz in compact_place:
            return compact_place

        match = re.search(r"(.+?)(_{2,})(.*)", compact_quiz)
        if not match:
            return ""

        prefix = match.group(1)
        suffix = match.group(3)
        prefix_idx = compact_place.find(prefix)
        if prefix_idx < 0:
            return ""

        start = prefix_idx + len(prefix)
        if not suffix:
            return compact_place[start:]

        suffix_idx = compact_place.find(suffix, start)
        if suffix_idx >= 0:
            return compact_place[start:suffix_idx]

        return ""

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
