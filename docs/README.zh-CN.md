# Apple Notes MCP

默认只读、按精确文件夹 ID 限定范围的本机 MCP 服务。可显式开启非删除编辑；
附件接口额外标记为实验功能，默认关闭。没有直接连接 iCloud 的云端 API，
远程访问时 Mac 必须保持登录、唤醒和联网。

## 快速试用（不接触真实笔记）

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
python scripts/smoke_test.py
python -m unittest discover -s tests -v
```

真实接入需要 macOS Notes 和 Automation 权限。先用 `--preflight` 检查，
再在本机用 `NOTES_ALLOW_REAL=1 apple-notes-mcp --notes --request-automation`
主动请求权限。`--folders` 只用于在本机选择文件夹；不要上传输出。
使用 `--allowed-folder` 明确填写所选 ID，子文件夹不自动包含。

写入必须同时开启 `--enable-writes` 和 `NOTES_ALLOW_WRITE=1`，每次编辑使用
最新版本号，并先保存私有备份。不提供删除、清空、解锁、分享或远程扩展范围。
存在附件的笔记不允许替换正文或从正文备份恢复，避免丢失附件。

已经有真实客户端验收证据的能力包括读取、搜索、新建、追加、重命名、基础格式
和备份恢复。跨文件夹移动只有合成测试；附件添加/读取尚未完成原生验收，需额外
开启 `--experimental-attachments`。原生待办勾选、置顶、标签和文件夹管理未实现。
不能把普通列表说成原生待办，也不能承诺支持 Notes 全部功能。

备份含私人正文，目录权限 `0700`、文件 `0600`，不在项目内。
安装不会启动后台服务、创建密钥或替换已有部署。配置示例必须在本机填写；
不要提交真实 ID、路径、凭据、笔记或备份。

完整命令、限制与故障排查见 [英文 README](../README.md)、
[验证范围](validation.md) 和 [安全说明](../SECURITY.md)。
