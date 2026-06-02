#!/usr/bin/env python3
"""
北向资金数据采集器
用法: python3 fetch_northbound.py [output_path]
  不指定路径时输出到 stdout
  指定路径时写入 JSON 文件并在 stdout 打印摘要
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_pipeline import get_north_flow

data = get_north_flow()

if len(sys.argv) > 1:
    outpath = sys.argv[1]
    os.makedirs(os.path.dirname(outpath) or '.', exist_ok=True)
    with open(outpath, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'  ✓ {data["net_flow"]}亿 source={data["data_source"]}')
else:
    print(json.dumps(data, ensure_ascii=False, indent=2))
