"""
cw_helper.py — CareerWill download info extractor
Parses CareerWill URLs that embed decryption keys via #keysV1= fragment.
"""


def get_download_info(url: str):
    """
    Parse a CareerWill URL containing '#keysV1=' embedded key info.

    Returns:
        (clean_url: str, keys_string: str | None)
        keys_string is formatted as '--key KID:KEY --key ...' ready for mp4decrypt,
        or None if no keys are present.
    """
    if "#keysV1=" not in url:
        return url, None

    try:
        base_url, keys_part = url.split("#keysV1=", 1)
        raw_keys = [k.strip() for k in keys_part.split(",") if k.strip()]
        if not raw_keys:
            return base_url.strip(), None
        keys_string = " ".join(f"--key {k}" for k in raw_keys)
        return base_url.strip(), keys_string
    except Exception as e:
        print(f"cw_helper.get_download_info error: {e}")
        return url, None
