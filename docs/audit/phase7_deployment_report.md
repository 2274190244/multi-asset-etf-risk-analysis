# Phase 7 — Direct Streamlit Deployment Acceptance

验证日期：2026-09-14。此报告覆盖在未手工运行 `build_research_demo.py` 的前提下，直接启动 `streamlit_app.py` 的部署验收。

## 结论

修复前的干净克隆不能完整部署：服务健康检查和主页返回 HTTP 200，但五个研究页面只显示“研究结果尚未生成”。修复后，首次真实浏览器会话会从随仓库发布的约 0.52 MB 标准化历史输入离线生成研究结果，随后六个页面完整加载。

本次没有 push、合并或发布到 Streamlit Community Cloud。验收模拟了其关键路径：根目录 `requirements.txt` 安装 → 直接启动入口 → 新浏览器会话访问。Cloud 使用 Linux；本机验证运行在 Windows / Python 3.12.14，因此不把本机验收表述为已在托管 Cloud 上实际发布。

## 根因与最小修复

`streamlit_app.py` 原先只读取已存在的 `research_results/` 或本地 Phase 归档。干净克隆中两者都不存在，故页面正确给出生成指引，却不能展示研究证据。`requirements.txt` 也允许数值依赖升级，和已验证的固定版本不同。

新增的部署初始化只在默认 `research_results/` 缺失时运行：

1. 读取已提交的标准化输入并校验哈希；不发起市场、NAV 或指数网络请求。
2. 调用既有 Phase 2–5 引擎，保留全部预定义情景，写入新的 `research_results/`。
3. 原构建器先在同一文件系统的临时目录写入，再以原子目录发布；错误不发布半包。
4. 同进程会话由锁串行化。跨进程竞争只在另一进程已发布完整、逐表哈希验证通过的目录时接受；Linux 的 `ENOTEMPTY` 竞争结果亦覆盖。其他错误继续显示给用户。
5. 显式 `ETF_RESEARCH_RESULTS`、已有默认结果及历史 `output_phase*` 不被自动替换。显式目录缺失仍显示手工生成指引。

`.streamlit/config.toml` 关闭开发用源码文件监视，避免监视运行时生成目录；原主题与匿名统计设置保持不变。`requirements.txt` 引用已验证的固定依赖并以 editable 模式安装本项目。没有修改金融计算、策略、参数、研究输出定义或 Phase 1–6 历史内容。

## 真实冷启动验收

最终候选为 `e18ab53c9de10feca0346a5471a1e0e63355b807`。从该分支的全新 Git 克隆开始，确认启动前不存在 `research_results/`、`output_phase1–5`、原始审计目录或虚拟环境。随后只执行：

```console
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

没有执行 `build_research_demo.py`。独立安装耗时 145.3 秒，来自 PyPI 的固定依赖可安装且 `pip check` 无冲突。服务健康接口与主页均返回 HTTP 200。

新的无头 Chrome 会话在首次访问前再次确认结果目录不存在。首次会话耗时 25.4 秒，自动生成日志仅出现一次完整 Phase 2–5 生成序列。六页结果如下：

| 页面 | 缺失结果提示 | 表格 | Plotly 图表 |
|---|---:|---:|---:|
| 研究概览 | 否 | 0 | 0 |
| ETF Tracking Research | 否 | 2 | 4 |
| Walk-Forward Portfolio Research | 否 | 2 | 4 |
| Index Construction Research | 否 | 3 | 2 |
| Robustness Analysis | 否 | 3 | 2 |
| 数据与方法附录 | 否 | 0 | 0 |

研究概览和附录为文字/来源页面，四个研究模块均验证了可见表格和图表。浏览器导航使用用户可见的侧栏标签；验收阻止到非本地 URL 的请求。

作为对照，修复前提交 `e1798d9` 用旧 `requirements.txt` 完成独立安装后，HTTP 200 仍可取得，但五个研究页全部只显示“研究结果尚未生成”；这证明自动初始化覆盖的是实际部署缺口，而非只改善测试环境。

## 测试结果

计数从 pytest JUnit XML 的实际执行结果读取，不从测试函数数量推断。

| 环境 | Collected | Passed | Failed | Skipped | 用时 |
|---|---:|---:|---:|---:|---:|
| 本阶段生产代码变更前、完整本地归档 baseline | 303 | 303 | 0 | 0 | 55.91 秒 |
| 最终候选、完整本地归档 | 311 | 311 | 0 | 0 | 75.37 秒 |
| 最终冷启动克隆、无原始归档 | 311 | 290 | 0 | 21 | 41.19 秒 |

最终套件在原 303 个用例上新增 8 个部署用例；原用例无删除。新增覆盖直接启动自动生成、六页加载、同进程并发、跨进程 `FileExistsError` / `ENOTEMPTY`、失败后可重试、现有结果/历史归档/显式目录不被覆盖。

干净克隆的 21 项跳过都需要未分发的原始 Phase 1/3/5 归档。它们在完整本地归档环境中全部执行通过，且跳过原因逐项显示，不计入通过数量。完整档案严格模式在缺失时退出，而不将缺失视作成功。

## 完整性与发布判断

重新计算的 `output_verified` 与 `output_phase1–5` 共 141 个本地历史文件哈希全部未变。新增提交不含 `research_results/`、`output_phase*`、SQLite、原始 HTTP 响应、审计中间文件、本机绝对路径或凭据；运行时结果和验收日志均位于 Git 忽略目录。

当前候选具备以下条件：

- **可 push：是。** 本地提交经过完整验证；尚未执行 push。
- **可 merge：工程上是。** `origin/main` 是当前候选的祖先，未发现提交历史冲突；仍须在 push 后创建或更新 PR，并由 GitHub 的实际合并检查确认。
- **可部署：是，限本阶段的技术验收。** 在干净克隆中已按 Cloud 等价路径直接启动并完整加载；实际 Streamlit Community Cloud 发布、Linux 运行时限制、平台磁盘持久性和账户配置尚未实际执行。

剩余边界不变：首次会话需要约 11 MB 可写空间和约 10–60 秒计算时间；平台重建或运行时磁盘清空会再次计算。公开标准化输入可重现 Phase 2–5 计算，不公开完整原始采集审计链，也不改变 Tracking 口径、样本或历史数据局限。
