# 重力储能智能调度与控制算法展示平台

这是一个面向会议展示和课题汇报的重力储能智能调度系统原型。系统采用 Vue/Vite 前端 + Python FastAPI 后端，实现从“多场景源荷建模”到“智能优化调度”再到“负荷预测实时控制”的完整展示流程。

## 功能模块

### 1. 多场景重力储能模型

- 输入应用场景、季节、建筑/园区类型、最大功率、初始 SOC。
- 后端生成 24 小时负荷、风电、光伏、电价、净负荷数据。
- 前端展示关键指标、源荷曲线、电价曲线和源荷表格。

### 2. 智能优化调度算法

- 输入 SOC、经济权重、峰谷权重、启停权重、种群规模、迭代次数。
- 后端生成候选调度方案、推荐方案、24 小时充放电计划。
- 前端展示优化前后净负荷、SOC 轨迹、充放电功率和调度明细表。

### 3. 负荷预测实时控制

- 输入预测模型、预测时域、实时偏差和控制模式。
- 后端生成未来 4 小时预测负荷、风光出力、多场景净负荷和下一周期控制建议。
- 前端展示预测区间、多场景曲线和实时控制建议表。

## 技术栈

- 前端：Vue 3 + Vite
- 后端：Python + FastAPI + Uvicorn
- 图表：SVG 自绘图表
- 数据：当前为后端确定性模拟样例数据

## 重要说明

当前版本是可运行展示原型：

- 数据不是现场实测数据。
- 算法不是完整真实 NSGA-II / TCN-VAE。
- 当前后端使用可解释模拟算法，便于演示系统流程和接口结构。
- 后续可在 `server/main.py` 中替换真实数据读取、真实优化算法、真实预测模型和设备控制接口。

## 快速运行

### 1. 安装依赖

```bash
npm install
python3 -m pip install -r requirements.txt
```

### 2. 启动后端

```bash
npm run api
```

后端地址：

```text
http://127.0.0.1:8001
```

### 3. 启动前端

打开另一个终端：

```bash
npm run dev -- --port 5174
```

浏览器访问：

```text
http://127.0.0.1:5174/
```

### 4. 登录账号

```text
账号：cscec-admin
密码：demo123456
```

## Windows 用户

Windows 电脑可以双击：

```text
start-windows.bat
```

脚本会自动检查 Node.js 和 Python，并安装依赖、启动前后端服务。

详细说明见：

```text
README-Windows运行说明.md
```

## macOS 用户

macOS 可以双击：

```text
start-mac.command
```

如果系统提示无法打开，可右键点击后选择“打开”。

## 后端接口

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/health` | GET | 后端健康检查 |
| `/api/bootstrap` | GET | 获取默认账号、表单和选项 |
| `/api/scenario/simulate` | POST | 生成源荷场景曲线 |
| `/api/optimization/run` | POST | 执行优化调度 |
| `/api/control/preview` | POST | 生成预测与实时控制建议 |

## 项目结构

```text
gravity-storage-showcase/
├── public/                 # 静态资源
├── src/assets/             # 中建四局 logo、登录页背景等前端资源
├── server/                 # FastAPI 后端
├── src/                    # Vue 前端源码
├── package.json            # 前端依赖与脚本
├── requirements.txt        # 后端 Python 依赖
├── start-windows.bat       # Windows 启动脚本
├── start-mac.command       # macOS 启动脚本
└── vite.config.js          # Vite 配置与 API 代理
```
