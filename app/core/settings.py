"""设置存储：settings 表 + 项目根 .env（GitHub Token 加密保存，不落库）。"""
import logging
from contextlib import closing

from app.constants import (
    ENV_FILE,
    SETTING_GITHUB_TOKEN,
    SETTING_LAST_PAGE,
    SETTING_SCAN_ROOT,
    SETTING_THEME,
    THEMES,
)
from app.core import secrets
from app.core.db import get_connection

log = logging.getLogger(__name__)

_KEY_PLAIN = "GITHUB_TOKEN"
_KEY_ENC = "GITHUB_TOKEN_DPAPI"


def _read_env() -> dict[str, str]:
    """手工解析 .env（key=value，支持 # 注释），无依赖。"""
    if not ENV_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            out[k.strip()] = v.strip()
    return out


def _write_env(values: dict[str, str | None]) -> None:
    """更新 .env 中的键（保留注释与顺序）；值为 None 表示删除该键。"""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.partition("=")[0].strip()
            if k in values:
                seen.add(k)
                if values[k] is not None:
                    out.append(f"{k}={values[k]}")
                continue
        out.append(line)
    for k, v in values.items():
        if k not in seen and v is not None:
            out.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _take_legacy_db_token() -> str | None:
    old = SettingsStore.get(SETTING_GITHUB_TOKEN)
    if old:
        SettingsStore.set(SETTING_GITHUB_TOKEN, "")
        return old
    return None


def _store_token(token: str) -> None:
    """尽量加密；加密不可用时退回明文并记录一次告警。"""
    encrypted = secrets.protect(token)
    if encrypted:
        _write_env({_KEY_ENC: encrypted, _KEY_PLAIN: None})
    else:
        log.warning("DPAPI 不可用，GitHub Token 将以明文保存在 .env")
        _write_env({_KEY_PLAIN: token, _KEY_ENC: None})


def get_github_token() -> str | None:
    """读取顺序：DPAPI 密文 → 旧明文（自动迁移）→ 旧数据库值（自动迁移）。"""
    env = _read_env()
    enc = env.get(_KEY_ENC)
    if enc:
        token = secrets.unprotect(enc)
        if token:
            return token
        log.warning("Token 解密失败，可能是换了 Windows 账户；请重新设置 Token")
    plain = env.get(_KEY_PLAIN)
    if plain:
        _store_token(plain)  # 顺手升级为加密存储
        return plain
    legacy = _take_legacy_db_token()
    if legacy:
        _store_token(legacy)
        return legacy
    return None


def set_github_token(token: str) -> None:
    """token 只写 .env；空字符串表示清除。"""
    SettingsStore.set(SETTING_GITHUB_TOKEN, "")
    if not token.strip():
        _write_env({_KEY_ENC: None, _KEY_PLAIN: None})
        return
    _store_token(token.strip())


def clear_github_token() -> None:
    set_github_token("")


def token_status() -> dict:
    """给设置页/状态栏用的非敏感摘要。"""
    env = _read_env()
    if env.get(_KEY_ENC):
        return {"configured": True, "encrypted": True}
    if env.get(_KEY_PLAIN):
        return {"configured": True, "encrypted": False}
    return {"configured": False, "encrypted": False}


def get_theme() -> str:
    value = SettingsStore.get(SETTING_THEME) or "system"
    return value if value in THEMES else "system"


def set_theme(value: str) -> None:
    SettingsStore.set(SETTING_THEME, value if value in THEMES else "system")


def get_last_page() -> str:
    return SettingsStore.get(SETTING_LAST_PAGE) or "dashboard"


def set_last_page(key: str) -> None:
    SettingsStore.set(SETTING_LAST_PAGE, key)


class SettingsStore:
    """键值设置存储，全部走短连接。"""

    @staticmethod
    def get(key: str, default: str | None = None) -> str | None:
        with closing(get_connection()) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    @staticmethod
    def set(key: str, value: str) -> None:
        with closing(get_connection()) as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()

    # ---------- 扫描根目录（多值，换行分隔存储，兼容旧的单路径值） ----------

    @staticmethod
    def get_scan_roots() -> list[str]:
        """返回扫描根目录列表（按添加顺序，自动去重保序）。"""
        val = SettingsStore.get(SETTING_SCAN_ROOT) or ""
        seen: dict[str, None] = {}
        for line in val.splitlines():
            p = line.strip()
            if p:
                seen.setdefault(p)
        return list(seen)

    @staticmethod
    def set_scan_roots(roots: list[str]) -> None:
        SettingsStore.set(SETTING_SCAN_ROOT, "\n".join(roots))
