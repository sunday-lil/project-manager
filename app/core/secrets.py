"""Windows DPAPI 令牌加密（无第三方依赖）。

用当前 Windows 用户的凭据加密，加密结果只能在同一用户会话/账户下解密。
非 Windows 或调用失败时返回 None，由调用方降级为明文并提示。
"""
import base64
import ctypes
import os
from ctypes import wintypes

_CRYPTPROTECT_UI_FORBIDDEN = 0x01
_ENTROPY = b"project-manager-v2"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _ctypes_ready() -> bool:
    return os.name == "nt" and hasattr(ctypes, "windll")


def available() -> bool:
    return _ctypes_ready()


def _call(proc: str, data: bytes, entropy: bytes | None = None) -> bytes | None:
    """调用 CryptProtectData / CryptUnprotectData，返回输出字节。"""
    if not _ctypes_ready():
        return None
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    fn = getattr(crypt32, proc)
    fn.argtypes = [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR,
                   ctypes.POINTER(_DataBlob), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    in_buf = ctypes.create_string_buffer(data, len(data))
    in_blob = _DataBlob(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    ent_buf = ent_blob = None
    if entropy:
        ent_buf = ctypes.create_string_buffer(entropy, len(entropy))
        ent_blob = _DataBlob(len(entropy), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DataBlob()
    ok = fn(ctypes.byref(in_blob), "ProjectManager",
            ctypes.byref(ent_blob) if ent_blob else None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
    if not ok:
        return None
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))


def protect(text: str) -> str | None:
    """明文 → base64(DPAPI 密文)；失败返回 None。"""
    if not text:
        return None
    raw = _call("CryptProtectData", text.encode("utf-8"), _ENTROPY)
    return base64.b64encode(raw).decode("ascii") if raw else None


def unprotect(blob: str) -> str | None:
    """base64(DPAPI 密文) → 明文；失败返回 None。"""
    if not blob:
        return None
    try:
        raw = base64.b64decode(blob, validate=True)
    except (ValueError, TypeError):
        return None
    out = _call("CryptUnprotectData", raw, _ENTROPY)
    if out is None:
        return None
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return None
