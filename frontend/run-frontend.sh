#!/bin/bash

# 프론트엔드 실행 스크립트
# Author: 피피

echo "🎨 MQTT 대시보드 프론트엔드 실행 시작"

# 경로 이동
cd "$(dirname "$0")/frontend" || exit 1

# Node 모듈 설치 (최초 1회만)
if [ ! -d "node_modules" ]; then
  echo "📦 의존성 설치 중 (npm install)..."
  npm install
fi

# 개발 서버 실행
echo "🚀 React 개발 서버 실행 중..."
npm start
