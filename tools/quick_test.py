#!/usr/bin/env python3
"""
MOJI WebChat 빠른 테스트 스크립트
웹 브라우저에서 챗봇과 대화하기 위한 서버 실행
"""

import os
import sys
import time
import subprocess
import webbrowser
from pathlib import Path

def check_requirements():
    """필수 패키지 확인"""
    try:
        import fastapi
        import uvicorn
        import langchain
        import openai
        print("✅ 모든 필수 패키지가 설치되어 있습니다.")
        return True
    except ImportError as e:
        print(f"❌ 필수 패키지가 없습니다: {e}")
        print("\n다음 명령으로 설치하세요:")
        print("pip install -r requirements.txt")
        return False

def check_api_key():
    """API 키 확인"""
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env 파일이 없습니다.")
        return False
    
    with open(env_path, 'r') as f:
        content = f.read()
        if 'your-openai-api-key-here' in content:
            print("⚠️  OpenAI API 키가 설정되지 않았습니다!")
            print(".env 파일에서 LLM_API_KEY를 실제 API 키로 변경하세요.")
            return False
    
    print("✅ API 키가 설정되어 있습니다.")
    return True

def start_server():
    """FastAPI 서버 시작"""
    print("\n🚀 MOJI 서버를 시작합니다...")
    print("=" * 50)
    print("서버 주소: http://localhost:8000")
    print("웹챗 주소: http://localhost:8000/static/webchat-test.html")
    print("웹챗 주소: http://localhost:8000/static/moji-webchat-v2.html")
    print("API 문서: http://localhost:8000/docs")
    print("=" * 50)
    print("\n서버를 중지하려면 Ctrl+C를 누르세요.")
    
    # 3초 후 브라우저 자동 열기
    print("\n3초 후 웹 브라우저가 자동으로 열립니다...")
    time.sleep(3)
    
    # 브라우저 열기
    webbrowser.open("http://localhost:8000/static/webchat-test.html")
    
    # 서버 실행
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "app.main:app", 
            "--reload", 
            "--host", "0.0.0.0", 
            "--port", "8000"
        ])
    except KeyboardInterrupt:
        print("\n\n👋 서버를 종료합니다.")

def main():
    """메인 실행 함수"""
    print("🤖 MOJI WebChat 테스트 도구")
    print("=" * 50)
    
    # 요구사항 확인
    if not check_requirements():
        return
    
    # API 키 확인
    if not check_api_key():
        response = input("\nAPI 키 없이 계속하시겠습니까? (y/N): ")
        if response.lower() != 'y':
            return
    
    # 서버 시작
    start_server()

if __name__ == "__main__":
    main()