# 티스토리 자동배포

티스토리·벨로그 블로그에 원고를 자동으로 발행하는 Windows 데스크톱 프로그램입니다.

## 주요 기능

- 여러 티스토리 계정·블로그 URL 일괄 관리
- 계정별 원고 파일 지정 및 자동 배포
- 발행 완료 URL·일시 기록
- OpenAI API 기반 CAPTCHA 자동 해결 (선택)
- **GitHub Releases 자동 업데이트** — 프로그램 재실행 시 새 버전 확인

## 실행 방법 (개발)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python run_gui.py
```

## 배포 빌드

```bat
build.bat
```

빌드 결과: `release\TistoryPoster\` 폴더 (`TistoryPoster.exe` 포함)

## GitHub 배포 (관리자)

```bat
.\deploy.bat
```

버전이 올라가고 GitHub Release에 zip이 업로드됩니다. 사용자 PC에서는 프로그램 시작 시 자동으로 업데이트를 확인합니다.

## 데이터 저장

- 계정 정보: `data/accounts.txt` (업데이트 시 `data/` 폴더는 보존됩니다)
- API 키·설정: Windows 레지스트리 (`QSettings`)

## 폴더 구조

```
├── gui.py              # 메인 GUI
├── gui_workers.py      # 백그라운드 작업 스레드
├── paths.py            # 버전·경로·데이터 디렉터리
├── updater.py          # GitHub 자동 업데이트 엔진
├── update_ui.py        # 업데이트 UI (PySide6)
├── ui_theme.py         # 앱 테마
├── src/
│   ├── tistory_poster.py
│   ├── account_manager.py
│   └── captcha_solver.py
└── scripts/            # GitHub 배포 스크립트
```

## 라이선스

개인·내부 사용 목적 프로젝트입니다.
