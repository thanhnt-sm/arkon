Viewed docker-compose.yml:1-171
Listed directory arkon
Viewed .env.docker:1-46
Searched for "DEFAULT_ADMIN_EMAIL"
Viewed HOW_TO_RUN.md:1-253

Dưới đây là thông tin đăng nhập mặc định và chuỗi kết nối (connection string) vào cơ sở dữ liệu PostgreSQL dựa trên cấu hình Docker (`docker-compose.yml` và `.env.docker`) trong dự án của bạn:

### 1. Thông tin đăng nhập mặc định (Default Admin Credentials)
Khi hệ thống khởi chạy lần đầu tiên, tài khoản Admin mặc định sẽ được tự động khởi tạo dựa trên cấu hình trong file `.env.docker`:
*   **Email (Tên đăng nhập):** `admin@arkon.local`
*   **Mật khẩu:** `admin123`

---

### 2. Chuỗi kết nối PostgreSQL (Connection String)

Tùy thuộc vào việc bạn kết nối từ bên trong mạng Docker hay từ máy chủ (Host) cá nhân của bạn, chuỗi kết nối sẽ có dạng như sau:

#### A. Kết nối từ bên trong mạng lưới Docker (giữa các container)
*   **Dành cho Backend (SQLAlchemy Asyncpg):** 
    ```
    postgresql+asyncpg://arkon:arkon_secret@postgres:5432/arkon
    ```
*   **Chuỗi kết nối tiêu chuẩn (Sync/CLI):**
    ```
    postgresql://arkon:arkon_secret@postgres:5432/arkon
    ```

#### B. Kết nối từ Máy Host của bạn (DBeaver, TablePlus, pgAdmin...)
Mặc định, cổng `5432` của dịch vụ PostgreSQL trong file `docker-compose.yml` đang bị comment (dòng 42-43):
```yaml
    # ports:
    #   - "5432:5432"
```

Để kết nối được từ máy ngoài vào database:
1. Bạn hãy mở comment phần cấu hình ports này trong file `docker-compose.yml`:
   ```yaml
    ports:
      - "5432:5432"
   ```
2. Khởi động lại container postgres:
   ```bash
   docker compose up -d postgres
   ```
3. Chuỗi kết nối từ máy Host lúc này sẽ là:
   ```
   postgresql://arkon:arkon_secret@localhost:5432/arkon
   ```

---

### Tóm tắt công việc đã thực hiện
* Tìm kiếm và kiểm tra cấu hình dịch vụ cơ sở dữ liệu và frontend trong file [docker-compose.yml](file:///Volumes/Data/101.AI/GitHub/arkon/docker-compose.yml).
* Xác minh và trích xuất các biến môi trường mặc định, tài khoản admin và chuỗi kết nối trong file [.env.docker](file:///Volumes/Data/101.AI/GitHub/arkon/.env.docker).
* Tra cứu tài liệu chạy thử nghiệm tại [HOW_TO_RUN.md](file:///Volumes/Data/101.AI/GitHub/arkon/docs/HOW_TO_RUN.md) để đảm bảo tính chuẩn xác của các thông tin trên.