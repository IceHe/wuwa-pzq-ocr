# 鸣潮声骸重构结果 OCR 记录器

一个面向《鸣潮》声骸重构结果界面的浏览器本地识别与记录页面。当前仓库已经拆成 `frontend/` 和 `backend/` 两部分，OCR 仍然在浏览器内执行，后端负责保存识别记录、上传截图和查询历史。

## 目录结构

- `frontend/`
  - 页面模板与静态资源
  - 浏览器端 OCR 与结果展示逻辑
- `backend/`
  - Flask 服务
  - 提供页面、识别记录 API、截图上传 API
  - PostgreSQL 入库与历史记录查询
- `images/`
  - 已识别截图的落盘目录
- `docs/`
  - 后端 OCR 方案文档，供未来恢复服务端实现时参考

## 当前实现

- 页面当前以游戏截图为主要输入，支持本地预览、OCR 结果展示和历史记录查看。
- 前端通过 `Tesseract.js` 在浏览器中加载 WASM 运行时处理图片内容。
- Flask 不参与前端 OCR 流程，只负责页面、记录和图片存储接口。
- 首次打开并开始识别时，浏览器会自行下载前端运行时资源，后续会复用浏览器缓存。
- 当前识别结果会提交到后端并写入 PostgreSQL 的 `wuwa_rebuild_log`。
- 首次保存成功且不是重复记录时，前端会继续上传原始截图，后端保存到仓库根目录 `images/`。
- 历史记录支持分页查询、详情回填；后端保留软删除接口，但当前页面未提供删除按钮。
- 仓库内仍保留一份旧的后端 OCR 设计备忘，供后续参考，不属于当前主流程。

## 历史设计备忘

如果后续需要参考旧的服务端识别设计，请查看：

- `docs/backend_ocr_design.md`

## 安装

推荐使用 Python 3.12 和 PostgreSQL。

```bash
./scripts/bootstrap.sh
```

环境变量默认从仓库根目录 `.env` 读取。当前数据库连接写法为：

```bash
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<database>
```

初始化数据库表：

```bash
./scripts/init_db.sh
```

依赖说明：

- `Flask` 用于提供页面与 API
- `psycopg[binary]` 用于连接 PostgreSQL

## Web 界面

```bash
./scripts/start_web.sh 8012
```

默认地址是 `http://127.0.0.1:8012`。

- 支持点击选择图片
- 支持直接把截图粘贴到页面
- 支持拖拽图片到上传区
- 前端会展示原图预览、左右词条表、状态标签和原始 JSON
- 图片不会先上传到后端，前端 OCR 逻辑始终在浏览器内执行
- 识别成功后，页面会把结果提交到后端并写入 PostgreSQL 的 `wuwa_rebuild_log`
- 如果不是 1 小时内的重复记录，页面会继续上传原始截图并保存到 `images/`
- 页面支持填写上传者昵称、邮箱、微信、QQ，随记录一起保存
- 页面支持查看最近历史记录、分页跳转和回填查看详情
- 原始 JSON 默认折叠，预览图支持点击放大，支持点击空白处、图片本身或按 `Esc` 关闭
- 如果 8012 也被占用，可以执行 `./scripts/start_web.sh 8080` 或 `PORT=8080 ./scripts/start_web.sh`
- 默认以单进程模式启动，避免 Flask debug reloader 额外占用端口；如需调试可执行 `DEBUG=1 ./scripts/start_web.sh`

记录去重规则：

- `user_id`
- 原词条 5 项 bitmap
- 新词条 5 项 bitmap
- 锁定位图
- 仅在最近 1 小时内查重

命中重复时，后端直接返回已有记录 ID，不会新增记录，也不会再次上传图片。

停止服务：

```bash
Ctrl + C
```

## API 概览

页面同时支持根路径和 `/browser-ocr/` 前缀两套入口，便于直接启动或挂到 nginx 子路径。

- `GET /api/health`
  - 健康检查
- `POST /api/rebuild_log`
  - 保存识别结果和上传者信息
- `POST /api/rebuild_image`
  - 关联上传原始截图，表单字段包含 `image`、`log_id`，可选 `nickname`
- `GET /api/rebuild_logs?limit=20&offset=0`
  - 分页获取历史记录
- `GET /api/rebuild_log/<id>`
  - 获取单条记录详情和原始 JSON
- `DELETE /api/rebuild_log/<id>`
  - 软删除单条记录

数据库表结构定义见：

- `backend/db.sql`

字段重点：

- `source_image`
  - OCR 识别时的原始文件名
- `uploaded_image`
  - 后端落盘到 `images/` 后的文件名
- `raw_json`
  - OCR 原始结果 JSON
- `uploader_*`
  - 上传者附加信息
- `request_ip`
  - 后端从请求头或连接信息解析出的来源 IP

## 测试

```bash
.venv312/bin/python -m unittest discover -s tests
```
