# selfEval

> version 1.5.0-rev24  
> Copyright (C) 2025 [Yile Wang](mailto:bluewindde@163.com)  
> 使用 [GNU 通用公共许可证，第三版以上](https://www.gnu.org/licenses/gpl-3.0.html) 发布，不含任何担保。  

本项目是对信息学竞赛程序进行本地测试的工具。

建议搭配 VSCode 使用。

## 前言

项目目前仍在开发中，请谨慎使用，文档还在咕咕咕，欢迎持续关注。

rev22 及以前的版本均没有上传 GitHub。

## 部署指南

环境要求：Linux/WSL。

本项目使用 Python 和 C++ 混合开发，在如下环境进行开发和测试：

- 物理机
  - Ubuntu 20.04.6 LTS
  - Python 3.13.7
  - C++ 17 (gcc 9.4.0)
  - libseccomp-dev 2.5.1
- WSL2
  - Windows 11 25H2
  - Ubuntu 24.04 LTS
  - Python 3.12.3
  - C++ 17 (gcc 13.3.0)
  - rev18 及以上的构建版本未在该设备上测试。

### 搭建 Python 环境

Python 版本需要不低于 3.12。

使用如下命令创建 venv：

```sh
python3 -m venv .venv
```

然后安装依赖：

```sh
pip3 install -r requirements.txt
```

这样就准备好了 Python 环境。

### 编译沙箱

从 rev22 开始，沙箱基于 seccomp-bpf，你可能需要安装软件包 libseccomp-dev，以获取头文件 linux/seccomp.h。

在 lib 目录下执行命令 make 即可使用 gcc 编译沙箱，其它编译器请自行研究。

注：rev22 之前沙箱基于 ptrace，特定情况下效率较低，更换底层后交互题测试效率可以提升约 110%。

### 在 Windows/WSL 中使用

数据配置向导使用 Qt6 作为图形框架，如果无法打开 PySide6 的 GUI 界面，请尝试安装 xcb 系列软件包，例如 libxcb-cursor，了解 [使用 WSL 运行 Linux GUI 应用](https://learn.microsoft.com/zh-cn/windows/wsl/tutorials/gui-apps)。
