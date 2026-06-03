"""
cp_encn.py — Classplus .encn encrypted video handler
Handles videos served from paths containing '_encn/master.m3u8'.
"""


async def decrypt_cp_encn_video(url: str, output_path: str, token: str = None) -> str | None:
    """
    Attempt to decrypt a Classplus .encn video stream.
    The stream is typically served as a standard HLS playlist once the signed
    URL is obtained via the Golden Eagle API (handled by drm_handler.py before
    this function is reached).  This function is a post-processing hook for
    any remaining proprietary decryption step.

    Args:
        url:         Signed / resolved HLS URL.
        output_path: Local path where the final video should be written.
        token:       Optional access token for re-signing if needed.

    Returns:
        output_path on success, or None if decryption is not needed / failed.
    """
    import os
    import subprocess

    if not url:
        return None

    # Standard yt-dlp download for already-signed .encn streams
    cmd = (
        f'yt-dlp --concurrent-fragments 8 '
        f'--fragment-retries 10 '
        f'--hls-use-mpegts '
        f'--no-check-certificate '
        f'-o "{output_path}" '
        f'"{url}"'
    )
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True)
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
        print(f"cp_encn yt-dlp stderr: {result.stderr.decode(errors='ignore')[:500]}")
        return None
    except Exception as e:
        print(f"cp_encn error: {e}")
        return None
