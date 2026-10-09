# NoteBridge

**让 AI 读懂和使用你的 Apple Notes。**

通过 MCP 连接 Mac 上的备忘录：搜索笔记、保留导出的排版结构、获取原图和原文件，
并按需开启带版本检查与本地备份的编辑。没有 Python 运行时第三方依赖，不建立后台索引。

[English](../README.md) · [架构](architecture.md) · [部署](deployment.md) · [版本记录](../CHANGELOG.md)

## 快速开始

需要 macOS、Python 3.9+ 和系统备忘录。先打开备忘录，让所需账号完成同步。

```sh
git clone https://github.com/mqingcs/notebridge.git
cd notebridge
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .

NOTES_ALLOW_REAL=1 notebridge --notes --request-automation
NOTES_ALLOW_REAL=1 notebridge --notes --folders
NOTES_ALLOW_REAL=1 notebridge --notes --allowed-folder '你的精确文件夹ID'
```

将 `.venv/bin/notebridge` 的绝对路径填入客户端的 stdio MCP 配置。
完整配置示例见[英文 README](../README.md#connect-your-mcp-client)。
只读取明确选择的文件夹，子文件夹不自动包含；本机使用无需 API key。

## 原图、原文件与排版

开启附件接口：

```sh
NOTES_ALLOW_REAL=1 NOTES_ALLOW_WRITE=1 notebridge --notes \
  --allowed-folder '你的精确文件夹ID' --enable-writes --experimental-attachments
```

- 列出附件后按 ID 读取，重名文件不会混淆。
- 原件保持原始字节，提供 MIME、总大小与完整 SHA-256。默认分段256 KiB，每段最大4 MiB，
  按 `next_offset` 继续并传 `expected_sha256`，拼接后核对哈希。
- 支持 MCP resources 的客户端还可一次获取64 MiB以内的完整原件。
- PNG、JPEG、HEIC等可另生成最长边1600像素的JPEG预览。预览不替代原图。
- 任意扩展名可按原始字节传输；GPG取得的是密文，不表示已经解密或理解其内容。
- `apple_notes_get` 设置 `format="html"` 返回 Notes 导出的排版结构。内嵌图片外置为哈希引用，
  可与附件原件匹配还原，避免将大量重复图片编码塞进文字上下文。

已在真实笔记验证 PNG、HEIC 原件和本地MCP预览；其他格式具有合成字节传输测试。
附件功能保留额外开启参数，后续继续扩展原生格式与客户端覆盖。

## 编辑与恢复

只需编辑时，添加 `--enable-writes` 并设置 `NOTES_ALLOW_WRITE=1`。
编辑前通过 `apple_notes_prepare_edit` 取得版本号，修改前自动保存本地备份。
支持新建、追加、重命名、基础格式、允许文件夹之间的移动，以及正文备份恢复。

默认备份位于 `~/Library/Application Support/Apple Notes MCP/backups`。
不提供删除；有附件的笔记不替换正文，正文备份不包含附件原件。
原生待办勾选、置顶、标签与文件夹管理尚未实现。

## 运行方式

服务按请求访问 Notes，空闲时等待输入，没有后台扫描。导出和预览会产生临时资源消耗。
它连接 Mac 应用，不直连 iCloud；远程使用时 Mac 需要保持登录、唤醒和联网。
安装包本身不会创建常驻服务。需要远程访问时，另行配置经过认证的私人传输。

贡献方式见 [CONTRIBUTING.md](../CONTRIBUTING.md)，MIT许可证见 [LICENSE](../LICENSE)。
