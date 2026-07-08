"""계정 저장/로드 관리"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import List

from paths import accounts_path, migrate_legacy_data


@dataclass
class Account:
    id: str
    password: str
    blog_url: str
    article_path: str = ""
    published_url: str = ""
    published_at: str = ""
    publish_error: str = ""

    @classmethod
    def from_line(cls, line: str) -> "Account | None":
        parts = next(csv.reader([line]))
        parts = [p.strip() for p in parts]
        if len(parts) >= 3:
            article_path = parts[3] if len(parts) >= 4 else ""
            published_url = parts[4] if len(parts) >= 5 else ""
            published_at = parts[5] if len(parts) >= 6 else ""
            publish_error = parts[6] if len(parts) >= 7 else ""
            if "/manage/" in published_url:
                published_url = ""
            return cls(
                id=parts[0],
                password=parts[1],
                blog_url=parts[2],
                article_path=article_path,
                published_url=published_url,
                published_at=published_at,
                publish_error=publish_error,
            )
        return None

    def to_line(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="")
        writer.writerow([
            self.id,
            self.password,
            self.blog_url,
            self.article_path,
            self.published_url,
            self.published_at,
            self.publish_error,
        ])
        return output.getvalue()


class AccountManager:
    def __init__(self, filepath: str | Path | None = None):
        migrate_legacy_data()
        self.filepath = Path(filepath) if filepath else accounts_path()

    def load(self) -> List[Account]:
        if not self.filepath.exists():
            return []
        accounts = []
        with self.filepath.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                acc = Account.from_line(line)
                if acc:
                    accounts.append(acc)
        return accounts

    def save(self, accounts: List[Account]):
        with self.filepath.open("w", encoding="utf-8") as f:
            f.write("# id,password,blog_url,article_path,published_url,published_at,publish_error\n")
            for acc in accounts:
                f.write(acc.to_line() + "\n")

    def add(self, account: Account):
        accounts = self.load()
        accounts.append(account)
        self.save(accounts)

    def delete(self, index: int):
        accounts = self.load()
        if 0 <= index < len(accounts):
            accounts.pop(index)
            self.save(accounts)
