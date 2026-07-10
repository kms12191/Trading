import os

import jwt
import requests

def get_user_id_from_header(auth_header: str) -> tuple[str, str]:
    """
    Authorization 헤더의 Bearer 토큰으로부터 user_id(sub)와 토큰을 파싱합니다.
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        raise Exception("유효하지 않은 인증 헤더입니다.")
    token = auth_header.split(" ")[1]
    # JWT 서명 검증은 Supabase API 호출 단계에서 대행하므로, 여기서는 디코딩만 처리
    payload = jwt.decode(token, options={"verify_signature": False})
    user_id = payload.get("sub")
    if not user_id:
        raise Exception("토큰 페이로드가 유효하지 않습니다.")
    return user_id, token


def validate_access_token(auth_header: str) -> tuple[str, str]:
    """Supabase Auth 서버에서 액세스 토큰의 유효성과 사용자 ID를 확인합니다."""
    user_id, token = get_user_id_from_header(auth_header)
    supabase_url = str(os.getenv("SUPABASE_URL") or "").rstrip("/")
    supabase_anon_key = str(os.getenv("SUPABASE_ANON_KEY") or "").strip()
    if not supabase_url or not supabase_anon_key:
        raise ValueError("Supabase 인증 설정이 없습니다.")

    try:
        response = requests.get(
            f"{supabase_url}/auth/v1/user",
            headers={
                "apikey": supabase_anon_key,
                "Authorization": f"Bearer {token}",
            },
            timeout=5,
        )
    except requests.RequestException as error:
        raise ValueError("Supabase 인증 서버에 연결하지 못했습니다.") from error

    if response.status_code != 200:
        raise ValueError("Supabase access token 검증에 실패했습니다.")

    try:
        verified_user_id = str((response.json() or {}).get("id") or "").strip()
    except ValueError as error:
        raise ValueError("Supabase 인증 응답을 해석하지 못했습니다.") from error

    if not verified_user_id or verified_user_id != user_id:
        raise ValueError("Supabase 사용자 정보가 토큰과 일치하지 않습니다.")

    return verified_user_id, token
