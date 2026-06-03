"""
appx_al.py — Appx / ClassX / SecureVideo link handler module
Handles XOR-encrypted videos/PDFs, node:// frozen directories, isp:// links,
ZIP-to-video extraction, and Cloudflare-protected PDFs.
"""

import os
import re
import json
import base64
import asyncio
import requests
import aiohttp
import aiofiles
import shutil
import tempfile
import zipfile
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# ── Constants ────────────────────────────────────────────────────────────────
APPX_REFERER = "https://player.akamai.net.in/"
_APPX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36",
    "Referer": APPX_REFERER,
    "Origin": "https://player.akamai.net.in",
    "Accept": "*/*",
    "Connection": "keep-alive",
}
_DL_TIMEOUT = aiohttp.ClientTimeout(total=600, connect=15, sock_read=120)
_CHUNK = 512 * 1024  # 512 KB


# ── Data class ───────────────────────────────────────────────────────────────
@dataclass
class AppxLinkInfo:
    url: str = ""
    link_type: str = "generic"   # xor_video | xor_pdf | enc_pdf | zip_video | hls_live | cloudflare_pdf | generic
    needs_referer: bool = False
    pdf_enc_key: Optional[str] = None
    xor_key: Optional[str] = None
    uhs_version: str = "1"


# ── Public helpers ────────────────────────────────────────────────────────────
def get_appx_headers() -> dict:
    return dict(_APPX_HEADERS)


def get_ytdlp_appx_header_args() -> str:
    return (
        '--add-header "Referer:https://player.akamai.net.in/" '
        '--add-header "Origin:https://player.akamai.net.in" '
        '--add-header "User-Agent:Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36"'
    )


# ── Link classification ───────────────────────────────────────────────────────
def classify_appx_link(url: str) -> AppxLinkInfo:
    """Inspect a URL and return an AppxLinkInfo describing how to handle it."""
    info = AppxLinkInfo(url=url)
    if not url:
        return info

    lower = url.lower()

    # XOR encrypted video (securevideo / classx with * separator)
    if ("securevideo" in lower or "classx" in lower or "appx" in lower) and "*" in url:
        if ".pdf" not in lower:
            parts = url.split("*", 1)
            info.url = parts[0].strip()
            info.xor_key = parts[1].strip() if len(parts) > 1 else None
            info.link_type = "xor_video"
            info.needs_referer = True
            return info

    # XOR encrypted PDF
    if ".pdf" in lower and "*" in url:
        parts = url.split("*", 1)
        info.url = parts[0].strip()
        info.pdf_enc_key = parts[1].strip() if len(parts) > 1 else None
        info.link_type = "xor_pdf"
        info.needs_referer = True
        return info

    # Cloudflare-protected PDF
    if ".pdf" in lower and "cloudflare" in lower:
        info.link_type = "cloudflare_pdf"
        return info

    # ZIP → video (UHS offline content)
    uhs_match = re.search(r"uhs[_-]?(\d)", url, re.IGNORECASE)
    if uhs_match and url.endswith(".zip"):
        info.link_type = "zip_video"
        info.uhs_version = uhs_match.group(1)
        info.needs_referer = True
        return info

    # HLS live stream
    if url.endswith(".m3u8") and "live" in lower:
        info.link_type = "hls_live"
        return info

    # Appx encrypted PDF (API-based)
    if ".pdf" in lower and ("appx" in lower or "classx" in lower):
        info.link_type = "enc_pdf"
        info.needs_referer = True
        return info

    # Generic appx link needing referer
    if any(d in lower for d in ["appx", "classx", "securevideo", "player.akamai"]):
        info.needs_referer = True

    return info


# ── Node:// frozen directory ──────────────────────────────────────────────────
def is_node_link(url: str) -> bool:
    """Return True if the string looks like a JSON node-directory object."""
    try:
        data = json.loads(url.strip())
        return isinstance(data, dict) and any(
            k in data for k in ("url", "hls", "dash", "stream", "video_url")
        )
    except (json.JSONDecodeError, ValueError):
        return False


async def resolve_node_link(node_jstr: str, resolution: int = 480) -> str:
    """Resolve a node:// JSON string to a playable URL."""
    data = json.loads(node_jstr)
    for key in ("hls", "dash", "url", "video_url", "stream"):
        val = data.get(key)
        if val and isinstance(val, str) and "://" in val:
            return val
    for key in (f"{resolution}p", str(resolution), "720p", "480p", "360p"):
        val = data.get(key)
        if val and isinstance(val, str) and "://" in val:
            return val
    raise ValueError(f"No playable URL found in node JSON. Keys: {list(data.keys())}")


# ── ISP:// insecure-player link ───────────────────────────────────────────────
def resolve_isp_link(payload: str) -> str:
    """Base64-decode an isp:// payload into a playable URL."""
    try:
        decoded = base64.b64decode(payload + "==").decode("utf-8").strip()
        if "://" in decoded:
            return decoded
    except Exception:
        pass
    decoded2 = urllib.parse.unquote(payload)
    if "://" in decoded2:
        return decoded2
    return payload


# ── AES decrypt helper ────────────────────────────────────────────────────────
def decrypt_aes_link(encrypted_data: str, aes_key: str, aes_iv: str) -> str:
    key_bytes = bytes.fromhex(aes_key)
    iv_bytes = bytes.fromhex(aes_iv)
    data = base64.b64decode(encrypted_data)
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    return unpad(cipher.decrypt(data), AES.block_size).decode("utf-8")


# ── XOR helpers ───────────────────────────────────────────────────────────────
def decrypt_xor(file_path: str, xor_key: str) -> bool:
    """XOR-decrypt a file in-place."""
    if not file_path or not os.path.exists(file_path) or not xor_key:
        return bool(xor_key is None)
    key_bytes = xor_key.encode("utf-8")
    key_len = len(key_bytes)
    chunk_size = _CHUNK
    try:
        with open(file_path, "r+b") as f:
            offset = 0
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                dec = bytes(b ^ key_bytes[(offset + i) % key_len] for i, b in enumerate(chunk))
                f.seek(offset)
                f.write(dec)
                offset += len(chunk)
        return True
    except Exception as e:
        print(f"XOR decrypt error: {e}")
        return False


def deobfuscate_ts(ts_data: bytes, key: str) -> bytes:
    """XOR-deobfuscate a TS segment in memory."""
    if not key:
        return ts_data
    kb = key.encode("utf-8")
    kl = len(kb)
    return bytes(b ^ kb[i % kl] for i, b in enumerate(ts_data))


# ── Async PDF downloaders ─────────────────────────────────────────────────────
async def download_xor_pdf(pdf_file: str, url: str, enc_key: Optional[str]) -> None:
    """Download a PDF then XOR-decrypt it if enc_key is provided."""
    hdr = get_appx_headers()
    async with aiohttp.ClientSession(timeout=_DL_TIMEOUT) as session:
        async with session.get(url, headers=hdr, allow_redirects=True) as resp:
            if resp.status not in (200, 206):
                raise Exception(f"HTTP {resp.status} downloading PDF")
            async with aiofiles.open(pdf_file, "wb") as f:
                async for chunk in resp.content.iter_chunked(_CHUNK):
                    await f.write(chunk)
    if enc_key and os.path.exists(pdf_file):
        decrypt_xor(pdf_file, enc_key)


async def download_encrypted_pdf(url: str, pdf_file: str) -> None:
    await download_xor_pdf(pdf_file, url, enc_key=None)


async def download_cloudflare_pdf(url: str, pdf_file: str) -> None:
    """Download a Cloudflare-protected PDF via cloudscraper, falling back to aiohttp."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        async with aiofiles.open(pdf_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=_CHUNK):
                if chunk:
                    await f.write(chunk)
    except ImportError:
        await download_xor_pdf(pdf_file, url, enc_key=None)


# ── ZIP → video ───────────────────────────────────────────────────────────────
async def zip_to_video(url: str, name: str, output_dir: str = ".") -> Optional[str]:
    """Download a ZIP archive and extract the video or m3u8 playlist inside."""
    temp_dir = tempfile.mkdtemp(prefix="appx_zip_")
    zip_path = os.path.join(temp_dir, f"{name}.zip")
    try:
        hdr = get_appx_headers()
        async with aiohttp.ClientSession(timeout=_DL_TIMEOUT) as session:
            async with session.get(url, headers=hdr, allow_redirects=True) as resp:
                resp.raise_for_status()
                async with aiofiles.open(zip_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        await f.write(chunk)

        extract_dir = os.path.join(temp_dir, "extract")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        for root, _, files in os.walk(extract_dir):
            for fname in files:
                if fname.endswith(".m3u8"):
                    return os.path.join(root, fname)
                if fname.endswith((".mp4", ".mkv", ".webm")):
                    dest = os.path.join(output_dir, f"{name}{os.path.splitext(fname)[1]}")
                    shutil.move(os.path.join(root, fname), dest)
                    return dest
        return None
    except Exception as e:
        print(f"zip_to_video error: {e}")
        return None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
