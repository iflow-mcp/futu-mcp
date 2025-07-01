#!/usr/bin/env python3
"""
富途MCP服务器 - 修复版本

基于simple_futu_real.py的稳定架构，但包含所有新功能。
确保工具能正确注册和识别。
"""

import asyncio
import sys
import os
from pathlib import Path
import pandas as pd
from typing import Dict, Any
import futu as ft
# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import mcp.server.stdio
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel import NotificationOptions

# 富途客户端
futu_client = None

def init_futu_client():
    """初始化富途客户端"""
    global futu_client
    
    try:
        from trademind.scheduler.futu_client import FutuClient
        
        # 从环境变量获取配置
        host = os.getenv("FUTU_API_HOST", "127.0.0.1")
        port = int(os.getenv("FUTU_API_PORT", "11111"))
        unlock_pwd = os.getenv("FUTU_UNLOCK_PWD", "")
        
        
        print(f"🔗 连接富途API: {host}:{port}", file=sys.stderr)
        
        config = {
            "host": host,
            "port": port,
            "unlock_pwd": unlock_pwd if unlock_pwd else None
        }
        
        futu_client = FutuClient(config)
        
        if futu_client.quote_ctx:
            print("✅ 富途行情API连接成功", file=sys.stderr)
        else:
            print("❌ 富途行情API连接失败", file=sys.stderr)
            return False
        if unlock_pwd and futu_client.trade_ctx:
            print("✅ 富途交易API连接成功", file=sys.stderr)
        elif unlock_pwd:
            print("❌ 富途交易API连接失败", file=sys.stderr)
        return True
        
    except Exception as e:
        print(f"❌ 富途客户端初始化失败: {e}", file=sys.stderr)
        futu_client = None
        return False

# 创建服务器
server = Server("futu-mcp-enhanced")

@server.list_tools()
async def list_tools():
    """列出所有工具"""
    return [  
        Tool(
            name="get_user_security",
            description="获取自选股列表，查看指定分组的自选股票",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_name": {
                        "type": "string",
                        "description": "自选股分组名称。系统分组：全部、沪深、港股、美股、期权、港股期权、美股期权、特别关注、期货",
                        "default": "全部"
                    }
                },
                "required": ["group_name"],
                "additionalProperties": False
            }
        ),
        
        Tool(
            name="get_user_security_group",
            description="获取自选股分组列表，查看所有可用的自选股分组",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_type": {
                        "type": "string",
                        "description": "分组类型筛选",
                        "enum": ["ALL", "SYSTEM", "CUSTOM"],
                        "default": "ALL"
                    }
                },
                "additionalProperties": False
            }
        ),
        
        Tool(
            name="get_positions",
            description="获取持仓信息（需要交易权限）",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_type": {
                        "type": "string",
                        "description": "账户类型",
                        "enum": ["REAL", ],
                        "default": "REAL"
                    }
                },
                "additionalProperties": False
            }
        ),

        Tool(
            name="get_market_snapshot",
            description="获取股票快照数据，包含实时价格、交易量、市值等详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "code_list": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "股票代码列表，如 ['US.AAPL', 'HK.00700']。每次最多可请求400个标的",
                        "maxItems": 400
                    }
                },
                "required": ["code_list"],
                "additionalProperties": False
            }
        ),

        Tool(
            name="get_history_kline",
            description="获取历史K线数据，支持分钟、日、周、月K线",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码，如 US.AAPL, HK.00700"
                    },
                    "start": {
                        "type": "string",
                        "description": "开始时间，格式：yyyy-MM-dd，如：2023-01-01",
                        "default": None
                    },
                    "end": {
                        "type": "string",
                        "description": "结束时间，格式：yyyy-MM-dd，如：2023-12-31",
                        "default": None
                    },
                    "ktype": {
                        "type": "string",
                        "description": "K线类型",
                        "enum": ["K_1M", "K_5M", "K_15M", "K_30M", "K_60M", "K_DAY", "K_WEEK", "K_MONTH"],
                        "default": "K_DAY"
                    },
                    "autype": {
                        "type": "string",
                        "description": "复权类型",
                        "enum": ["None", "QFQ", "HFQ"],
                        "default": "QFQ"
                    }
                },
                "required": ["code"],
                "additionalProperties": False
            }
        ),
        
        Tool(
            name="get_funds",
            description="获取账户资金信息，包括总资产、现金、证券资产等详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "trd_env": {
                        "type": "string",
                        "description": "交易环境，REAL（真实）或 SIMULATE（模拟）",
                        "enum": ["REAL", "SIMULATE"],
                        "default": "REAL"
                    },
                    "acc_id": {
                        "type": "integer",
                        "description": "交易业务账户ID，默认0表示使用第一个账户",
                        "default": 0
                    },
                    "refresh_cache": {
                        "type": "boolean",
                        "description": "是否刷新缓存",
                        "default": False
                    }
                },
                "additionalProperties": False
            }
        ),

        Tool(
            name="place_order",
            description="下单交易，支持股票、期权等品种的买入卖出",
            inputSchema={
                "type": "object",
                "properties": {
                    "price": {
                        "type": "number",
                        "description": "订单价格，即使是市价单也需要传入价格（可以是任意值）"
                    },
                    "qty": {
                        "type": "number",
                        "description": "订单数量，期权期货单位是'张'"
                    },
                    "code": {
                        "type": "string",
                        "description": "股票代码，如 US.AAPL, HK.00700"
                    },
                    "trd_side": {
                        "type": "string",
                        "description": "交易方向",
                        "enum": ["BUY", "SELL", "SELL_SHORT", "BUY_BACK"]
                    },
                    "order_type": {
                        "type": "string",
                        "description": "订单类型",
                        "enum": ["NORMAL", "MARKET", "ABSOLUTE_LIMIT", "AUCTION", "AUCTION_LIMIT", "SPECIAL_LIMIT"],
                        "default": "NORMAL"
                    },
                    "adjust_limit": {
                        "type": "number",
                        "description": "价格微调幅度，正数代表向上调整，负数代表向下调整",
                        "default": 0
                    },
                    "trd_env": {
                        "type": "string",
                        "description": "交易环境",
                        "enum": ["REAL", "SIMULATE"],
                        "default": "REAL"
                    },
                    "acc_id": {
                        "type": "integer",
                        "description": "交易业务账户ID，默认0表示使用第一个账户",
                        "default": 0
                    },
                    "remark": {
                        "type": "string",
                        "description": "备注，订单会带上此备注字段，方便标识订单"
                    },
                    "time_in_force": {
                        "type": "string",
                        "description": "订单有效期",
                        "enum": ["DAY", "GTC"],
                        "default": "DAY"
                    },
                    "fill_outside_rth": {
                        "type": "boolean",
                        "description": "是否允许盘前盘后成交，用于港股盘前竞价与美股盘前盘后",
                        "default": False
                    }
                },
                "required": ["price", "qty", "code", "trd_side"],
                "additionalProperties": False
            }
        ),

        Tool(
            name="modify_order",
            description="改单/撤单，支持修改价格、数量或撤销订单",
            inputSchema={
                "type": "object",
                "properties": {
                    "modify_order_op": {"type": "string", "enum": ["NORMAL", "CANCEL"], "description": "操作类型"},
                    "order_id": {"type": "string", "description": "订单号"},
                    "qty": {"type": "number", "description": "改单后数量", "default": 0},
                    "price": {"type": "number", "description": "改单后价格", "default": 0},
                    "adjust_limit": {"type": "number", "description": "价格微调幅度", "default": 0},
                    "trd_env": {"type": "string", "enum": ["REAL", "SIMULATE"], "default": "REAL"},
                    "acc_id": {"type": "integer", "default": 0}
                },
                "required": ["modify_order_op", "order_id"],
                "additionalProperties": False
            }
        ),

        Tool(
            name="get_stock_filter",
            description="条件选股，支持多种属性和技术指标筛选",
            inputSchema={
                "type": "object",
                "properties": {
                    "market": {
                        "type": "string",
                        "description": "市场标识",
                        "enum": ["HK", "US", "SH", "SZ"],
                        "default": "HK"
                    },
                    "filter_list": {
                        "type": "array",
                        "description": "筛选条件列表，支持简单条件、财务指标和技术指标",
                        "items": {
                            "type": "object",
                            "oneOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["simple"]},
                                        "filter_min": {"type": "number"},
                                        "filter_max": {"type": "number"},
                                        "stock_field": {
                                            "type": "string",
                                            "description": "股票字段，如 CUR_PRICE, VOLUME, MARKET_VAL 等"
                                        },
                                        "is_no_filter": {"type": "boolean", "default": False},
                                        "sort": {
                                            "type": "string",
                                            "enum": ["ASCEND", "DESCEND"],
                                            "default": "ASCEND"
                                        }
                                    },
                                    "required": ["type", "filter_min", "filter_max", "stock_field"]
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["financial"]},
                                        "filter_min": {"type": "number"},
                                        "filter_max": {"type": "number"},
                                        "stock_field": {
                                            "type": "string",
                                            "description": "财务指标字段，如 CURRENT_RATIO, PE_RATIO 等"
                                        },
                                        "is_no_filter": {"type": "boolean", "default": False},
                                        "sort": {
                                            "type": "string",
                                            "enum": ["ASCEND", "DESCEND"],
                                            "default": "ASCEND"
                                        },
                                        "quarter": {
                                            "type": "string",
                                            "enum": ["ANNUAL", "QUARTERLY"],
                                            "default": "ANNUAL"
                                        }
                                    },
                                    "required": ["type", "filter_min", "filter_max", "stock_field"]
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["custom"]},
                                        "ktype": {
                                            "type": "string",
                                            "enum": ["K_DAY", "K_WEEK", "K_MONTH", "K_1M", "K_5M", "K_15M", "K_30M", "K_60M"],
                                            "default": "K_DAY"
                                        },
                                        "stock_field1": {
                                            "type": "string",
                                            "description": "第一个技术指标字段，如 MA10, RSI"
                                        },
                                        "stock_field2": {
                                            "type": "string",
                                            "description": "第二个技术指标字段，如 MA60, PRICE"
                                        },
                                        "relative_position": {
                                            "type": "string",
                                            "enum": ["MORE", "LESS", "CROSS_UP", "CROSS_DOWN"],
                                            "description": "两个指标的相对位置关系"
                                        },
                                        "is_no_filter": {"type": "boolean", "default": False}
                                    },
                                    "required": ["type", "stock_field1", "stock_field2", "relative_position"]
                                }
                            ]
                        }
                    },
                    "plate_code": {
                        "type": "string",
                        "description": "板块代码，如 'HK.Motherboard'（港股主板）",
                        "default": None
                    },
                    "begin": {
                        "type": "integer",
                        "description": "分页起点",
                        "default": 0
                    },
                    "num": {
                        "type": "integer",
                        "description": "返回数量，默认200，最大200",
                        "default": 200,
                        "maximum": 200
                    }
                },
                "required": ["market", "filter_list"],
                "additionalProperties": False
            }
        ),

        Tool(
            name="get_option_chain",
            description="获取期权链，支持多种筛选条件",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "标的股票代码，如 HK.00700"},
                    "index_option_type": {"type": "string", "description": "指数期权类型，仅港股指数期权有效", "default": "NORMAL"},
                    "start": {"type": "string", "description": "开始日期，到期日 yyyy-MM-dd", "default": None},
                    "end": {"type": "string", "description": "结束日期，到期日 yyyy-MM-dd", "default": None},
                    "option_type": {"type": "string", "description": "期权类型 CALL/PUT/ALL", "default": "ALL"},
                    "option_cond_type": {"type": "string", "description": "价内外类型 ALL/OTM/ATM/ITM", "default": "ALL"},
                    "data_filter": {
                        "type": "object",
                        "description": "数据筛选条件，可选",
                        "properties": {
                            "implied_volatility_min": {"type": "number"},
                            "implied_volatility_max": {"type": "number"},
                            "delta_min": {"type": "number"},
                            "delta_max": {"type": "number"},
                            "gamma_min": {"type": "number"},
                            "gamma_max": {"type": "number"},
                            "vega_min": {"type": "number"},
                            "vega_max": {"type": "number"},
                            "theta_min": {"type": "number"},
                            "theta_max": {"type": "number"},
                            "rho_min": {"type": "number"},
                            "rho_max": {"type": "number"},
                            "net_open_interest_min": {"type": "number"},
                            "net_open_interest_max": {"type": "number"},
                            "open_interest_min": {"type": "number"},
                            "open_interest_max": {"type": "number"},
                            "vol_min": {"type": "number"},
                            "vol_max": {"type": "number"}
                        },
                        "additionalProperties": False
                    }
                },
                "required": ["code"],
                "additionalProperties": False
            }
        ),
    ]

def get_history_kline(code: str, start: str = None, end: str = None, ktype: str = 'K_DAY', autype: str = 'QFQ') -> str:
    """获取历史K线数据"""
    try:
        # 调用富途客户端获取K线数据
        kline_data = futu_client.get_history_kline(code, start, end, ktype, autype)
        
        if isinstance(kline_data, dict) and "error" in kline_data:
            return f"❌ {kline_data['error']}"

        # 格式化输出
        result = f"📊 {code} 历史K线数据\n" + "=" * 60 + "\n\n"
        
        # 基本信息
        result += f"⏰ 周期：{ktype}\n"
        result += f"📅 时间范围：{start or '365天前'} 至 {end or '今日'}\n"
        result += f"🔄 复权方式：{autype}\n\n"
        
        # 统计数据
        stats = kline_data.get('统计数据', {})
        result += f"共 {stats.get('K线数量', 0)} 根K线\n"
        
        # 区间表现
        total_change = stats.get('总涨跌幅', '0%')
        if isinstance(total_change, str):
            total_change = float(total_change.rstrip('%'))
        direction = "📈" if total_change >= 0 else "📉"
        result += f"\n{direction} 区间表现：\n"
        result += f"   涨跌幅：{total_change:+.2f}%\n"
        result += f"   最高价：{stats.get('最高价', 0):.3f}\n"
        result += f"   最低价：{stats.get('最低价', 0):.3f}\n"
        
        # 成交统计
        result += f"\n📊 成交统计：\n"
        result += f"   总成交量：{stats.get('总成交量', 0):,.0f}\n"
        result += f"   平均成交量：{stats.get('平均成交量', 0):,.0f}\n"
        
        if "平均换手率" in stats:
            result += f"   平均换手率：{stats.get('平均换手率', 0):.2f}%\n"

        # === MACD详细数据输出 ===
        tech = kline_data.get("技术指标", {})
        if tech:
            # MACD
            if "macd" in tech:
                macd = tech["macd"]
                latest = macd.get("latest", {})
                signals = macd.get("signals", [])
                result += "\n📊 MACD 指标：\n"
                result += f"   最新 DIF: {latest.get('DIF', 0):.4f}\n"
                result += f"   最新 DEA: {latest.get('DEA', 0):.4f}\n"
                result += f"   最新 MACD: {latest.get('MACD', 0):.4f}\n"
                if signals:
                    result += "   最近5个信号：\n"
                    for s in signals:
                        result += f"      {s['date']}: {s['signal']}\n"
                else:
                    result += "   最近无明显金叉/死叉信号\n"
            # 布林带
            if "boll" in tech:
                boll = tech["boll"]
                result += "\n📊 布林带：\n"
                result += f"   上轨(UP): {boll.get('UP', 0):.3f}\n"
                result += f"   中轨(MB): {boll.get('MB', 0):.3f}\n"
                result += f"   下轨(DN): {boll.get('DN', 0):.3f}\n"
            # 压力/支撑位
            if "levels" in tech:
                levels = tech["levels"]
                result += "\n📊 主要压力/支撑位：\n"
                result += f"   年内高点: {levels.get('year_high', 0):.3f}\n"
                result += f"   年内低点: {levels.get('year_low', 0):.3f}\n"
                result += f"   20日均线: {levels.get('ma20', 0):.3f}\n"
                result += f"   60日均线: {levels.get('ma60', 0):.3f}\n"

        return result

    except Exception as e:
        return f"❌ 获取历史K线失败: {str(e)}"

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """处理工具调用"""
    print(f"🔧 调用工具: {name}, 参数: {arguments}", file=sys.stderr)
    
    if not futu_client:
        return [TextContent(
            type="text",
            text="❌ 富途客户端未连接\n\n请确保:\n1. 富途牛牛客户端已启动并登录\n2. API接口已开启\n3. 网络连接正常"
        )]
    
    try:
        # 我的自选股
        if name == "get_user_security":
            group_name = arguments.get("group_name", "特别关注")
            
            # 调用富途客户端获取自选股列表
            user_securities = futu_client.get_user_security(group_name)
            
            if not user_securities:
                return [TextContent(
                    type="text",
                    text=f"❌ 获取自选股列表失败"
                )]
            
            # 格式化输出
            result = f"📋 自选股列表（分组：{group_name}）\n" + "=" * 60 + "\n\n"
            for stock in user_securities:
                result += f"{stock.get('股票代码', '')} - {stock.get('股票名称', '')} | 市场: {stock.get('市场', '')} | 每手: {stock.get('每手股数', '')}\n"
            
            return [TextContent(
                type="text",
                text=result
            )]
            
        # 自选股分组
        elif name == "get_user_security_group":
            group_type = arguments.get("group_type", "ALL")
            
            # 调用富途客户端获取分组列表
            groups = futu_client.get_user_security_group(group_type)
            
            if not groups:
                return [TextContent(
                    type="text",
                    text=f"❌ 获取分组列表失败"
                )]
            
            # 格式化输出
            result = "📋 自选股分组列表\n" + "=" * 60 + "\n\n"
            for group in groups:
                result += f"📁 {group.get('分组名称', '')} ({group.get('分组类型', '')})\n"
            
            return [TextContent(
                type="text",
                text=result
            )]
            
        # 持仓信息
        elif name == "get_positions":
            account_type = arguments.get("account_type", "REAL")
            
            # 调用富途客户端获取持仓信息
            positions = futu_client.get_positions(account_type)
            
            if not positions:
                return [TextContent(
                    type="text",
                    text=f"❌ 获取持仓信息失败"
                )]
                
            return [TextContent(
                type="text",
                text=positions
            )]
            
        # 获取快照
        elif name == "get_market_snapshot":
            code_list = arguments.get("code_list", [])
            
            # 调用富途客户端获取快照数据
            snapshot = futu_client.get_market_snapshot(code_list)
            
            if not snapshot:
                return [TextContent(
                    type="text",
                    text=f"❌ 获取快照数据失败"
                )]
            
            if "error" in snapshot:
                return [TextContent(
                    type="text",
                    text=f"❌ {snapshot['error']}"
                )]
                
            # 格式化输出
            result = "📊 股票快照数据\n" + "=" * 60 + "\n\n"
            
            for stock in snapshot.get("快照数据", []):
                result += f"📈 {stock['股票代码']} - {stock['股票名称']}\n"
                result += f"   最新价: {stock['最新价']:.3f}\n"
                result += f"   涨跌幅: {((stock['最新价'] - stock['昨收价']) / stock['昨收价'] * 100):.2f}%\n"
                result += f"   今开: {stock['开盘价']:.3f} | 最高: {stock['最高价']:.3f} | 最低: {stock['最低价']:.3f}\n"
                result += f"   成交量: {stock['成交量']:,.0f} | 成交额: {stock['成交额']:,.0f}\n"
                result += f"   换手率: {stock['换手率']}\n"
                result += f"   市值: {stock['总市值']:,.2f}\n\n"
            
            return [TextContent(
                type="text",
                text=result
            )]
            
        # 获取K线
        elif name == "get_history_kline":
            code = arguments.get("code")
            start = arguments.get("start")
            end = arguments.get("end")
            ktype = arguments.get("ktype", "K_DAY")
            autype = arguments.get("autype", "QFQ")
            
            result = get_history_kline(code, start, end, ktype, autype)
            return [TextContent(
                type="text",
                text=result
            )]
            
        # 获取资金信息
        elif name == "get_funds":
            trd_env = arguments.get("trd_env", "REAL")
            acc_id = arguments.get("acc_id", 0)
            refresh_cache = arguments.get("refresh_cache", False)
            
            # 调用富途客户端获取资金信息
            funds = futu_client.get_funds(trd_env, acc_id, refresh_cache)
            
            if isinstance(funds, dict) and "error" in funds:
                return [TextContent(
                    type="text",
                    text=f"❌ {funds['error']}"
                )]
            
            # 格式化输出
            result = "💰 账户资金信息\n" + "=" * 60 + "\n\n"
            
            # 总资产信息
            result += "📊 总资产\n"
            for key, value in funds.get("总资产", {}).items():
                result += f"   {key}: {value:,.2f}\n"
            
            # 现金信息
            result += "\n💵 现金信息\n"
            for currency, info in funds.get("现金信息", {}).items():
                result += f"   {currency}:\n"
                for key, value in info.items():
                    result += f"      {key}: {value:,.2f}\n"
            
            # 交易能力
            result += "\n💪 交易能力\n"
            for key, value in funds.get("交易能力", {}).items():
                result += f"   {key}: {value:,.2f}\n"
            
            # 风险信息
            result += "\n⚠️ 风险信息\n"
            for key, value in funds.get("风险信息", {}).items():
                if isinstance(value, (int, float)):
                    result += f"   {key}: {value:,.2f}\n"
                else:
                    result += f"   {key}: {value}\n"
            
            return [TextContent(
                type="text",
                text=result
            )]
            
        # 下单
        elif name == "place_order":
            # 提取参数
            price = arguments.get("price")
            qty = arguments.get("qty")
            code = arguments.get("code")
            trd_side = arguments.get("trd_side")
            order_type = arguments.get("order_type", "NORMAL")
            adjust_limit = arguments.get("adjust_limit", 0)
            trd_env = arguments.get("trd_env", "REAL")
            acc_id = arguments.get("acc_id", 0)
            remark = arguments.get("remark")
            time_in_force = arguments.get("time_in_force", "DAY")
            fill_outside_rth = arguments.get("fill_outside_rth", False)
            
            # 调用富途客户端下单
            result = futu_client.place_order(
                price=price,
                qty=qty,
                code=code,
                trd_side=trd_side,
                order_type=order_type,
                adjust_limit=adjust_limit,
                trd_env=trd_env,
                acc_id=acc_id,
                remark=remark,
                time_in_force=time_in_force,
                fill_outside_rth=fill_outside_rth
            )
            
            if isinstance(result, dict) and "error" in result:
                return [TextContent(
                    type="text",
                    text=f"❌ {result['error']}"
                )]
            
            # 格式化输出
            order_info = result.get("data", {})
            output = "🎯 下单成功\n" + "=" * 40 + "\n\n"
            
            # 添加订单信息
            for key, value in order_info.items():
                output += f"{key}: {value}\n"
            
            return [TextContent(
                type="text",
                text=output
            )]
            
        # 改单/撤单
        elif name == "modify_order":
            modify_order_op = arguments.get("modify_order_op")
            order_id = arguments.get("order_id")
            qty = arguments.get("qty", 0)
            price = arguments.get("price", 0)
            adjust_limit = arguments.get("adjust_limit", 0)
            trd_env = arguments.get("trd_env", "REAL")
            acc_id = arguments.get("acc_id", 0)
            result = futu_client.modify_order(modify_order_op, order_id, qty, price, adjust_limit, trd_env, acc_id)
            if isinstance(result, dict) and "error" in result:
                return [TextContent(type="text", text=f"❌ {result['error']}")]
            return [TextContent(type="text", text=f"✅ 改单/撤单成功: {result}")]
            
        # 条件选股
        elif name == "get_stock_filter":
            # 提取参数
            market = arguments.get("market")
            filter_list = arguments.get("filter_list", [])
            plate_code = arguments.get("plate_code")
            begin = arguments.get("begin", 0)
            num = arguments.get("num", 200)
            
            # 转换筛选条件
            converted_filters = []
            for filter_data in filter_list:
                filter_type = filter_data.get("type", "simple")
                
                if filter_type == "simple":
                    f = ft.SimpleFilter()
                    f.filter_min = filter_data.get("filter_min")
                    f.filter_max = filter_data.get("filter_max")
                    f.stock_field = getattr(ft.StockField, filter_data.get("stock_field", ""))
                    f.is_no_filter = filter_data.get("is_no_filter", False)
                    if "sort" in filter_data:
                        f.sort = getattr(ft.SortDir, filter_data.get("sort", ""))
                    converted_filters.append(f)
                    
                elif filter_type == "financial":
                    f = ft.FinancialFilter()
                    f.filter_min = filter_data.get("filter_min")
                    f.filter_max = filter_data.get("filter_max")
                    f.stock_field = getattr(ft.StockField, filter_data.get("stock_field", ""))
                    f.is_no_filter = filter_data.get("is_no_filter", False)
                    if "sort" in filter_data:
                        f.sort = getattr(ft.SortDir, filter_data.get("sort", ""))
                    f.quarter = getattr(ft.FinancialQuarter, filter_data.get("quarter", "ANNUAL"))
                    converted_filters.append(f)
                    
                elif filter_type == "custom":
                    f = ft.CustomIndicatorFilter()
                    f.ktype = getattr(ft.KLType, filter_data.get("ktype", "K_DAY"))
                    f.stock_field1 = getattr(ft.StockField, filter_data.get("stock_field1", ""))
                    f.stock_field2 = getattr(ft.StockField, filter_data.get("stock_field2", ""))
                    f.relative_position = getattr(ft.RelativePosition, filter_data.get("relative_position", ""))
                    f.is_no_filter = filter_data.get("is_no_filter", False)
                    converted_filters.append(f)
            
            # 调用富途客户端进行条件选股
            result = futu_client.get_stock_filter(
                market=getattr(ft.Market, market, ft.Market.HK),
                filter_list=converted_filters,
                plate_code=plate_code,
                begin=begin,
                num=num
            )
            
            if isinstance(result, dict) and "error" in result:
                return [TextContent(
                    type="text",
                    text=f"❌ {result['error']}"
                )]
            
            # 格式化输出
            output = "🔍 条件选股结果\n" + "=" * 40 + "\n\n"
            
            if not result:
                output += "未找到符合条件的股票"
            else:
                output += f"共找到 {len(result)} 只股票：\n\n"
                for stock in result:
                    output += f"📈 {stock['code']} - {stock['name']}\n"
                    
                    # 添加筛选条件的值
                    for filter_data in filter_list:
                        if filter_data.get("type") == "simple":
                            field = filter_data.get("stock_field", "")
                            if field in stock:
                                output += f"   {field}: {stock[field]}\n"
                        elif filter_data.get("type") == "financial":
                            field = filter_data.get("stock_field", "")
                            if field in stock:
                                output += f"   {field}: {stock[field]}\n"
                        elif filter_data.get("type") == "custom":
                            if "custom_indicator" in stock:
                                output += f"   技术指标: {stock['custom_indicator']}\n"
                    output += "\n"
            
            return [TextContent(
                type="text",
                text=output
            )]
            
        # 获取期权链
        elif name == "get_option_chain":
            code = arguments.get("code")
            index_option_type = arguments.get("index_option_type", "NORMAL")
            start = arguments.get("start")
            end = arguments.get("end")
            option_type = arguments.get("option_type", "ALL")
            option_cond_type = arguments.get("option_cond_type", "ALL")
            data_filter = arguments.get("data_filter")

            result = futu_client.get_option_chain(
                code=code,
                index_option_type=index_option_type,
                start=start,
                end=end,
                option_type=option_type,
                option_cond_type=option_cond_type,
                data_filter=data_filter
            )
            if isinstance(result, dict) and "error" in result:
                return [TextContent(type="text", text=f"❌ {result['error']}")]
            # 简单格式化输出
            output = f"🔗 期权链（{code}）\n" + "="*40 + "\n\n"
            for chain in result.get("optionChain", []):
                output += f"到期日: {chain.get('strikeTime', '')}\n"
                for opt in chain.get("option", []):
                    call = opt.get("call", {})
                    put = opt.get("put", {})
                    if call:
                        output += f"  CALL: {call['basic']['security']['code']} 行权价: {call['optionExData']['strikePrice']}\n"
                    if put:
                        output += f"  PUT:  {put['basic']['security']['code']} 行权价: {put['optionExData']['strikePrice']}\n"
                output += "\n"
            return [TextContent(type="text", text=output)]
            
        else:
            return [TextContent(
                type="text",
                text=f"❌ 未知的工具: {name}"
            )]
            
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"❌ 工具调用失败: {str(e)}"
        )]

async def run_server():
    """运行服务器"""
    try:
        print("🚀 启动富途修复版MCP服务器...", file=sys.stderr)
        
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            print("✅ 服务器已启动", file=sys.stderr)
            
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="futu-mcp-enhanced",
                    server_version="2.0.0-fixed",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    ),
                ),
            )
    
    except KeyboardInterrupt:
        print("🛑 服务器被中断", file=sys.stderr)
    except Exception as e:
        print(f"❌ 服务器错误: {e}", file=sys.stderr)
        raise

def main():
    """主函数"""
    try:
        print("🚀 启动富途MCP服务器 v2.0 - 修复版", file=sys.stderr)
        print("=" * 50, file=sys.stderr)
        
        # 初始化富途客户端
        if not init_futu_client():
            print("⚠️ 富途客户端初始化失败，将使用受限功能", file=sys.stderr)
        
        # 运行服务器
        asyncio.run(run_server())
        
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止", file=sys.stderr)
    except Exception as e:
        print(f"❌ 启动失败: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # 清理资源
        if futu_client:
            try:
                futu_client.close()
                print("✅ 富途客户端已关闭", file=sys.stderr)
            except:
                pass

if __name__ == "__main__":
    main() 