# Windows 运行说明

## 1. 最简单运行方式

解压压缩包后，进入：

```text
gravity-storage-showcase
```

双击：

```text
start-windows.bat
```

脚本会自动执行：

1. 检查 Node.js。
2. 检查 Python。
3. 安装前端依赖。
4. 创建 Python 虚拟环境。
5. 安装后端依赖。
6. 启动后端服务。
7. 启动前端服务。
8. 自动打开浏览器。

浏览器地址：

```text
http://127.0.0.1:5174/
```

登录账号：

```text
账号：siat-admin
密码：demo123456
```

## 2. 老师电脑需要具备的环境

Windows 电脑需要提前安装：

- Node.js LTS：https://nodejs.org/
- Python 3.10 或更高版本：https://www.python.org/downloads/

安装 Python 时建议勾选：

```text
Add Python to PATH
```

## 3. 为什么不能直接带 Mac 依赖给 Windows

前端依赖目录 `node_modules` 和 Python 虚拟环境 `.venv` 中可能包含系统相关的二进制文件。

Mac 上安装出来的依赖不能保证在 Windows 上直接运行，所以发送给 Windows 老师时，正确做法是发送源码和启动脚本，让脚本在 Windows 本机自动安装依赖。

## 4. 关闭系统

启动后会弹出两个命令行窗口：

- Gravity Storage Backend
- Gravity Storage Frontend

关闭这两个窗口即可停止系统。

