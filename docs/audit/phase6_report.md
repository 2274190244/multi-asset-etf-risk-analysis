# Phase 6 交付报告

## 范围
仅整理Phase 1–5为研究作品，未修改金融计算、策略或历史结果；未新增模型、Regime。

## 最终页面
研究概览 → ETF Tracking Research → Walk-Forward Portfolio Research → Index Construction Research → Robustness Analysis → 数据与方法附录。
四个研究模块均按Research Question → Methodology → Evidence → Findings → Limitations呈现。

## 交付
- README.md：研究主线、发现、口径、运行、复现、验证与局限。
- docs/RESEARCH_SUMMARY.md：完整研究解释、3条简历bullet与5条面试要点。
- streamlit_app.py：六页面侧栏导航、已存结果筛选、证据表下载。
- src/portfolio_analysis/research_display.py：SHA256校验、Tracking不可比屏蔽、同组筛选、共享结论。
- tests/test_research_display.py：14项展示测试；原4项旧布局测试归档并替换，因此总数净增10。
- docs/METHODOLOGY.md：补充显示单位、已存样本和跨阶段比较边界。

## 验证与审计
Baseline：287 collected，287 passed，0 failed/skipped，55.00秒。
首轮：297 collected，296 passed，1 failed，30.13秒。旧Phase 1测试在Windows临时目录重命名时报WinError 5。
第二轮新目录：297 collected，296 passed，1 failed，30.16秒；同类错误出现在另一项旧测试，未修改生产代码掩盖问题。
第三轮改用另一磁盘临时目录，结果见下面最终记录。未确定间歇访问错误根因，不能断言是同步程序或杀毒软件。
页面使用Streamlit AppTest验证六页渲染、筛选和不可得状态，未完成独立浏览器像素级视觉验收。
output_verified及output_phase1至output_phase5全部原文件哈希一致，见phase6/preservation_check.json。

## 研究口径
主组最低国债权重95.57%，扩展组93.73%只描述可用路径。逆波动低风险与集中度并存。月度通常提高换手但并非所有配对均如此，收益改善不稳定。
股票跟踪结果相对全收益研究参考，未替代官方价格基准。黄金/国债严格跟踪指标不可得。没有参数择优、显著性或实盘能力主张。

## 剩余局限
原研究数据长度、固定Universe、数据修订、分红完整性、估值时点和费用模型局限保留。
展示层只读取并校验已存证据；不会更新数据或重新优化。CSV字段保留研究标识以便审计，阅读解释见各模块。
旧README、旧页面及旧布局测试保存在docs/audit/phase6，不覆盖Phase 1–5输出。

第三轮：297 collected，294 passed，3 failed，30.27秒；较长临时目录使原始数据文件复制出现FileNotFoundError，路径超过传统Windows路径长度范围。改用仓库内短路径再验证，未修改历史金融代码。日志final_tests_localtemp.log保留。

## 最终完整测试
297 collected / 297 passed / 0 failed / 0 skipped / 0 errors，30.21秒。使用短临时路径.t6；日志phase6/final_shortpath.log与JUnit XML。14项新展示检查替换4项旧布局断言，净增10。
