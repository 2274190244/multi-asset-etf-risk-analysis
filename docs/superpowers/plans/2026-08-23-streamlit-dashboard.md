# 中文 Streamlit ETF 风险看板实施计划

> **执行方式：** 在 `feature/streamlit-dashboard` 分支中按测试先行实施；每一阶段先写失败测试，再完成最小实现并复测。

**目标：** 将 `output_verified` 中的已验证结果制作成可由招聘者在线浏览的中文 Streamlit 看板，同时保持原有 88 项分析测试全部通过。

**架构：** `src/portfolio_analysis/dashboard_data.py` 负责文件读取、字段校验和派生指标；`streamlit_app.py` 只负责筛选器、布局和 Plotly 图表；页面不请求实时行情，不修改验证数据。

**技术栈：** Python 3.12、pandas、NumPy、Streamlit、Plotly、pytest、Streamlit AppTest。

---

## 任务 1：建立看板数据契约

**文件：**
- 新增：`src/portfolio_analysis/dashboard_data.py`
- 新增：`tests/test_dashboard_data.py`

1. 编写失败测试，覆盖八个输入文件、必需字段、日期解析和有限数值校验。
2. 运行 `python -m pytest tests/test_dashboard_data.py -q`，确认因模块不存在而失败。
3. 实现 `DashboardDataError`、`DashboardData` 和 `load_dashboard_data(project_root)`。
4. 再次运行单文件测试，确认真实 `output_verified` 数据可以加载。
5. 增加缺少文件、缺少字段、非法日期和非有限数值用例，确保错误信息包含文件名与问题字段。

## 任务 2：实现可测试的派生分析

**文件：**
- 修改：`src/portfolio_analysis/dashboard_data.py`
- 修改：`tests/test_dashboard_data.py`

1. 为资产区间累计收益编写测试：筛选资产和日期后，每只资产起点必须为 `0%`。
2. 为组合回撤编写测试：回撤不大于零，且等于累计财富相对历史峰值的变化。
3. 为相关性矩阵编写测试：矩阵为方阵、对称、对角线为 1，并使用中文资产名称。
4. 实现 `asset_cumulative_returns`、`portfolio_drawdowns` 和 `correlation_wide`。
5. 运行 `python -m pytest tests/test_dashboard_data.py -q`，确认全部通过。

## 任务 3：编写中文 Streamlit 看板

**文件：**
- 修改：`streamlit_app.py`
- 修改：`requirements.txt`
- 修改：`pyproject.toml`
- 新增：`tests/test_streamlit_app.py`

1. 先写 AppTest 烟雾测试，断言标题、四个标签页、四个关键数字及无未捕获异常。
2. 运行 `python -m pytest tests/test_streamlit_app.py -q`，确认空入口无法满足测试。
3. 配置宽屏页面、克制的白底深蓝视觉系统和侧边栏资产/日期筛选。
4. 实现“市场表现”：累计收益曲线、收益波动散点图、资产指标表。
5. 实现“风险分析”：最大回撤/VaR/夏普对比与相关性热力图。
6. 实现“组合分析”：组合累计收益、组合回撤、权重分组图和指标表。
7. 实现“数据质量”：清洗计数、覆盖区间、方法与数据来源说明。
8. 补齐 Streamlit、Plotly 等部署依赖并运行两个新增测试文件。

## 任务 4：补全招聘展示与部署说明

**文件：**
- 修改：`README.md`
- 新增：`docs/assets/streamlit-dashboard.png`

1. 增加“在线演示/本地运行/Streamlit Community Cloud 部署”章节。
2. 明确部署参数：仓库 `2274190244/multi-asset-etf-risk-analysis`、分支 `main`、入口 `streamlit_app.py`。
3. 启动本地服务器并保存不含本机信息的桌面截图。
4. 将截图加入 README，并检查中文显示与链接路径。

## 任务 5：完整验证与提交

**文件：**
- 验证全部新增和既有文件

1. 运行 `python -m pytest tests -q -p no:cacheprovider`，要求原有 88 项及新增测试全部通过。
2. 在桌面和手机视口检查四个标签页、图表非空、文字不重叠、表格不越界。
3. 检查 `git diff --check`、依赖文件和 Git 状态。
4. 提交功能分支，提交信息为 `feat: add Chinese Streamlit risk dashboard`。
5. 本地服务器保持运行，并向用户提供访问地址和后续 Streamlit Cloud 发布步骤。
