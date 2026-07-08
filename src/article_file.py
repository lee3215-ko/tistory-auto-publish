"""원고 파일 발행 결과에 따른 폴더 이동."""

from __future__ import annotations

import shutil
from pathlib import Path

FOLDER_SUCCESS = "발행완료"
FOLDER_FAILED = "발행실패"


def move_article_after_publish(article_path: str, *, success: bool) -> str | None:
    """원고 파일을 같은 폴더 아래 발행완료/발행실패 하위 폴더로 이동."""
    src = Path(article_path).resolve()
    if not src.is_file():
        return None
    if src.parent.name in (FOLDER_SUCCESS, FOLDER_FAILED):
        return str(src)

    dest_dir = src.parent / (FOLDER_SUCCESS if success else FOLDER_FAILED)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        stem, suffix = src.stem, src.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(src), str(dest))
    return str(dest)
