# Auction Backend Project

경매 시스템을 위한 Django REST API 백엔드 프로젝트입니다.

## 🚀 프로젝트 개요

이 프로젝트는 경매 시스템의 백엔드 API를 제공합니다. 사용자 인증, 포인트 관리, 카카오페이 결제 기능을 포함하고 있습니다.

## 📋 주요 기능

- **사용자 관리**
  - 회원가입/로그인/로그아웃
  - 카카오 소셜 로그인
  - 사용자 프로필 관리
  - JWT 토큰 기반 인증

- **포인트 시스템**
  - 포인트 잔액 조회
  - 포인트 차감 기능
  - 포인트 사용 내역 관리

- **결제 시스템**
  - 카카오페이 연동
  - 결제 준비 및 승인
  - 결제 내역 관리

## 🛠 기술 스택

- **Backend**: Django 4.2.8
- **API**: Django REST Framework
- **Authentication**: JWT (Simple JWT)
- **Payment**: KakaoPay API
- **Documentation**: Swagger (drf-yasg)
- **CORS**: django-cors-headers

## 📁 프로젝트 구조

```
mutsha-auction-back-professor/
├── manage.py
├── requirements.txt
├── .env (환경변수 파일)
├── seminar/                 # Django 프로젝트 설정
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── UserProfile/            # 사용자 관리 앱
│   ├── models.py
│   ├── views.py
│   ├── serializers.py
│   ├── urls.py
│   └── ...
├── Point/                  # 포인트 관리 앱
│   ├── models.py
│   ├── views.py
│   ├── serializers.py
│   ├── urls.py
│   └── ...
└── Payment/               # 결제 관리 앱
    ├── models.py
    ├── views.py
    ├── serializers.py
    ├── urls.py
    └── ...
```

## 🔧 설치 및 실행

### 1. 저장소 클론
```bash
git clone <repository-url>
cd mutsha-auction-back-professor
```

### 2. 가상환경 생성 및 활성화
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 환경변수 설정
프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 추가하세요:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True

# Kakao Settings
KAKAO_SECRET_KEY=your-kakao-rest-api-key
KAKAO_CLIENT_SECRET=your-kakao-client-secret
KAKAO_REDIRECT_URI=http://localhost:5173/auth
KAKAO_PAY_KEY=your-kakao-pay-secret-key-dev
KAKAO_PAY_CID=TC0ONETIME
```

### 5. 데이터베이스 마이그레이션
```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. 서버 실행
```bash
python manage.py runserver
```

서버가 실행되면 다음 URL에서 접근할 수 있습니다:
- 메인 서버: http://localhost:8000
- 관리자 페이지: http://localhost:8000/admin
- API 문서 (Swagger): http://localhost:8000/swagger/

## 📚 API 문서

### 인증 관련 API
- `POST /api/user/signup/` - 회원가입
- `POST /api/user/signin/` - 로그인
- `POST /api/user/signout/` - 로그아웃
- `POST /api/user/refresh/` - 토큰 갱신
- `GET /api/user/kakao/` - 카카오 로그인
- `GET /api/user/kakao/callback/` - 카카오 로그인 콜백

### 포인트 관련 API
- `GET /api/point/` - 포인트 잔액 조회
- `POST /api/point/deduct/` - 포인트 차감

### 결제 관련 API
- `POST /api/payment/ready/` - 결제 준비
- `POST /api/payment/approve/` - 결제 승인

## 🔐 인증

이 프로젝트는 JWT (JSON Web Token) 기반 인증을 사용합니다.

### 토큰 사용법
API 요청 시 Authorization 헤더에 Bearer 토큰을 포함하세요:
```
Authorization: Bearer <your-access-token>
```

## 💳 카카오페이 연동

카카오페이 결제 기능을 사용하려면 다음이 필요합니다:
1. 카카오페이 개발자 계정
2. 카카오페이 앱 등록
3. 결제 키 및 시크릿 키 발급

## 🧪 테스트

```bash
python manage.py test
```

## 📝 환경변수 설명

| 변수명 | 설명 | 예시 |
|--------|------|------|
| `SECRET_KEY` | Django 시크릿 키 | django-insecure-... |
| `KAKAO_SECRET_KEY` | 카카오 앱의 REST API 키 (= client_id) | your-kakao-rest-api-key |
| `KAKAO_CLIENT_SECRET` | 카카오 REST API 키의 클라이언트 시크릿 | your-kakao-client-secret |
| `KAKAO_REDIRECT_URI` | 카카오 로그인 리다이렉트 URI (프론트 `/auth`) | http://localhost:5173/auth |
| `KAKAO_PAY_KEY` | 카카오페이 Secret key(dev) | your-kakao-pay-secret-key-dev |
| `KAKAO_PAY_CID` | 카카오페이 가맹점 코드 (테스트용) | TC0ONETIME |
