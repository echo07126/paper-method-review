# 第三方组件与许可声明（THIRD PARTY NOTICES）

本项目「论文方法论审查助手」以**未修改**方式使用下列第三方组件。版本与许可证取自各组件随包发布的元数据。
完整的许可文本随各组件的包文件（Python：`*.dist-info/`；前端：`node_modules/<pkg>/LICENSE`）一并分发。

## 后端运行时（backend/requirements.txt）

| 组件 | 版本 | 许可证 |
| --- | --- | --- |
| fastapi | 0.141.1 | MIT |
| uvicorn[standard] | 0.53.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| python-docx | 1.2.0 | MIT |
| python-multipart | 0.0.32 | Apache-2.0 |
| httpx | 0.28.1 | BSD-3-Clause |
| starlette（传递依赖） | 1.6.0 | BSD-3-Clause |
| anyio（传递依赖） | 4.15.1 | MIT |
| lxml（传递依赖） | 6.1.3 | BSD-3-Clause |

## 前端（frontend/package.json）

| 组件 | 版本 | 许可证 |
| --- | --- | --- |
| vue | 3.5.42 | MIT |
| vue-router | 4.6.4 | MIT |
| pinia | 2.3.1 | MIT |
| axios | 1.20.0 | MIT |
| vite | 7.3.6 | MIT |
| typescript | 5.9.3 | Apache-2.0 |
| vue-tsc | 3.3.11 | MIT |
| @vitejs/plugin-vue | 6.0.9 | MIT |
| @types/node | 22.20.2 | MIT |

## 容器基础镜像

| 镜像 | 用途 | 许可说明 |
| --- | --- | --- |
| `python:3.12-slim` | 后端运行 | Python 为 PSF License；Debian 基础系统组件各自许可 |
| `node:22-alpine` | 前端构建阶段（不进入运行镜像） | Node.js 为 MIT；Alpine 组件各自许可 |
| `nginxinc/nginx-unprivileged:alpine` | 前端运行 | nginx 为 BSD-2-Clause |

## 模型服务

本项目**不分发任何模型权重**；模型能力通过 DeepSeek 官方 API（`https://api.deepseek.com`）以网络调用获得，
受服务商条款约束，API Key 由使用者自备。模型输出必须通过结构化校验与证据门控，仅作顾问参考。

## 许可文本获取

- Python 组件：`pip download <name>==<version>` 后解压包内 `*.dist-info/LICENSE*`；或 <https://pypi.org/project/<name>/>
- 前端组件：`node_modules/<name>/LICENSE`；或 <https://www.npmjs.com/package/<name>>
- 基础镜像：`docker run --rm <image> cat /usr/share/doc/<pkg>/copyright` 及各镜像官方仓库

## 自行开发部分

`backend/app/`、`frontend/src/`、`checklists/`、`backend/scripts/`、`docs/`、`materials/` 下的全部内容均为本项目自主开发，
第三方组件仅作为通用库使用，未修改其源代码。
