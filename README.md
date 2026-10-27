# Fluffs

这里是一个轻量的异步 QQ 机器人框架

`fluffs` 是框架 （OneBot 11/NapCat），`meowers` 是基于它写的示例应用。


## 它现在能干嘛
- **异步**：使用 `asyncio`
- **接入大模型**：群里 @ 聊天对话，其他用途什么的
- **插件热重载**：发 `//reload` 生效
- **微内核架构**：比较轻量啦算是

## 怎么跑起来
你需要提前装好：
Python 3.14+、
`uv` 包管理器，
还有 [NapCat](https://napneko.github.io/)

1. **克隆代码**
   ```bash
   git clone https://github.com/eriser-owo/fluffs.git
   cd fluffs
   ```
2. **装依赖**（uv 会自动搞定）
   ```bash
   uv sync
   ```
   
| 依赖 | 版本 | 用途 | 用在哪 |
|---|---|---|---|
| `websockets` | ≥15.0 | WebSocket 服务端 / 客户端 | `fluffs/napcat/transport/`（反向 / 正向 WS） |
| `coloredlogs` | ≥15.0.1 | 终端彩色日志 | `fluffs/logging_setup.py`（`ColoredFormatter`） |

> 只有这 2 个是框架自己要的。把 `meowers/` 目录整个挪走，框架仍然能启动（只剩内置 `//help` `//status`）。



3. **改配置**


   把 `config/config.toml.example` 和 `.env.example` 复制一份，去掉后缀名 `.example` ,填上你的信息。
   在 NapCat 中配置好正/反向WS以及其他配置项


4. **启动！**


   先启动 NapCat 然后运行项目（launch.bat/launch.sh）


## 怎么写插件？
去 `meowers/plugins/` 目录下,参考 `_template.py`

## 协议
- 使用 MIT 协议开源
