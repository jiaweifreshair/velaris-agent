# Build Instructions

## 前提条件
- **Python 构建工具**: `uv` + `hatchling`
- **Python 版本**: 建议 `3.11+`；本仓库测试入口会优先选择与已安装二进制依赖架构一致的解释器
- **前端工具链**: `Node.js 20` + `npm`
- **可选环境变量**:
  - `VELARIS_TEST_POSTGRES_DSN`：启用 PostgreSQL 集成测试时必需
- **系统要求**:
  - macOS / Linux
  - 可写工作区
  - 若执行前端安装，需要可访问 npm registry

## 构建步骤

### 1. 安装 Python 依赖
```bash
uv sync --extra dev
```

### 2. 安装前端依赖
```bash
cd frontend/terminal
npm ci
cd ../..
```

### 3. 构建 Python 分发产物
```bash
uv build
```

### 4. 校验前端 TypeScript
```bash
cd frontend/terminal
npx tsc --noEmit
cd ../..
```

## 本次实测结果
- `uv build`：成功
- `npx tsc --noEmit`：成功
- 生成产物：
  - `dist/velaris_agent-0.1.0.tar.gz`
  - `dist/velaris_agent-0.1.0-py3-none-any.whl`

## 成功判定
- `dist/` 下生成 `.tar.gz` 与 `.whl`
- `frontend/terminal` TypeScript 无报错退出
- 无需额外手工补丁即可完成构建与前端类型校验

## 常见问题排查

### 1. Python 扩展架构不匹配
- 现象：`pydantic_core` 等二进制扩展提示 `arm64/x86_64` 不兼容
- 处理：优先通过 `./scripts/run_pytest.sh` 执行测试；该脚本会自动选择兼容解释器

### 2. 前端依赖安装失败
- 现象：`npm ci` 失败或锁文件不匹配
- 处理：确认 `frontend/terminal/package-lock.json` 未被污染，并使用 Node 20

### 3. PostgreSQL 集成无法启动
- 现象：带 PostgreSQL 的测试被 skip 或连接失败
- 处理：先设置 `VELARIS_TEST_POSTGRES_DSN`，再执行集成测试指令
