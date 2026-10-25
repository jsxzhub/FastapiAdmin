# Project Introduction

This project is a secondary development based on FastapiAdmin, dedicated to building a ready-to-use admin framework. We are committed to being permanently free and open source, and we invite developers from all walks of life to build and share together, polishing a higher-quality enterprise-grade solution.

# Installation

```bash
git clone https://github.com/fastapiadmin/FastapiAdmin.git
```

# Backend

## Configuration

```bash
cd backend/
cp env/.env.example env/.env.dev
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py run --env=dev
```

## Database Migration (use when models change)

```bash
python main.py revision --env=dev
python main.py upgrade --env=dev
```

## Plugin Development

The project uses a **plugin-based architecture**. It is recommended to develop under `backend/app/plugin/`:

### Automatic Route Registration Mechanism

1. Name the controller file `controller.py`
2. Automatic route mapping: `module_xxx` → `/xxx`
3. The system automatically scans all `controller.py` files under `plugin/` and registers their routes

### Development Steps

1. Create `module_yourfeature/` under `backend/app/plugin/`
2. Write `model.py` → `schema.py` → `crud.py` → `service.py` → `controller.py` in order
3. Routes are registered automatically, no manual configuration required

### Backend Conventions

- **Date serialization**: Use Pydantic `PlainSerializer(..., when_used='json')`; use `mode='python'` for ORM and `mode='json'` for JSON/Redis
- **Unified response**: Use `SuccessResponse` and `jsonable_encoder`
- **Permission control**: All API endpoints must add `AuthPermission` permission control
- **Logging**: Use `OperationLogRoute` to record key operations

# Frontend

## Configuration

```bash
cd frontend/web
cp .env.development.example .env.development
```

## Install Dependencies

```bash
pnpm install
```

## Run

```bash
pnpm run dev
```

## Other Scripts

```bash
pnpm build            # Production build
pnpm type-check       # TypeScript check
pnpm lint             # ESLint + Prettier + Stylelint
pnpm clean:cache      # Clean cache
```

## Adding a New Page

- Create the corresponding API file under `src/api/`
- Create the page component under `src/views/`
- Register the route (static or dynamic routes) + configure the backend menu
- Keep the path and name consistent across all three

# Mobile

## Configuration

```bash
cd frontend/app
cp .env.development.example .env.development
```

## Install Dependencies

```bash
pnpm install
```

## Run

### H5

```bash
pnpm run dev:h5 --host
```

### WeChat Mini Program

```bash
# Start the WeChat Mini Program dev server
pnpm run dev:mp-weixin

# Import the project directory into WeChat DevTools: dist/dev/mp-weixin
```

### Other Platforms

```bash
# Start the Alipay Mini Program dev server
pnpm run dev:mp-alipay

# Start the Baidu Mini Program dev server
pnpm run dev:mp-baidu

# Start the ByteDance (Toutiao) Mini Program dev server
pnpm run dev:mp-toutiao

# Start the QQ Mini Program dev server
pnpm run dev:mp-qq
```

## Build & Release

### H5 Build

```
pnpm run build:h5

# The build output is in the dist/build/h5 directory
```

### WeChat Mini Program Build

```
pnpm run build:mp-weixin

# The build output is in the dist/build/mp-weixin directory
```

### Other Platform Builds

```
# Build the Alipay Mini Program
pnpm run build:mp-alipay

# Build the Baidu Mini Program
pnpm run build:mp-baidu

# Build the ByteDance (Toutiao) Mini Program
pnpm run build:mp-toutiao

# Build the QQ Mini Program
pnpm run build:mp-qq
```

# Community & Sponsorship

Scan the WeChat QR code below and add us on WeChat with the note "FastapiAdmin" to join the group.

<!-- Use an HTML table for side-by-side display -->
<table>
  <tr>
    <!-- First image: personal QR code -->
    <td style="text-align:center; padding:10px;">
 <img src="https://github.com/user-attachments/assets/73466c31-31f6-4c25-af49-47506acb5043" alt="Personal QR Code" width="300" />
      <br>
 </td>
    <!-- Second image: personal payment QR code -->
 <td style="text-align:center; padding:10px;">
 <img src="https://github.com/user-attachments/assets/51fb80d0-09cf-4cfc-837b-42e43cbeb70b" alt="Personal Payment QR Code" width="300" />
      <br>
 </td>
  </tr>
</table>