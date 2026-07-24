# NutriScreen 迁移与正式部署

本项目可部署在没有公网 IP 的 Linux 服务器。Cloudflare Tunnel 由服务器主动连接 Cloudflare，用户通过 `https://nutriscreen.cn` 访问服务。

## 目标结构

```text
手机 / Pad → Cloudflare → Named Tunnel → Nginx
                                      ├─ /     Vue 构建产物
                                      └─ /api/ FastAPI (127.0.0.1:8000)
```

## 1. 迁移前：导出和复制

在源服务器停止后端后，将整个项目复制到新服务器的 `/srv/NutriProject`：

- 项目源代码（不含 `node_modules/`、`dist/`）；
- `nutri_back/history.db`、`history_reports/`、`sessions/`；
- `nutri_back/scales/outputs/`（若需保留尚未归档报告）；
- `nutri_back/classify_model/passing/face_landmarker.task`；
- 模型权重放在 `nutri_back/classify_model/weight/best_checkpoint.pth`；
- 后端密钥保存在 `deploy/nutri-backend.env`（仅服务器保存，不能提交 Git）。

不要复制 AutoDL 的 `cert.pem` 或 Tunnel JSON 凭据到正式服务器；新服务器应创建新的 Named Tunnel。

## 2. 项目目录（不创建系统用户）

以下示例不创建系统用户，将代码、模型、环境变量与 Tunnel 配置都保留在同一项目目录。若你希望使用其他目录，只需在所有配置文件中一致替换 `/srv/NutriProject`。

```bash
mkdir -p /srv/NutriProject/deploy/cloudflared
chmod 700 /srv/NutriProject/deploy/cloudflared
```

## 3. 建立 Conda 环境

在已安装 Miniconda 的新服务器：

```bash
conda env create -f /srv/NutriProject/deploy/environment.nutri_serve.yml
```

若新服务器有 NVIDIA GPU，先安装与 PyTorch CUDA 12.8 兼容的驱动；无 GPU 时后端会自动使用 CPU，但推理较慢。

## 4. 构建前端

创建 `/srv/NutriProject/nutri_front/.env.production`：

```env
VITE_API_BASE=/api
```

再构建：

```bash
cd /srv/NutriProject/nutri_front
npm ci
npm run build
```

## 5. 配置后端和 Nginx

### 5.1 配置后端密钥和模型路径

复制模板，编辑其中的 Qwen 密钥和模型路径：

```bash
cp /srv/NutriProject/deploy/nutri-backend.env.example /srv/NutriProject/deploy/nutri-backend.env
chmod 600 /srv/NutriProject/deploy/nutri-backend.env
vi /srv/NutriProject/deploy/nutri-backend.env
```

至少确认以下两项：

```env
MODEL_CHECKPOINT_PATH=/srv/NutriProject/nutri_back/classify_model/weight/best_checkpoint.pth
DASHSCOPE_API_KEY=你的真实密钥
```

确认模型文件存在：

```bash
ls -lh /srv/NutriProject/nutri_back/classify_model/weight/best_checkpoint.pth
```

### 5.2 注册后端 systemd 服务

先确认 Conda Python 的实际路径；若不是 `/root/miniconda3/envs/nutri_serve/bin/python`，编辑服务文件中的 `ExecStart`：

```bash
which conda
cp /srv/NutriProject/deploy/systemd/nutriscreen-backend.service /etc/systemd/system/nutriscreen-backend.service
vi /etc/systemd/system/nutriscreen-backend.service
```

此服务默认以 root 运行，后端仅监听 `127.0.0.1:8000`，不会直接开放给公网。

### 5.3 配置和启用 Nginx

安装 Nginx 后复制项目模板并启用站点：

```bash
apt update
apt install -y nginx
cp /srv/NutriProject/deploy/nginx/nutriscreen.conf /etc/nginx/sites-available/nutriscreen.conf
ln -sf /etc/nginx/sites-available/nutriscreen.conf /etc/nginx/sites-enabled/nutriscreen.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx
```

此 Nginx 配置将 `nutriscreen.cn/` 提供为前端页面，将 `nutriscreen.cn/api/` 转发到本机 FastAPI。Cloudflare Tunnel 只需访问本机 `127.0.0.1:80`。

## 6. 创建新的生产 Tunnel

不要复制 AutoDL 的 `cert.pem` 或 JSON 凭据。新服务器应重新创建 Tunnel，以下以 `nutriscreen-prod` 为例。

### 6.1 安装并登录 cloudflared

安装适用于新服务器架构的官方 cloudflared 后，执行：

```bash
cloudflared tunnel login
```

终端会给出 Cloudflare 授权链接。用本机浏览器打开、登录拥有 `nutriscreen.cn` 的 Cloudflare 账号、选择该域名并点击授权；成功后回到终端。

### 6.2 创建 Tunnel 和项目内配置

```bash
cloudflared tunnel create nutriscreen-prod
```

记下命令输出的 UUID。将生成的 `<UUID>.json` 放入 `/srv/NutriProject/deploy/cloudflared/` 并限制权限：

```bash
cp /root/.cloudflared/<UUID>.json /srv/NutriProject/deploy/cloudflared/<UUID>.json
chmod 600 /srv/NutriProject/deploy/cloudflared/<UUID>.json
cp /srv/NutriProject/deploy/cloudflared/nutriscreen.yml.example /srv/NutriProject/deploy/cloudflared/nutriscreen.yml
vi /srv/NutriProject/deploy/cloudflared/nutriscreen.yml
```

把配置中的 `<NEW_TUNNEL_UUID>` 两处替换为实际 UUID。随后在 Cloudflare 创建 DNS 路由：

```bash
cloudflared tunnel route dns nutriscreen-prod nutriscreen.cn
```

若该命令提示 DNS 记录已经存在，先不要删除旧记录；在 Cloudflare 控制台的 DNS 页面将 `nutriscreen.cn` 的 CNAME 目标切换到新 Tunnel UUID 对应的 `cfargotunnel.com` 地址。此时 AutoDL 仍可继续提供服务，直到新服务器验证通过。

### 6.3 注册 Tunnel systemd 服务

确认 `cloudflared` 的安装路径（通常是 `/usr/local/bin/cloudflared`），必要时编辑服务文件中的 `ExecStart`：

```bash
which cloudflared
cp /srv/NutriProject/deploy/systemd/nutriscreen-cloudflared.service /etc/systemd/system/nutriscreen-cloudflared.service
vi /etc/systemd/system/nutriscreen-cloudflared.service
```

## 7. 开机自启与验证

### 7.1 启动顺序

```bash
systemctl daemon-reload
systemctl enable --now nutriscreen-backend
systemctl status nutriscreen-backend --no-pager
curl http://127.0.0.1:8000/health

systemctl enable --now nutriscreen-cloudflared
systemctl status nutriscreen-cloudflared --no-pager
```

后端健康检查必须先返回 JSON，再启动和验证 Tunnel。

### 7.2 查看故障日志

```bash
journalctl -u nutriscreen-backend -n 100 --no-pager
journalctl -u nutriscreen-cloudflared -n 100 --no-pager
journalctl -u nutriscreen-backend -f
```

### 7.3 外网验证与切换完成

依次验证：

1. `curl http://127.0.0.1:8000/health` 返回 JSON；
2. 浏览器访问 `https://nutriscreen.cn`，前端页面正常加载；
3. 手机/Pad 上传图片、生成报告、保存共享历史；
4. 刷新后确认同一 Pad 草稿可恢复，其他 Pad 草稿不串数据；
5. Cloudflare 控制台确认 Tunnel 状态为 Healthy。

以上均通过后，再停止 AutoDL 上的 FastAPI、Vite 和旧 Named Tunnel。
## 安全和备份

- 为 `nutriscreen.cn` 配置 Cloudflare Access，仅允许授权人员访问；
- 每日备份 `history.db`、`history_reports/`、`sessions/` 和模型权重；
- SQLite 备份前先停止后端，或使用 SQLite 的在线备份机制；
- 正式环境不要运行 Vite 开发服务，也不要继续使用临时 `trycloudflare.com` Tunnel。

