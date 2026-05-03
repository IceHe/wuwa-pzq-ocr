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
- 历史记录支持分页查询和详情回填。
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
npm run start
```

默认地址是 `http://127.0.0.1:8012`。

- 支持点击选择图片
- 支持直接把截图粘贴到页面
- 支持拖拽图片到上传区
- 前端会展示原图预览、左右词条表、状态标签和原始 JSON
- 图片不会先上传到后端，前端 OCR 逻辑始终在浏览器内执行
- 识别成功后，页面会把结果提交到后端并写入 PostgreSQL 的 `wuwa_rebuild_log`
- 如果不是 1 小时内的重复记录，页面会继续上传原始截图并保存到 `images/`
- 如果识别结果未通过质量检查，页面不会写入 `wuwa_rebuild_log`，而是把原图、raw OCR 和失败原因保存到 `failed-samples/`
- 页面支持填写上传者昵称、邮箱、微信、QQ，随记录一起保存
- 页面支持查看最近历史记录、分页跳转和回填查看详情
- 原始 JSON 默认折叠，预览图支持点击放大，支持点击空白处、图片本身或按 `Esc` 关闭
- 如果 8012 也被占用，可以执行 `./scripts/start_web.sh 8080` 或 `PORT=8080 ./scripts/start_web.sh`
- 默认以单进程模式启动，避免 Flask debug reloader 额外占用端口；如需调试可执行 `DEBUG=1 ./scripts/start_web.sh`

## 常用命令

仓库提供 `package.json` 作为统一命令入口，不需要安装 Node 依赖；只要求系统有 `node` 和 `npm`。

```bash
npm run start
npm run test
npm run db:backup
npm run service:restart
npm run health
```

常用脚本：

- `npm run start`
  - 本地以前台方式启动 Flask 服务，端口 `8012`
- `npm run test`
  - 执行前端 JS 语法检查和 Python 单元测试
- `npm run db:backup`
  - 备份 PostgreSQL 数据库到 `backups/db/`
- `npm run service:install`
  - 安装/更新 systemd 服务
- `npm run service:restart`
  - 重启线上 systemd 服务
- `npm run service:status`
  - 查看线上 systemd 服务状态
- `npm run service:logs`
  - 查看线上 systemd 服务最近日志
- `npm run deploy`
  - 重启线上服务并执行健康检查

## 服务部署

线上 systemd 服务名固定为：

```text
wuwa-ocr.service
```

安装或更新 systemd unit：

```bash
npm run service:install
```

重启服务：

```bash
npm run service:restart
```

检查服务状态：

```bash
npm run service:status
```

健康检查：

```bash
npm run health
```

当前服务监听 `0.0.0.0:8012`，本机健康检查地址是 `http://127.0.0.1:8012/api/health`。如果通过 nginx 子路径访问，也可以检查 `http://127.0.0.1:8012/browser-ocr/api/health`。

## 数据备份

在标注、调参或批量处理前，先备份线上 PostgreSQL 数据库：

```bash
./scripts/backup_db.sh
```

备份文件会写入 `backups/db/wuwa_ocr_<timestamp>.sql`。`backups/` 已加入 `.gitignore`，避免把包含用户信息、IP 和原始 JSON 的 SQL 备份提交到仓库。

## 标注后台

标注后台入口：

```text
https://pzq.icehe.life/annotation
```

本地启动后也可以访问：

```text
http://127.0.0.1:8012/annotation
```

启用前需要配置口令：

```bash
ANNOTATION_PASSWORD=<your-password>
```

标注后台读取 3 组样本：

- `samples-20260503/`
- `images/`
- `samples/`

标签保存到独立文件 `annotations/rebuild_labels.json`，不会写入线上用户数据表 `public.wuwa_rebuild_log`。训练、回归和调参过程也应只读取线上表或图片文件，不应更新、删除或复用 `wuwa_rebuild_log` 保存中间结果。

识别失败样本会保存到 `failed-samples/`，并在标注后台中显示为“失败待标注”样本组。该目录已加入 `.gitignore`，用于持续收集失败截图、raw OCR 和质量检查错误；人工标注后，标签仍统一写入 `annotations/rebuild_labels.json`。

线上结果保存前有质量闸门：

- 必须识别到有效特征码
- 左右各 5 行都必须是已知词条
- 数值必须能匹配项目内档位表
- 有置信度字段时，过低置信度会阻止保存

这不是在线训练 Tesseract 模型，而是“失败样本 -> 标注 -> 回归 -> 修正规则”的闭环。当前浏览器 OCR 架构下，新增失败样本主要用于扩充别名、定位、预处理和质量规则。

标注页内的“浏览器回归”会在当前浏览器中批量调用同一套前端 OCR，与已保存标签比对，并把报告写入 `reports/ocr-regression/`。`reports/` 已加入 `.gitignore`。

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

如果是 systemd 方式运行，停止服务：

```bash
systemctl stop wuwa-ocr.service
```

## API 概览

页面同时支持根路径和 `/browser-ocr/` 前缀两套入口，便于直接启动或挂到 nginx 子路径。

- `GET /api/health`
  - 健康检查
- `POST /api/rebuild_log`
  - 保存识别结果和上传者信息
- `POST /api/rebuild_image`
  - 关联上传原始截图，表单字段包含 `image`、`log_id`，可选 `nickname`
- `POST /api/ocr_failure`
  - 保存识别失败样本，表单字段包含 `image`、`payload`、`quality`，可选 `nickname`
- `GET /api/rebuild_logs?limit=20&offset=0`
  - 分页获取历史记录
- `GET /api/rebuild_log/<id>`
  - 获取单条记录详情和原始 JSON

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
npm run test
```

等价于：

```bash
node --check frontend/static/app.js
node --check frontend/static/annotation.js
node --check frontend/static/recognizer.js
.venv312/bin/python -m unittest discover -s tests
```
