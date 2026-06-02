# 筛选踩坑记录

## 踩坑 1：市值单位陷阱
- **现象**：筛选条件 `市值>50亿` 结果 0 只
- **根因**：tushare `total_mv` 单位是**万元**，用了 `÷ 1e8` 导致所有市值变成小数
- **修复**：`df['total_mv'] = df['total_mv'] / 1e4  # 万元→亿`
- **验证**：茅台 total_mv 约 1.8e7 万 → ÷1e4 = 18000亿 ✓

## 踩坑 2：PE+PB 权重过高导致银行霸榜
- **现象**：筛选 30 只，全是大行、保险、建筑
- **根因**：`score = 0.4*pe_score + 0.3*pb_score + 0.3*mv_score`，银行天然低PE低PB
- **修复方向**：
  - 加入 ROE>10% 或营收增速筛选
  - 调高 PE 下限到 15（排除极端低估值）
  - 行业分散：每个行业只取 Top 2-3
  - 分成多池：价值池 / 成长池 / GARP池

## 踩坑 3：cronjob 脚本路径
- **现象**：`data fetch` 无 symbol 参数返回错误
- **结论**：data fetch CLI 不支持龙虎榜/北向/涨停板等市场级查询
- **替代方案**：直接用 akshare Python API

## 踩坑 4：Profile 环境下 $HOME 被重定向
- **现象**：脚本中 `$HOME/wiki/...` 解析为 `/home/pc/.hermes/profiles/xiaohong/home/wiki/...`
- **修复**：使用绝对路径 `/home/pc/.hermes/profiles/xiaohong/home/wiki`
- **cron 脚本**：用 `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` 定位同目录脚本

## 踩坑 5：akshare 东方财富限流
- **现象**：`stock_sh_a_spot_em()` 报 `RemoteDisconnected`
- **结论**：东方财富接口有频率限制
- **替代**：用 tushare 做全市场查询，akshare 做补充
