# 重力储能智能调度与控制算法展示平台运行说明

## 1. 项目说明

这是一个“前端 + 后端”的重力储能智能调度展示系统原型。

- 前端：Vue + Vite，负责登录页、模块导航、参数输入、图表和表格展示。
- 后端：Python FastAPI，负责生成场景数据、优化调度结果和实时控制建议。
- 当前数据：后端确定性模拟数据，用于展示流程；不是现场实测数据。
- 当前算法：可解释模拟算法，用于演示；后续可替换为真实 NSGA-II、TCN-VAE 或现场控制接口。

## 2. 目录结构

```text
gravity-storage-showcase/
├── src/                    # 前端源码
├── public/                 # logo 和登录页背景等静态资源
├── server/                 # FastAPI 后端源码
├── package.json            # 前端依赖和启动脚本
├── package-lock.json       # 前端依赖锁定文件
├── requirements.txt        # 后端 Python 依赖
├── vite.config.js          # Vite 配置和 /api 代理
└── README-运行说明.md       # 本说明文件
```

## 3. 环境要求

建议安装：

- Node.js 18 或更高版本
- Python 3.10 或更高版本

## 4. 安装依赖

进入项目目录：

```bash
cd gravity-storage-showcase
```

安装前端依赖：

```bash
npm install
```

安装后端依赖：

```bash
python3 -m pip install -r requirements.txt
```

## 5. 启动后端

打开一个终端窗口，在项目目录执行：

```bash
npm run api
```

后端默认地址：

```text
http://127.0.0.1:8001
```

可测试：

```text
http://127.0.0.1:8001/api/health
```

## 6. 启动前端

再打开一个新的终端窗口，在项目目录执行：

```bash
npm run dev -- --port 5174
```

浏览器打开：

```text
http://127.0.0.1:5174/
```

## 7. 登录信息

演示账号：

```text
账号：siat-admin
密码：demo123456
```

## 8. 演示流程

建议按以下顺序展示：

1. 登录系统。
2. 模块一：选择场景参数，点击“生成场景曲线”。
3. 模块二：设置优化参数，点击“开始优化求解”。
4. 模块三：设置预测控制参数，点击“生成控制建议”。

## 9. 常见问题

### 页面提示“后端未连接”

请确认后端已经启动：

```bash
npm run api
```

### 前端端口被占用

可以换一个端口，例如：

```bash
npm run dev -- --port 5175
```

### 依赖安装失败

请先确认 Node.js 和 Python 已安装，并且网络可以访问 npm 和 PyPI。

## 10. 后续真实算法接入说明

当前核心计算集中在：

```text
server/main.py
```

后续如果接入真实数据或真实算法，主要替换以下函数：

- `simulate_scenario`：替换为真实负荷、风电、光伏、电价数据读取或预测。
- `run_optimization`：替换为真实 NSGA-II、多目标优化或强化学习调度算法。
- `run_control`：替换为真实 TCN-VAE、实时预测模型或设备控制接口。

