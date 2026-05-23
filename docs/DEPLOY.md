# Deploy Script — Hướng dẫn sử dụng

Script `deploy.sh` ở thư mục gốc của dự án giúp bạn build và chạy toàn bộ Arkon bằng Docker Compose chỉ với một lệnh.

---

## Yêu cầu

| Công cụ | Phiên bản tối thiểu | Kiểm tra |
|---------|---------------------|----------|
| Docker Desktop | 24+ | `docker --version` |
| docker compose (plugin) | v2+ | `docker compose version` |

> **Lưu ý macOS:** Docker Desktop phải đang chạy (icon trên thanh menu). Script sẽ báo lỗi nếu daemon chưa khởi động.

---

## Lần đầu chạy

```bash
# 1. Clone hoặc vào thư mục dự án
cd /path/to/arkon

# 2. Tạo file cấu hình môi trường
cp .env.docker.example .env.docker

# 3. (Tuỳ chọn nhưng khuyến nghị) Đổi SECRET_KEY thành chuỗi ngẫu nhiên
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Paste kết quả vào dòng SECRET_KEY= trong .env.docker

# 4. Chạy deploy
./deploy.sh
```

Script sẽ tự động:
1. Kiểm tra Docker đang chạy
2. Validate `.env.docker`
3. Build image backend (`arkon-backend`) và frontend (`arkon-frontend`)
4. Khởi động tất cả 8 container
5. Chờ health check pass
6. In URL truy cập

---

## Tất cả các lệnh

### Lệnh cơ bản

```bash
./deploy.sh                # Build + start (dùng cache Docker)
./deploy.sh --no-cache     # Build lại từ đầu, không dùng cache
./deploy.sh --pull         # Kéo base image mới nhất rồi mới build
./deploy.sh --logs         # Sau khi start, hiển thị logs (Ctrl+C để thoát)
```

### Quản lý container

```bash
./deploy.sh --status       # Xem trạng thái các container
./deploy.sh --restart      # Stop, rebuild, start lại (GIỮ dữ liệu)
./deploy.sh --down         # Stop và xoá container (GIỮ volumes/dữ liệu)
./deploy.sh --reset        # Stop + XOÁ HẾT dữ liệu (volumes) + rebuild
```

### Kết hợp nhiều flag

```bash
./deploy.sh --no-cache --logs        # Build sạch + xem logs ngay
./deploy.sh --restart --no-cache     # Restart + build sạch
./deploy.sh --pull --no-cache        # Kéo base image mới + build sạch
```

---

## Workflow phổ biến

### Test sau khi sửa code

```bash
./deploy.sh --restart
```

Đây là lệnh dùng nhiều nhất khi phát triển: stop container cũ, build lại với code mới, start lại.

### Build hoàn toàn từ đầu (debug build lỗi)

```bash
./deploy.sh --no-cache --logs
```

Khi bạn nghi ngờ Docker cache đang giữ bản cũ, hoặc sau khi thay đổi `pyproject.toml` / `package.json`.

### Xem logs một service cụ thể

```bash
docker logs arkon_api -f          # API backend
docker logs arkon_worker -f       # Wiki compilation worker
docker logs arkon_worker_skills -f # Skills worker
docker logs arkon_frontend -f     # Next.js frontend
```

### Reset hoàn toàn (môi trường sạch)

```bash
./deploy.sh --reset
```

> ⚠️ Lệnh này **XOÁ TOÀN BỘ** database PostgreSQL, Redis cache, và file MinIO.
> Chỉ dùng khi cần test từ đầu hoặc schema migration bị lỗi.

---

## URL sau khi deploy

| Dịch vụ | URL |
|---------|-----|
| Admin UI (Frontend) | http://localhost:3119 |
| Backend API | http://localhost:5055 |
| API Swagger Docs | http://localhost:5055/docs |
| Health check | http://localhost:5055/health |
| MinIO Console | http://localhost:9003 |

---

## Cấu hình `.env.docker`

| Biến | Mặc định | Ghi chú |
|------|---------|---------|
| `SECRET_KEY` | *(ví dụ, cần đổi)* | **Bắt buộc đổi** trước khi dùng thật |
| `DEFAULT_ADMIN_EMAIL` | `admin@arkon.local` | Tài khoản admin lần đầu |
| `DEFAULT_ADMIN_PASSWORD` | `admin123` | Đổi sau lần đăng nhập đầu |
| `POSTGRES_PASSWORD` | `arkon_secret` | Password PostgreSQL |
| `MINIO_SECRET_KEY` | `minioadmin123` | Password MinIO |
| `REDIS_PASSWORD` | `arkon_secret` | Password Redis |
| `NEXT_PUBLIC_API_URL` | `http://localhost:5055` | URL API mà browser dùng |

Để deploy trên server với domain thật, đổi `NEXT_PUBLIC_API_URL` thành URL công khai của API (ví dụ `https://arkon.yourcompany.com`).

---

## Xử lý lỗi thường gặp

### `Docker daemon is not running`

Mở Docker Desktop và chờ icon trên thanh menu chuyển sang trạng thái bình thường, rồi chạy lại.

### Build lỗi `no space left on device`

```bash
docker system prune -f          # Xoá cache, image không dùng
docker volume prune -f          # Xoá volume orphan
./deploy.sh --no-cache
```

### Container `arkon_api` không healthy, xem lỗi migration

```bash
docker logs arkon_api | grep -A5 "ERROR\|Error\|migration"
```

Nếu lỗi do migration schema, reset hoàn toàn:
```bash
./deploy.sh --reset
```

### `port is already allocated`

Có tiến trình khác đang dùng port 5055 hoặc 3119:

```bash
# macOS/Linux — tìm process dùng port 5055
lsof -i :5055
lsof -i :3119
# Kill process hoặc đổi port trong .env.docker
```

### Stuck ở 55% khi xử lý file

Worker MRP đang chờ LLM hoặc LLM connection bị lỗi:
```bash
docker logs arkon_worker -f --tail 50
```

Đảm bảo đã cấu hình LLM trong Settings (Admin UI → Settings → LLM Model).

---

## Kiến trúc container

```
Browser → arkon_frontend (3119) → arkon_api (5055)
                                       │
                       ┌───────────────┼──────────────────┐
                       ▼               ▼                  ▼
               arkon_postgres    arkon_redis        arkon_minio
                (PostgreSQL)      (Redis)            (MinIO S3)
                                       │
                       ┌───────────────┴──────────┐
                       ▼                          ▼
               arkon_worker              arkon_worker_skills
            (wiki compilation)          (skill processing)
```

Tất cả container trong mạng `arkon_internal` (isolated). Chỉ `api`, `frontend`, và `minio` expose port ra ngoài.
