# 경량화된 파이썬 3.9 버전을 베이스로 사용합니다.
FROM python:3.9-slim

# 작업 디렉토리 설정
WORKDIR /app

# 컨테이너의 시스템 시간대를 한국 시간(KST)으로 설정
ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 요구사항 파일을 먼저 복사하고 패키지를 설치합니다. (캐시 효율 극대화)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 나머지 소스 코드를 모두 복사합니다.
COPY . .

# Flask 서버가 사용하는 5000번 포트를 엽니다.
EXPOSE 5000

# 앱 실행 (app.py)
CMD ["python", "app.py"]