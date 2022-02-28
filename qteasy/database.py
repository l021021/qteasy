# coding=utf-8
# ======================================
# File:     database.py
# Author:   Jackie PENG
# Contact:  jackie.pengzhao@gmail.com
# Created:  2020-11-29
# Desc:
#   Local historical data management.
# ======================================

import pymysql
from sqlalchemy import create_engine
import pandas as pd
from os import path
import warnings

from concurrent.futures import ProcessPoolExecutor, as_completed

from .utilfuncs import AVAILABLE_ASSET_TYPES, progress_bar, time_str_format, nearest_market_trade_day
from .utilfuncs import str_to_list, regulate_date_format, TIME_FREQ_STRINGS
from .history import stack_dataframes
from .tsfuncs import acquire_data

AVAILABLE_DATA_FILE_TYPES = ['csv', 'hdf', 'feather', 'fth']
AVAILABLE_CHANNELS = ['df', 'csv', 'excel', 'tushare']
ADJUSTABLE_PRICE_TYPES = ['open', 'high', 'low', 'close']

""" 
这里定义AVAILABLE_TABLES 以及 TABLE_STRUCTURES
"""
DATA_MAPPING_TABLE = []

# 定义所有的数据表，并定义数据表的结构名称、数据表类型、资产类别、频率、tushare来源、更新规则
# 以下dict可以用于直接生成数据表，使用TABLE_SOURCE_MAPPINNG_COLUMNS作为列名
# comp_args、comp_type、val_boe均用于指导数据表内容的自动下载, 参见refill_table_data()函数的docstring
TABLE_SOURCE_MAPPING_COLUMNS = ['structure', 'desc', 'table_usage', 'asset_type', 'freq', 'tushare', 'fill_arg_name',
                                'fill_arg_type', 'arg_boe']
TABLE_SOURCE_MAPPING = {

    'trade_calendar':
        ['trade_calendar', 'desc', 'cal', 'none', 'none', 'trade_calendar', '', '', ''],

    'stock_basic':
        ['stock_basic', 'desc', 'basics', 'E', 'none', 'stock_basic', 'exchange', 'list', 'SSE,SZSE,BSE'],

    'stock_names':
        ['name_changes', 'desc', 'basics', 'E', 'none', 'name_change', '', '', ''],

    'index_basic':
        ['index_basic', 'desc', 'basics', 'IDX', 'none',  'index_basic', 'market', 'list',
         'SSE,MSCI,CSI,SZSE,CICC,SW,OTH'],

    'fund_basic':
        ['fund_basic', 'desc', 'basics', 'FD', 'none',  'fund_basic', 'market', 'list', 'E,O'],

    'future_basic':
        ['future_basic', 'desc', 'basics', 'FT', 'none', 'future_basic', 'exchange', 'list', 'CFFEX,DCE,CZCE,SHFE,INE'],

    'opt_basic':
        ['opt_basic', 'desc', 'basics', 'OPT', 'none', 'options_basic', 'exchange', 'list',
         'SSE,SZSE,CFFEX,DCE,CZCE,SHFE'],

    'stock_1min':
        ['bars', 'desc', 'data', 'E', '1min', 'mins', 'share', 'table_col', 'stock_basic,ts_code'],

    'stock_5min':
        ['bars', 'desc', 'data', 'E', '5min', 'mins', 'share', 'table_col', 'stock_basic,ts_code'],

    'stock_15min':
        ['bars', 'desc', 'data', 'E', '15min', 'mins', 'share', 'table_col', 'stock_basic,ts_code'],

    'stock_30min':
        ['bars', 'desc', 'data', 'E', '30min', 'mins', 'share', 'table_col', 'stock_basic,ts_code'],

    'stock_hour':
        ['bars', 'desc', 'data', 'E', '60min', 'mins', 'share', 'table_col', 'stock_basic,ts_code'],

    'stock_daily':
        ['bars', 'desc', 'data', 'E', 'd', 'daily', 'trade_date', 'datetime', '19901211,now'],

    'stock_weekly':
        ['bars', 'desc', 'data', 'E', 'w', 'weekly', 'trade_date', 'datetime', '19901221,now'],

    'stock_monthly':
        ['bars', 'desc', 'data', 'E', 'm', 'monthly', 'trade_date', 'datetime', '19901211,now'],

    'index_daily':
        ['bars', 'desc', 'data', 'IDX', 'd', 'index_daily', 'ts_code', 'table_col', 'fund_basic,ts_code'],

    'index_weekly':
        ['bars', 'desc', 'data', 'IDX', 'w', 'index_weekly', 'trade_date', 'datetime', '19910705,now'],

    'index_monthly':
        ['bars', 'desc', 'data', 'IDX', 'm', 'index_monthly', 'trade_date', 'datetime', ''],

    'fund_daily':
        ['bars', 'desc', 'data', 'FD', 'd', 'fund_daily', 'trade_date', 'datetime', '19980417,now'],

    'fund_nav':
        ['fund_nav', 'desc', 'data', 'FD', 'd', 'fund_net_value', 'trade_date', 'datetime', '20000107,now'],

    'fund_share':
        ['fund_share', 'desc', 'events', 'FD', 'none', 'fund_share', '', '', ''],

    'fund_manager':
        ['fund_manager', 'desc', 'events', 'FD', 'none', 'fund_manager', '', '', ''],

    'future_daily':
        ['future_daily', 'desc', 'data', 'FT', 'd', 'future_daily', 'trade_date', 'datetime', ''],

    'options_daily':
        ['options_daily', 'desc', 'data', 'OPT', 'd', 'options_daily', 'trade_date', 'datetime', ''],

    'stock_adj_factor':
        ['adj_factors', 'desc', 'adj', 'E', 'd', 'adj_factors', 'trade_date', 'datetime', ''],

    'fund_adj_factor':
        ['adj_factors', 'desc', 'adj', 'FD', 'd', 'fund_adj', 'trade_date', 'datetime', ''],

    'stock_indicator':
        ['stock_indicator', 'desc', 'data', 'E', 'd', 'daily_basic', 'trade_date', 'datetime', ''],

    'stock_indicator2':
        ['stock_indicator2', 'desc', 'data', 'E', 'd', 'daily_basic2', 'trade_date', 'datetime', ''],

    'index_indicator':
        ['index_indicator', 'desc', 'data', 'IDX', 'd', 'index_daily_basic', 'trade_date', 'datetime', ''],

    'index_weight':
        ['index_weight', 'desc', 'comp', 'IDX', 'm', 'composite', '', '', ''],

    'income':
        ['income', 'desc', 'data', 'E', 'q', 'income', '', '', ''],

    'balance':
        ['balance', 'desc', 'data', 'E', 'q', 'balance', '', '', ''],

    'cashflow':
        ['cashflow', 'desc', 'data', 'E', 'q', 'cashflow', '', '', ''],

    'financial':
        ['financial', 'desc', 'data', 'E', 'q', 'indicators', '', '', ''],

    'forecast':
        ['forecast', 'desc', 'data', 'E', 'q', 'forecast', '', '', ''],

    'express':
        ['express', 'desc', 'data', 'E', 'q', 'express', '', '', ''],

}
# 定义Table structure，定义所有数据表的列名、数据类型、限制、主键以及注释，用于定义数据表的结构
TABLE_STRUCTURES = {

    'trade_calendar':   {'columns':    ['exchange', 'cal_date', 'is_open', 'pretrade_date'],
                         'dtypes':     ['varchar(9)', 'date', 'tinyint', 'date'],
                         'remarks':    ['交易所', '日期', '是否交易', '上一交易日'],
                         'prime_keys': [0, 1]},

    'stock_basic':      {'columns':    ['ts_code', 'symbol', 'name', 'area', 'industry', 'fullname', 'enname',
                                        'cnspell', 'market', 'exchange', 'curr_type', 'list_status', 'list_date',
                                        'delist_date', 'is_hs'],
                         'dtypes':     ['varchar(9)', 'varchar(6)', 'varchar(20)', 'varchar(10)', 'varchar(10)',
                                        'varchar(50)', 'varchar(80)', 'varchar(40)', 'varchar(6)', 'varchar(6)',
                                        'varchar(6)', 'varchar(4)', 'date', 'date', 'varchar(2)'],
                         'remarks':    ['证券代码', '股票代码', '股票名称', '地域', '所属行业', '股票全称', '英文全称', '拼音缩写',
                                        '市场类型', '交易所代码', '交易货币', '上市状态', '上市日期', '退市日期', '是否沪深港通'],
                         'prime_keys': [0]},

    'name_changes':     {'columns':    ['ts_code', 'start_date', 'name', 'end_date', 'ann_date', 'change_reason'],
                         'dtypes':     ['varchar(9)', 'date', 'varchar(8)', 'date', 'date', 'varchar(10)'],
                         'remarks':    ['证券代码', '开始日期', '证券名称', '结束日期', '公告日期', '变更原因'],
                         'prime_keys': [0, 1]},

    'index_basic':      {'columns':    ['ts_code', 'name', 'fullname', 'market', 'publisher', 'index_type', 'category',
                                        'base_date', 'base_point', 'list_date', 'weight_rule', 'desc', 'exp_date'],
                         'dtypes':     ['varchar(24)', 'varchar(40)', 'varchar(80)', 'varchar(8)', 'varchar(30)',
                                        'varchar(30)', 'varchar(6)', 'date', 'float', 'date', 'text', 'text', 'date'],
                         'remarks':    ['证券代码', '简称', '指数全称', '市场', '发布方', '指数风格', '指数类别', '基期', '基点',
                                        '发布日期', '加权方式', '描述', '终止日期'],
                         'prime_keys': [0]},

    'fund_basic':       {'columns':    ['ts_code', 'name', 'management', 'custodian', 'fund_type', 'found_date',
                                        'due_date', 'list_date', 'issue_date', 'delist_date', 'issue_amount', 'm_fee',
                                        'c_fee', 'duration_year', 'p_value', 'min_amount', 'exp_return', 'benchmark',
                                        'status', 'invest_type', 'type', 'trustee', 'purc_startdate', 'redm_startdate',
                                        'market'],
                         'dtypes':     ['varchar(24)', 'varchar(24)', 'varchar(20)', 'varchar(20)', 'varchar(8)', 'date',
                                        'date', 'date', 'date', 'date', 'float', 'float', 'float', 'float', 'float',
                                        'float', 'float', 'text', 'varchar(2)', 'varchar(10)', 'varchar(10)',
                                        'varchar(10)', 'date', 'date', 'varchar(2)'],
                         'remarks':    ['证券代码', '简称', '管理人', '托管人', '投资类型', '成立日期', '到期日期', '上市时间',
                                        '发行日期', '退市日期', '发行份额(亿)', '管理费', '托管费', '存续期', '面值',
                                        '起点金额(万元)', '预期收益率', '业绩比较基准', '存续状态D摘牌 I发行 L已上市',
                                        '投资风格', '基金类型', '受托人', '日常申购起始日', '日常赎回起始日', 'E场内O场外'],
                         'prime_keys': [0]},

    'future_basic':     {'columns':    ['ts_code', 'symbol', 'exchange', 'name', 'fut_code', 'multiplier', 'trade_unit',
                                        'per_unit', 'quote_unit', 'quote_unit_desc', 'd_mode_desc', 'list_date',
                                        'delist_date', 'd_month', 'last_ddate', 'trade_time_desc'],
                         'dtypes':     ['varchar(24)', 'varchar(12)', 'varchar(8)', 'varchar(40)', 'varchar(12)',
                                        'float', 'varchar(4)', 'float', 'varchar(4)', 'text', 'text', 'date', 'date',
                                        'varchar(6)', 'date', 'varchar(40)'],
                         'remarks':    ['证券代码', '交易标识', '交易市场', '中文简称', '合约产品代码', '合约乘数',
                                        '交易计量单位', '交易单位(每手)', '报价单位', '最小报价单位说明', '交割方式说明',
                                        '上市日期', '最后交易日期', '交割月份', '最后交割日', '交易时间说明'],
                         'prime_keys': [0]},

    'opt_basic':        {'columns':    ['ts_code', 'exchange', 'name', 'per_unit', 'opt_code', 'opt_type', 'call_put',
                                        'exercise_type', 'exercise_price', 's_month', 'maturity_date', 'list_price',
                                        'list_date', 'delist_date', 'last_edate', 'last_ddate', 'quote_unit',
                                        'min_price_chg'],
                         'dtypes':     ['varchar(24)', 'varchar(6)', 'varchar(50)', 'varchar(10)', 'varchar(12)',
                                        'varchar(6)', 'varchar(6)', 'varchar(6)', 'float', 'varchar(8)', 'date',
                                        'float', 'date', 'date', 'date', 'date', 'varchar(6)', 'varchar(6)'],
                         'remarks':    ['证券代码', '交易市场', '合约名称', '合约单位', '标准合约代码', '合约类型', '期权类型',
                                        '行权方式', '行权价格', '结算月', '到期日', '挂牌基准价', '开始交易日期',
                                        '最后交易日期', '最后行权日期', '最后交割日期', '报价单位', '最小价格波幅'],
                         'prime_keys': [0]},

    # 下面的bars表适用于stock_1min / stock_5min / stock_30min / stock_hourly /
    # stock_daily / stock_weekly / stock_monthly / index_daily / index_weekly /
    # index_monthly / fund_daily 等数据表
    # 用于股票、指数以及部分基金的K线数据结构，包括分钟、小时、天、周和月k线，更新时按时间下载，更新时按前两列的内容更新去重
    'bars':             {'columns':    ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close', 'change',
                                        'pct_chg', 'vol', 'amount'],
                         'dtypes':     ['varchar(20)', 'date', 'float', 'float', 'float', 'float', 'float', 'float',
                                        'float', 'double', 'double'],
                         'remarks':    ['证券代码', '交易日期', '开盘价', '最高价', '最低价', '收盘价', '昨收价', '涨跌额',
                                        '涨跌幅', '成交量 （手）', '成交额 （千元）'],
                         'prime_keys': [0, 1]},

    # 以下adj_factors表结构可以同时用于stock_adj_factors / fund_adj_factors两张表
    'adj_factors':      {'columns':    ['ts_code', 'trade_date', 'adj_factor'],
                         'dtypes':     ['varchar(9)', 'date', 'double'],
                         'remarks':    ['证券代码', '交易日期', '复权因子'],
                         'prime_keys': [0, 1]},

    'fund_nav':         {'columns':    ['ts_code', 'nav_date', 'ann_date', 'unit_nav', 'accum_nav', 'accum_div',
                                        'net_asset', 'total_netasset', 'adj_nav', 'update_flag'],
                         'dtypes':     ['varchar(24)', 'date', 'date', 'float', 'float', 'float', 'double', 'double',
                                        'float', 'varchar(2)'],
                         'remarks':    ['TS代码', '净值日期', '公告日期', '单位净值', '累计净值', '累计分红', '资产净值',
                                        '合计资产净值', '复权单位净值', '更新标记'],
                         'prime_keys': [0, 1]},

    'fund_share':       {'columns':    ['ts_code', 'trade_date', 'fd_share'],
                         'dtypes':     ['varchar(9)', 'date', 'float'],
                         'remarks':    ['证券代码', '变动日期，格式YYYYMMDD', '基金份额（万）'],
                         'prime_keys': [0, 1]},

    'fund_manager':     {'columns':    ['ts_code', 'ann_date', 'name', 'gender', 'birth_year', 'edu', 'nationality',
                                        'begin_date', 'end_date', 'resume'],
                         'dtypes':     ['varchar(9)', 'date', 'varchar(6)', 'varchar(2)', 'year', 'varchar(30)',
                                        'varchar(4)', 'date', 'date', 'text'],
                         'remarks':    ['证券代码', '公告日期', '基金经理姓名', '性别', '出生年份', '学历', '国籍', '任职日期',
                                        '离任日期', '简历'],
                         'prime_keys': [0, 1]},

    'future_daily':     {'columns':    ['ts_code', 'trade_date', 'pre_close', 'pre_settle', 'open', 'high', 'low',
                                        'close', 'settle', 'change1', 'change2', 'vol', 'amount', 'oi', 'oi_chg',
                                        'delv_settle'],
                         'dtypes':     ['varchar(20)', 'date', 'float', 'float', 'float', 'float', 'float', 'float',
                                        'float', 'float', 'float', 'double', 'double', 'double', 'double', 'float'],
                         'remarks':    ['证券代码', '交易日期', '昨收盘价', '昨结算价', '开盘价', '最高价', '最低价',
                                        '收盘价', '结算价', '涨跌1 收盘价-昨结算价', '涨跌2 结算价-昨结算价', '成交量(手)',
                                        '成交金额(万元)', '持仓量(手)', '持仓量变化', '交割结算价'],
                         'prime_keys': [0, 1]},

    'options_daily':    {'columns':    ['ts_code', 'trade_date', 'exchange', 'pre_settle', 'pre_close', 'open', 'high',
                                        'low', 'close', 'settle', 'vol', 'amount', 'oi'],
                         'dtypes':     ['varchar(20)', 'date', 'varchar(8)', 'float', 'float', 'float', 'float',
                                        'float', 'float', 'float', 'double', 'double', 'double'],
                         'remarks':    ['证券代码', '交易日期', '交易市场', '昨结算价', '昨收盘价', '开盘价', '最高价', '最低价',
                                        '收盘价', '结算价', '成交量(手)', '成交金额(万元)', '持仓量(手)'],
                         'prime_keys': [0, 1]},

    'stock_indicator':  {'columns':    ['ts_code', 'trade_date', 'close', 'turnover_rate', 'turnover_rate_f',
                                        'volume_ratio', 'pe', 'pe_ttm', 'pb', 'ps', 'ps_ttm', 'dv_ratio', 'dv_ttm',
                                        'total_share', 'float_share', 'free_share', 'total_mv', 'circ_mv'],
                         'dtypes':     ['varchar(9)', 'date', 'float', 'float', 'float', 'float', 'float', 'float',
                                        'float', 'float', 'float', 'float', 'float', 'double', 'double', 'double',
                                        'double', 'double'],
                         'remarks':    ['证券代码', '交易日期', '当日收盘价', '换手率（%）', '换手率（自由流通股）', '量比',
                                        '市盈率（总市值/净利润， 亏损的PE为空）', '市盈率（TTM，亏损的PE为空）',
                                        '市净率（总市值/净资产）', '市销率', '市销率（TTM）', '股息率 （%）',
                                        '股息率（TTM）（%）', '总股本 （万股）', '流通股本 （万股）', '自由流通股本 （万）',
                                        '总市值 （万元）', '流通市值（万元）'],
                         'prime_keys': [0, 1]},

    'stock_indicator2': {'columns':    ['ts_code', 'trade_date', 'vol_ratio', 'turn_over', 'swing',
                                        'selling', 'buying', 'total_share', 'float_share', 'pe',
                                        'float_mv', 'total_mv', 'avg_price', 'strength', 'activity', 'avg_turnover',
                                        'attack', 'interval_3', 'interval_6'],
                         'dtypes':     ['varchar(9)', 'date', 'float', 'float', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'float', 'float'],
                         'remarks':    ['证券代码', '交易日期', '量比', '换手率', '振幅', '**成交量',
                                        '外盘（主动买， 手）', '总股本(亿)', '流通股本(亿)', '市盈(动)',
                                        '流通市值', '总市值', '平均价', '强弱度(%)', '活跃度(%)', '笔换手', '攻击波(%)',
                                        '近3月涨幅', '近6月涨幅'],
                         'prime_keys': [0, 1]},

    'index_indicator':  {'columns':    ['ts_code', 'trade_date', 'total_mv', 'float_mv', 'total_share', 'float_share',
                                        'free_share', 'turnover_rate', 'turnover_rate_f', 'pe', 'pe_ttm', 'pb'],
                         'dtypes':     ['varchar(9)', 'date', 'double', 'double', 'double', 'double', 'double', 'float',
                                        'float', 'float', 'float', 'float'],
                         'remarks':    ['证券代码', '交易日期', '当日总市值（元）', '当日流通市值（元）', '当日总股本（股）',
                                        '当日流通股本（股）', '当日自由流通股本（股）', '换手率', '换手率(基于自由流通股本)',
                                        '市盈率', '市盈率TTM', '市净率'],
                         'prime_keys': [0, 1]},

    'index_weight':     {'columns':    ['index_code', 'trade_date', 'con_code', 'weight'],
                         'dtypes':     ['varchar(24)', 'date', 'varchar(9)', 'float'],
                         'remarks':    ['指数代码', '交易日期', '成分代码', '权重'],
                         'prime_keys': [0, 1]},

    'income':           {'columns':    ['ts_code', 'end_date', 'ann_date', 'f_ann_date', 'report_type', 'comp_type',
                                        'end_type', 'basic_eps', 'diluted_eps', 'total_revenue', 'revenue',
                                        'int_income', 'prem_earned', 'comm_income', 'n_commis_income', 'n_oth_income',
                                        'n_oth_b_income', 'prem_income', 'out_prem', 'une_prem_reser', 'reins_income',
                                        'n_sec_tb_income', 'n_sec_uw_income', 'n_asset_mg_income', 'oth_b_income',
                                        'fv_value_chg_gain', 'invest_income', 'ass_invest_income', 'forex_gain',
                                        'total_cogs', 'oper_cost', 'int_exp', 'comm_exp', 'biz_tax_surchg', 'sell_exp',
                                        'admin_exp', 'fin_exp', 'assets_impair_loss', 'prem_refund', 'compens_payout',
                                        'reser_insur_liab', 'div_payt', 'reins_exp', 'oper_exp', 'compens_payout_refu',
                                        'insur_reser_refu', 'reins_cost_refund', 'other_bus_cost', 'operate_profit',
                                        'non_oper_income', 'non_oper_exp', 'nca_disploss', 'total_profit',
                                        'income_tax', 'n_income', 'n_income_attr_p', 'minority_gain',
                                        'oth_compr_income', 't_compr_income', 'compr_inc_attr_p', 'compr_inc_attr_m_s',
                                        'ebit', 'ebitda', 'insurance_exp', 'undist_profit', 'distable_profit',
                                        'rd_exp', 'fin_exp_int_exp', 'fin_exp_int_inc', 'transfer_surplus_rese',
                                        'transfer_housing_imprest', 'transfer_oth', 'adj_lossgain',
                                        'withdra_legal_surplus', 'withdra_legal_pubfund', 'withdra_biz_devfund',
                                        'withdra_rese_fund', 'withdra_oth_ersu', 'workers_welfare',
                                        'distr_profit_shrhder', 'prfshare_payable_dvd', 'comshare_payable_dvd',
                                        'capit_comstock_div', 'net_after_nr_lp_correct', 'credit_impa_loss',
                                        'net_expo_hedging_benefits', 'oth_impair_loss_assets', 'total_opcost',
                                        'amodcost_fin_assets', 'oth_income', 'asset_disp_income',
                                        'continued_net_profit', 'end_net_profit', 'update_flag'],
                         'dtypes':     ['varchar(9)', 'date', 'date', 'date', 'varchar(6)', 'varchar(6)', 'varchar(6)',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'varchar(4)'],
                         'remarks':    ['证券代码', '报告期', '公告日期', '实际公告日期', '报告类型 见底部表',
                                        '公司类型(1一般工商业2银行3保险4证券)', '报告期类型', '基本每股收益', '稀释每股收益',
                                        '营业总收入', '营业收入', '利息收入', '已赚保费', '手续费及佣金收入', '手续费及佣金净收入',
                                        '其他经营净收益', '加:其他业务净收益', '保险业务收入', '减:分出保费',
                                        '提取未到期责任准备金', '其中:分保费收入', '代理买卖证券业务净收入', '证券承销业务净收入',
                                        '受托客户资产管理业务净收入', '其他业务收入', '加:公允价值变动净收益', '加:投资净收益',
                                        '其中:对联营企业和合营企业的投资收益', '加:汇兑净收益', '营业总成本', '减:营业成本',
                                        '减:利息支出', '减:手续费及佣金支出', '减:营业税金及附加', '减:销售费用', '减:管理费用',
                                        '减:财务费用', '减:资产减值损失', '退保金', '赔付总支出', '提取保险责任准备金',
                                        '保户红利支出', '分保费用', '营业支出', '减:摊回赔付支出', '减:摊回保险责任准备金',
                                        '减:摊回分保费用', '其他业务成本', '营业利润', '加:营业外收入', '减:营业外支出',
                                        '其中:减:非流动资产处置净损失', '利润总额', '所得税费用', '净利润(含少数股东损益)',
                                        '净利润(不含少数股东损益)', '少数股东损益', '其他综合收益', '综合收益总额',
                                        '归属于母公司(或股东)的综合收益总额', '归属于少数股东的综合收益总额', '息税前利润',
                                        '息税折旧摊销前利润', '保险业务支出', '年初未分配利润', '可分配利润', '研发费用',
                                        '财务费用:利息费用', '财务费用:利息收入', '盈余公积转入', '住房周转金转入', '其他转入',
                                        '调整以前年度损益', '提取法定盈余公积', '提取法定公益金', '提取企业发展基金',
                                        '提取储备基金', '提取任意盈余公积金', '职工奖金福利', '可供股东分配的利润',
                                        '应付优先股股利', '应付普通股股利', '转作股本的普通股股利',
                                        '扣除非经常性损益后的净利润（更正前）', '信用减值损失', '净敞口套期收益',
                                        '其他资产减值损失', '营业总成本（二）', '以摊余成本计量的金融资产终止确认收益',
                                        '其他收益', '资产处置收益', '持续经营净利润', '终止经营净利润', '更新标识'],
                         'prime_keys': [0, 1]},

    'balance':          {'columns':    ['ts_code', 'end_date', 'ann_date', 'f_ann_date', 'report_type', 'comp_type',
                                        'end_type', 'total_share', 'cap_rese', 'undistr_porfit', 'surplus_rese',
                                        'special_rese', 'money_cap', 'trad_asset', 'notes_receiv', 'accounts_receiv',
                                        'oth_receiv', 'prepayment', 'div_receiv', 'int_receiv', 'inventories',
                                        'amor_exp', 'nca_within_1y', 'sett_rsrv', 'loanto_oth_bank_fi',
                                        'premium_receiv', 'reinsur_receiv', 'reinsur_res_receiv', 'pur_resale_fa',
                                        'oth_cur_assets', 'total_cur_assets', 'fa_avail_for_sale', 'htm_invest',
                                        'lt_eqt_invest', 'invest_real_estate', 'time_deposits', 'oth_assets', 'lt_rec',
                                        'fix_assets', 'cip', 'const_materials', 'fixed_assets_disp',
                                        'produc_bio_assets', 'oil_and_gas_assets', 'intan_assets', 'r_and_d',
                                        'goodwill', 'lt_amor_exp', 'defer_tax_assets', 'decr_in_disbur', 'oth_nca',
                                        'total_nca', 'cash_reser_cb', 'depos_in_oth_bfi', 'prec_metals',
                                        'deriv_assets', 'rr_reins_une_prem', 'rr_reins_outstd_cla',
                                        'rr_reins_lins_liab', 'rr_reins_lthins_liab', 'refund_depos',
                                        'ph_pledge_loans', 'refund_cap_depos', 'indep_acct_assets', 'client_depos',
                                        'client_prov', 'transac_seat_fee', 'invest_as_receiv', 'total_assets',
                                        'lt_borr', 'st_borr', 'cb_borr', 'depos_ib_deposits', 'loan_oth_bank',
                                        'trading_fl', 'notes_payable', 'acct_payable', 'adv_receipts',
                                        'sold_for_repur_fa', 'comm_payable', 'payroll_payable', 'taxes_payable',
                                        'int_payable', 'div_payable', 'oth_payable', 'acc_exp', 'deferred_inc',
                                        'st_bonds_payable', 'payable_to_reinsurer', 'rsrv_insur_cont',
                                        'acting_trading_sec', 'acting_uw_sec', 'non_cur_liab_due_1y', 'oth_cur_liab',
                                        'total_cur_liab', 'bond_payable', 'lt_payable', 'specific_payables',
                                        'estimated_liab', 'defer_tax_liab', 'defer_inc_non_cur_liab', 'oth_ncl',
                                        'total_ncl', 'depos_oth_bfi', 'deriv_liab', 'depos', 'agency_bus_liab',
                                        'oth_liab', 'prem_receiv_adva', 'depos_received', 'ph_invest',
                                        'reser_une_prem', 'reser_outstd_claims', 'reser_lins_liab',
                                        'reser_lthins_liab', 'indept_acc_liab', 'pledge_borr', 'indem_payable',
                                        'policy_div_payable', 'total_liab', 'treasury_share', 'ordin_risk_reser',
                                        'forex_differ', 'invest_loss_unconf', 'minority_int',
                                        'total_hldr_eqy_exc_min_int', 'total_hldr_eqy_inc_min_int',
                                        'total_liab_hldr_eqy', 'lt_payroll_payable', 'oth_comp_income',
                                        'oth_eqt_tools', 'oth_eqt_tools_p_shr', 'lending_funds', 'acc_receivable',
                                        'st_fin_payable', 'payables', 'hfs_assets', 'hfs_sales', 'cost_fin_assets',
                                        'fair_value_fin_assets', 'cip_total', 'oth_pay_total', 'long_pay_total',
                                        'debt_invest', 'oth_debt_invest', 'oth_eq_invest', 'oth_illiq_fin_assets',
                                        'oth_eq_ppbond', 'receiv_financing', 'use_right_assets', 'lease_liab',
                                        'contract_assets', 'contract_liab', 'accounts_receiv_bill', 'accounts_pay',
                                        'oth_rcv_total', 'fix_assets_total', 'update_flag'],
                         'dtypes':     ['varchar(9)', 'date', 'date', 'date', 'varchar(10)', 'varchar(10)',
                                        'varchar(10)', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'varchar(2)'],
                         'remarks':    ['证券代码', '报告期', '公告日期', '实际公告日期', '报表类型', '公司类型', '报告期类型',
                                        '期末总股本', '资本公积金', '未分配利润', '盈余公积金', '专项储备', '货币资金',
                                        '交易性金融资产', '应收票据', '应收账款', '其他应收款', '预付款项', '应收股利',
                                        '应收利息', '存货', '长期待摊费用', '一年内到期的非流动资产', '结算备付金', '拆出资金',
                                        '应收保费', '应收分保账款', '应收分保合同准备金', '买入返售金融资产', '其他流动资产',
                                        '流动资产合计', '可供出售金融资产', '持有至到期投资', '长期股权投资', '投资性房地产',
                                        '定期存款', '其他资产', '长期应收款', '固定资产', '在建工程', '工程物资', '固定资产清理',
                                        '生产性生物资产', '油气资产', '无形资产', '研发支出', '商誉', '长期待摊费用',
                                        '递延所得税资产', '发放贷款及垫款', '其他非流动资产', '非流动资产合计',
                                        '现金及存放中央银行款项', '存放同业和其它金融机构款项', '贵金属', '衍生金融资产',
                                        '应收分保未到期责任准备金', '应收分保未决赔款准备金', '应收分保寿险责任准备金',
                                        '应收分保长期健康险责任准备金', '存出保证金', '保户质押贷款', '存出资本保证金',
                                        '独立账户资产', '其中：客户资金存款', '其中：客户备付金', '其中:交易席位费',
                                        '应收款项类投资', '资产总计', '长期借款', '短期借款', '向中央银行借款',
                                        '吸收存款及同业存放', '拆入资金', '交易性金融负债', '应付票据', '应付账款', '预收款项',
                                        '卖出回购金融资产款', '应付手续费及佣金', '应付职工薪酬', '应交税费', '应付利息',
                                        '应付股利', '其他应付款', '预提费用', '递延收益', '应付短期债券', '应付分保账款',
                                        '保险合同准备金', '代理买卖证券款', '代理承销证券款', '一年内到期的非流动负债',
                                        '其他流动负债', '流动负债合计', '应付债券', '长期应付款', '专项应付款', '预计负债',
                                        '递延所得税负债', '递延收益-非流动负债', '其他非流动负债', '非流动负债合计',
                                        '同业和其它金融机构存放款项', '衍生金融负债', '吸收存款', '代理业务负债', '其他负债',
                                        '预收保费', '存入保证金', '保户储金及投资款', '未到期责任准备金', '未决赔款准备金',
                                        '寿险责任准备金', '长期健康险责任准备金', '独立账户负债', '其中:质押借款', '应付赔付款',
                                        '应付保单红利', '负债合计', '减:库存股', '一般风险准备', '外币报表折算差额',
                                        '未确认的投资损失', '少数股东权益', '股东权益合计(不含少数股东权益)',
                                        '股东权益合计(含少数股东权益)', '负债及股东权益总计', '长期应付职工薪酬', '其他综合收益',
                                        '其他权益工具', '其他权益工具(优先股)', '融出资金', '应收款项', '应付短期融资款',
                                        '应付款项', '持有待售的资产', '持有待售的负债', '以摊余成本计量的金融资产',
                                        '以公允价值计量且其变动计入其他综合收益的金融资产', '在建工程(合计)(元)',
                                        '其他应付款(合计)(元)', '长期应付款(合计)(元)', '债权投资(元)', '其他债权投资(元)',
                                        '其他权益工具投资(元)', '其他非流动金融资产(元)', '其他权益工具:永续债(元)',
                                        '应收款项融资', '使用权资产', '租赁负债', '合同资产', '合同负债', '应收票据及应收账款',
                                        '应付票据及应付账款', '其他应收款(合计)（元）', '固定资产(合计)(元)', '更新标识'],
                         'prime_keys': [0, 1]},

    'cashflow':         {'columns':    ['ts_code', 'end_date', 'ann_date', 'f_ann_date', 'comp_type', 'report_type',
                                        'end_type', 'net_profit', 'finan_exp', 'c_fr_sale_sg', 'recp_tax_rends',
                                        'n_depos_incr_fi', 'n_incr_loans_cb', 'n_inc_borr_oth_fi',
                                        'prem_fr_orig_contr', 'n_incr_insured_dep', 'n_reinsur_prem',
                                        'n_incr_disp_tfa', 'ifc_cash_incr', 'n_incr_disp_faas',
                                        'n_incr_loans_oth_bank', 'n_cap_incr_repur', 'c_fr_oth_operate_a',
                                        'c_inf_fr_operate_a', 'c_paid_goods_s', 'c_paid_to_for_empl',
                                        'c_paid_for_taxes', 'n_incr_clt_loan_adv', 'n_incr_dep_cbob',
                                        'c_pay_claims_orig_inco', 'pay_handling_chrg', 'pay_comm_insur_plcy',
                                        'oth_cash_pay_oper_act', 'st_cash_out_act', 'n_cashflow_act',
                                        'oth_recp_ral_inv_act', 'c_disp_withdrwl_invest', 'c_recp_return_invest',
                                        'n_recp_disp_fiolta', 'n_recp_disp_sobu', 'stot_inflows_inv_act',
                                        'c_pay_acq_const_fiolta', 'c_paid_invest', 'n_disp_subs_oth_biz',
                                        'oth_pay_ral_inv_act', 'n_incr_pledge_loan', 'stot_out_inv_act',
                                        'n_cashflow_inv_act', 'c_recp_borrow', 'proc_issue_bonds',
                                        'oth_cash_recp_ral_fnc_act', 'stot_cash_in_fnc_act', 'free_cashflow',
                                        'c_prepay_amt_borr', 'c_pay_dist_dpcp_int_exp', 'incl_dvd_profit_paid_sc_ms',
                                        'oth_cashpay_ral_fnc_act', 'stot_cashout_fnc_act', 'n_cash_flows_fnc_act',
                                        'eff_fx_flu_cash', 'n_incr_cash_cash_equ', 'c_cash_equ_beg_period',
                                        'c_cash_equ_end_period', 'c_recp_cap_contrib', 'incl_cash_rec_saims',
                                        'uncon_invest_loss', 'prov_depr_assets', 'depr_fa_coga_dpba',
                                        'amort_intang_assets', 'lt_amort_deferred_exp', 'decr_deferred_exp',
                                        'incr_acc_exp', 'loss_disp_fiolta', 'loss_scr_fa', 'loss_fv_chg',
                                        'invest_loss', 'decr_def_inc_tax_assets', 'incr_def_inc_tax_liab',
                                        'decr_inventories', 'decr_oper_payable', 'incr_oper_payable', 'others',
                                        'im_net_cashflow_oper_act', 'conv_debt_into_cap',
                                        'conv_copbonds_due_within_1y', 'fa_fnc_leases', 'im_n_incr_cash_equ',
                                        'net_dism_capital_add', 'net_cash_rece_sec', 'credit_impa_loss',
                                        'use_right_asset_dep', 'oth_loss_asset', 'end_bal_cash', 'beg_bal_cash',
                                        'end_bal_cash_equ', 'beg_bal_cash_equ', 'update_flag'],
                         'dtypes':     ['varchar(9)', 'date', 'date', 'date', 'varchar(10)', 'varchar(10)',
                                        'varchar(10)', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'varchar(2)'],
                         'remarks':    ['证券代码', '报告期', '公告日期', '实际公告日期', '公司类型', '报表类型', '报告期类型',
                                        '净利润', '财务费用', '销售商品、提供劳务收到的现金', '收到的税费返还',
                                        '客户存款和同业存放款项净增加额', '向中央银行借款净增加额', '向其他金融机构拆入资金净增加额',
                                        '收到原保险合同保费取得的现金', '保户储金净增加额', '收到再保业务现金净额',
                                        '处置交易性金融资产净增加额', '收取利息和手续费净增加额', '处置可供出售金融资产净增加额',
                                        '拆入资金净增加额', '回购业务资金净增加额', '收到其他与经营活动有关的现金',
                                        '经营活动现金流入小计', '购买商品、接受劳务支付的现金', '支付给职工以及为职工支付的现金',
                                        '支付的各项税费', '客户贷款及垫款净增加额', '存放央行和同业款项净增加额',
                                        '支付原保险合同赔付款项的现金', '支付手续费的现金', '支付保单红利的现金',
                                        '支付其他与经营活动有关的现金', '经营活动现金流出小计', '经营活动产生的现金流量净额',
                                        '收到其他与投资活动有关的现金', '收回投资收到的现金', '取得投资收益收到的现金',
                                        '处置固定资产、无形资产和其他长期资产收回的现金净额',
                                        '处置子公司及其他营业单位收到的现金净额', '投资活动现金流入小计',
                                        '购建固定资产、无形资产和其他长期资产支付的现金', '投资支付的现金',
                                        '取得子公司及其他营业单位支付的现金净额', '支付其他与投资活动有关的现金',
                                        '质押贷款净增加额', '投资活动现金流出小计', '投资活动产生的现金流量净额',
                                        '取得借款收到的现金', '发行债券收到的现金', '收到其他与筹资活动有关的现金',
                                        '筹资活动现金流入小计', '企业自由现金流量', '偿还债务支付的现金',
                                        '分配股利、利润或偿付利息支付的现金', '其中:子公司支付给少数股东的股利、利润',
                                        '支付其他与筹资活动有关的现金', '筹资活动现金流出小计', '筹资活动产生的现金流量净额',
                                        '汇率变动对现金的影响', '现金及现金等价物净增加额', '期初现金及现金等价物余额',
                                        '期末现金及现金等价物余额', '吸收投资收到的现金', '其中:子公司吸收少数股东投资收到的现金',
                                        '未确认投资损失', '加:资产减值准备', '固定资产折旧、油气资产折耗、生产性生物资产折旧',
                                        '无形资产摊销', '长期待摊费用摊销', '待摊费用减少', '预提费用增加',
                                        '处置固定、无形资产和其他长期资产的损失', '固定资产报废损失', '公允价值变动损失',
                                        '投资损失', '递延所得税资产减少', '递延所得税负债增加', '存货的减少',
                                        '经营性应收项目的减少', '经营性应付项目的增加', '其他',
                                        '经营活动产生的现金流量净额(间接法)', '债务转为资本', '一年内到期的可转换公司债券',
                                        '融资租入固定资产', '现金及现金等价物净增加额(间接法)', '拆出资金净增加额',
                                        '代理买卖证券收到的现金净额(元)', '信用减值损失', '使用权资产折旧', '其他资产减值损失',
                                        '现金的期末余额', '减:现金的期初余额', '加:现金等价物的期末余额',
                                        '减:现金等价物的期初余额', '更新标志(1最新）'],
                         'prime_keys': [0, 1]},

    'financial':        {'columns':    ['ts_code', 'end_date', 'ann_date', 'eps', 'dt_eps', 'total_revenue_ps',
                                        'revenue_ps', 'capital_rese_ps', 'surplus_rese_ps', 'undist_profit_ps',
                                        'extra_item', 'profit_dedt', 'gross_margin', 'current_ratio', 'quick_ratio',
                                        'cash_ratio', 'invturn_days', 'arturn_days', 'inv_turn', 'ar_turn', 'ca_turn',
                                        'fa_turn', 'assets_turn', 'op_income', 'valuechange_income', 'interst_income',
                                        'daa', 'ebit', 'ebitda', 'fcff', 'fcfe', 'current_exint', 'noncurrent_exint',
                                        'interestdebt', 'netdebt', 'tangible_asset', 'working_capital',
                                        'networking_capital', 'invest_capital', 'retained_earnings', 'diluted2_eps',
                                        'bps', 'ocfps', 'retainedps', 'cfps', 'ebit_ps', 'fcff_ps', 'fcfe_ps',
                                        'netprofit_margin', 'grossprofit_margin', 'cogs_of_sales', 'expense_of_sales',
                                        'profit_to_gr', 'saleexp_to_gr', 'adminexp_of_gr', 'finaexp_of_gr',
                                        'impai_ttm', 'gc_of_gr', 'op_of_gr', 'ebit_of_gr', 'roe', 'roe_waa', 'roe_dt',
                                        'roa', 'npta', 'roic', 'roe_yearly', 'roa2_yearly', 'roe_avg',
                                        'opincome_of_ebt', 'investincome_of_ebt', 'n_op_profit_of_ebt', 'tax_to_ebt',
                                        'dtprofit_to_profit', 'salescash_to_or', 'ocf_to_or', 'ocf_to_opincome',
                                        'capitalized_to_da', 'debt_to_assets', 'assets_to_eqt', 'dp_assets_to_eqt',
                                        'ca_to_assets', 'nca_to_assets', 'tbassets_to_totalassets', 'int_to_talcap',
                                        'eqt_to_talcapital', 'currentdebt_to_debt', 'longdeb_to_debt',
                                        'ocf_to_shortdebt', 'debt_to_eqt', 'eqt_to_debt', 'eqt_to_interestdebt',
                                        'tangibleasset_to_debt', 'tangasset_to_intdebt', 'tangibleasset_to_netdebt',
                                        'ocf_to_debt', 'ocf_to_interestdebt', 'ocf_to_netdebt', 'ebit_to_interest',
                                        'longdebt_to_workingcapital', 'ebitda_to_debt', 'turn_days', 'roa_yearly',
                                        'roa_dp', 'fixed_assets', 'profit_prefin_exp', 'non_op_profit', 'op_to_ebt',
                                        'nop_to_ebt', 'ocf_to_profit', 'cash_to_liqdebt',
                                        'cash_to_liqdebt_withinterest', 'op_to_liqdebt', 'op_to_debt', 'roic_yearly',
                                        'total_fa_trun', 'profit_to_op', 'q_opincome', 'q_investincome', 'q_dtprofit',
                                        'q_eps', 'q_netprofit_margin', 'q_gsprofit_margin', 'q_exp_to_sales',
                                        'q_profit_to_gr', 'q_saleexp_to_gr', 'q_adminexp_to_gr', 'q_finaexp_to_gr',
                                        'q_impair_to_gr_ttm', 'q_gc_to_gr', 'q_op_to_gr', 'q_roe', 'q_dt_roe',
                                        'q_npta', 'q_opincome_to_ebt', 'q_investincome_to_ebt', 'q_dtprofit_to_profit',
                                        'q_salescash_to_or', 'q_ocf_to_sales', 'q_ocf_to_or', 'basic_eps_yoy',
                                        'dt_eps_yoy', 'cfps_yoy', 'op_yoy', 'ebt_yoy', 'netprofit_yoy',
                                        'dt_netprofit_yoy', 'ocf_yoy', 'roe_yoy', 'bps_yoy', 'assets_yoy', 'eqt_yoy',
                                        'tr_yoy', 'or_yoy', 'q_gr_yoy', 'q_gr_qoq', 'q_sales_yoy', 'q_sales_qoq',
                                        'q_op_yoy', 'q_op_qoq', 'q_profit_yoy', 'q_profit_qoq', 'q_netprofit_yoy',
                                        'q_netprofit_qoq', 'equity_yoy', 'rd_exp', 'update_flag'],
                         'dtypes':     ['varchar(9)', 'date', 'date', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'varchar(4)'],
                         'remarks':    ['证券代码', '报告期', '公告日期', '基本每股收益', '稀释每股收益', '每股营业总收入',
                                        '每股营业收入', '每股资本公积', '每股盈余公积', '每股未分配利润', '非经常性损益',
                                        '扣除非经常性损益后的净利润（扣非净利润）', '毛利', '流动比率', '速动比率', '保守速动比率',
                                        '存货周转天数', '应收账款周转天数', '存货周转率', '应收账款周转率', '流动资产周转率',
                                        '固定资产周转率', '总资产周转率', '经营活动净收益', '价值变动净收益', '利息费用',
                                        '折旧与摊销', '息税前利润', '息税折旧摊销前利润', '企业自由现金流量', '股权自由现金流量',
                                        '无息流动负债', '无息非流动负债', '带息债务', '净债务', '有形资产', '营运资金',
                                        '营运流动资本', '全部投入资本', '留存收益', '期末摊薄每股收益', '每股净资产',
                                        '每股经营活动产生的现金流量净额', '每股留存收益', '每股现金流量净额', '每股息税前利润',
                                        '每股企业自由现金流量', '每股股东自由现金流量', '销售净利率', '销售毛利率', '销售成本率',
                                        '销售期间费用率', '净利润/营业总收入', '销售费用/营业总收入', '管理费用/营业总收入',
                                        '财务费用/营业总收入', '资产减值损失/营业总收入', '营业总成本/营业总收入',
                                        '营业利润/营业总收入', '息税前利润/营业总收入', '净资产收益率', '加权平均净资产收益率',
                                        '净资产收益率(扣除非经常损益)', '总资产报酬率', '总资产净利润', '投入资本回报率',
                                        '年化净资产收益率', '年化总资产报酬率', '平均净资产收益率(增发条件)',
                                        '经营活动净收益/利润总额', '价值变动净收益/利润总额', '营业外收支净额/利润总额',
                                        '所得税/利润总额', '扣除非经常损益后的净利润/净利润', '销售商品提供劳务收到的现金/营业收入',
                                        '经营活动产生的现金流量净额/营业收入', '经营活动产生的现金流量净额/经营活动净收益',
                                        '资本支出/折旧和摊销', '资产负债率', '权益乘数', '权益乘数(杜邦分析)', '流动资产/总资产',
                                        '非流动资产/总资产', '有形资产/总资产', '带息债务/全部投入资本',
                                        '归属于母公司的股东权益/全部投入资本', '流动负债/负债合计', '非流动负债/负债合计',
                                        '经营活动产生的现金流量净额/流动负债', '产权比率', '归属于母公司的股东权益/负债合计',
                                        '归属于母公司的股东权益/带息债务', '有形资产/负债合计', '有形资产/带息债务',
                                        '有形资产/净债务', '经营活动产生的现金流量净额/负债合计',
                                        '经营活动产生的现金流量净额/带息债务', '经营活动产生的现金流量净额/净债务',
                                        '已获利息倍数(EBIT/利息费用)', '长期债务与营运资金比率', '息税折旧摊销前利润/负债合计',
                                        '营业周期', '年化总资产净利率', '总资产净利率(杜邦分析)', '固定资产合计',
                                        '扣除财务费用前营业利润', '非营业利润', '营业利润／利润总额', '非营业利润／利润总额',
                                        '经营活动产生的现金流量净额／营业利润', '货币资金／流动负债', '货币资金／带息流动负债',
                                        '营业利润／流动负债', '营业利润／负债合计', '年化投入资本回报率', '固定资产合计周转率',
                                        '利润总额／营业收入', '经营活动单季度净收益', '价值变动单季度净收益',
                                        '扣除非经常损益后的单季度净利润', '每股收益(单季度)', '销售净利率(单季度)',
                                        '销售毛利率(单季度)', '销售期间费用率(单季度)', '净利润／营业总收入(单季度)',
                                        '销售费用／营业总收入 (单季度)', '管理费用／营业总收入 (单季度)',
                                        '财务费用／营业总收入 (单季度)', '资产减值损失／营业总收入(单季度)',
                                        '营业总成本／营业总收入 (单季度)', '营业利润／营业总收入(单季度)', '净资产收益率(单季度)',
                                        '净资产单季度收益率(扣除非经常损益)', '总资产净利润(单季度)',
                                        '经营活动净收益／利润总额(单季度)', '价值变动净收益／利润总额(单季度)',
                                        '扣除非经常损益后的净利润／净利润(单季度)', '销售商品提供劳务收到的现金／营业收入(单季度)',
                                        '经营活动产生的现金流量净额／营业收入(单季度)',
                                        '经营活动产生的现金流量净额／经营活动净收益(单季度)', '基本每股收益同比增长率(%)',
                                        '稀释每股收益同比增长率(%)', '每股经营活动产生的现金流量净额同比增长率(%)',
                                        '营业利润同比增长率(%)', '利润总额同比增长率(%)', '归属母公司股东的净利润同比增长率(%)',
                                        '归属母公司股东的净利润-扣除非经常损益同比增长率(%)',
                                        '经营活动产生的现金流量净额同比增长率(%)', '净资产收益率(摊薄)同比增长率(%)',
                                        '每股净资产相对年初增长率(%)', '资产总计相对年初增长率(%)',
                                        '归属母公司的股东权益相对年初增长率(%)', '营业总收入同比增长率(%)',
                                        '营业收入同比增长率(%)', '营业总收入同比增长率(%)(单季度)',
                                        '营业总收入环比增长率(%)(单季度)', '营业收入同比增长率(%)(单季度)',
                                        '营业收入环比增长率(%)(单季度)', '营业利润同比增长率(%)(单季度)',
                                        '营业利润环比增长率(%)(单季度)', '净利润同比增长率(%)(单季度)',
                                        '净利润环比增长率(%)(单季度)', '归属母公司股东的净利润同比增长率(%)(单季度)',
                                        '归属母公司股东的净利润环比增长率(%)(单季度)', '净资产同比增长率', '研发费用', '更新标识'],
                         'prime_keys': [0, 1]},

    'forecast':         {'columns':    ['ts_code', 'ann_date', 'end_date', 'type', 'p_change_min', 'p_change_max',
                                        'net_profit_min', 'net_profit_max', 'last_parent_net', 'first_ann_date',
                                        'summary', 'change_reason'],
                         'dtypes':     ['varchar(9)', 'date', 'date', 'varchar(9)', 'float', 'float', 'double',
                                        'double', 'double', 'date', 'text', 'text'],
                         'remarks':    ['证券代码', '公告日期', '报告期', '业绩预告类型', '预告净利润变动幅度下限（%）',
                                        '预告净利润变动幅度上限（%）', '预告净利润下限（万元）', '预告净利润上限（万元）',
                                        '上年同期归属母公司净利润', '首次公告日', '业绩预告摘要', '业绩变动原因'],
                         # 业绩预告类型包括：预增/预减/扭亏/首亏/续亏/续盈/略增/略减
                         'prime_keys': [0, 1]},

    'express':          {'columns':    ['ts_code', 'ann_date', 'end_date', 'revenue', 'operate_profit', 'total_profit',
                                        'n_income', 'total_assets', 'total_hldr_eqy_exc_min_int', 'diluted_eps',
                                        'diluted_roe', 'yoy_net_profit', 'bps', 'yoy_sales', 'yoy_op', 'yoy_tp',
                                        'yoy_dedu_np', 'yoy_eps', 'yoy_roe', 'growth_assets', 'yoy_equity',
                                        'growth_bps', 'or_last_year', 'op_last_year', 'tp_last_year', 'np_last_year',
                                        'eps_last_year', 'open_net_assets', 'open_bps', 'perf_summary', 'is_audit',
                                        'remark'],
                         'dtypes':     ['varchar(9)', 'date', 'date', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'double', 'double', 'double',
                                        'double', 'double', 'double', 'double', 'double', 'text', 'varchar(9)', 'text'],
                         'remarks':    ['证券代码', '公告日期', '报告期', '营业收入(元)', '营业利润(元)', '利润总额(元)',
                                        '净利润(元)', '总资产(元)', '股东权益合计(不含少数股东权益)(元)', '每股收益(摊薄)(元)',
                                        '净资产收益率(摊薄)(%)', '去年同期修正后净利润', '每股净资产', '同比增长率:营业收入',
                                        '同比增长率:营业利润', '同比增长率:利润总额', '同比增长率:归属母公司股东的净利润',
                                        '同比增长率:基本每股收益', '同比增减:加权平均净资产收益率', '比年初增长率:总资产',
                                        '比年初增长率:归属母公司的股东权益', '比年初增长率:归属于母公司股东的每股净资产',
                                        '去年同期营业收入', '去年同期营业利润', '去年同期利润总额', '去年同期净利润',
                                        '去年同期每股收益', '期初净资产', '期初每股净资产', '业绩简要说明', '是否审计： 1是 0否',
                                        '备注'],
                         'prime_keys': [0, 1]}

}


class DataConflictWarning(Warning):
    """ Warning Type: Data conflict detected"""
    pass


class MissingDataWarning(Warning):
    """ Warning Type: Local Data Missing"""
    pass


# noinspection SqlDialectInspection,PyTypeChecker
class DataSource:
    """ DataSource 对象管理存储在本地的历史数据文件或数据库.

    通过DataSource对象，History模块可以容易地从本地存储的数据中读取并组装所需要的历史数据
    并确保历史数据符合HistoryPannel的要求。
    所有的历史数据必须首先从网络数据提供商处下载下来并存储在本地文件或数据库中，DataSource
    对象会检查数据的格式，确保格式正确并删除重复的数据。
    下载下来的历史数据可以存储成不同的格式，但是不管任何存储格式，所有数据表的结构都是一样
    的，而且都是与Pandas的DataFrame兼容的数据表格式。目前兼容的文件存储格式包括csv, hdf,
    ftr(feather)，兼容的数据库包括mysql和MariaDB。
    如果HistoryPanel所要求的数据未存放在本地，DataSource对象不会主动下载缺失的数据，仅会
    返回空DataFrame。
    DataSource对象可以按要求定期刷新或从NDP拉取数据，也可以手动操作

    """

    def __init__(self,
                 source_type: str,
                 file_type: str = None,
                 file_loc: str = None,
                 host: str = None,
                 port: int = None,
                 user: str = None,
                 password: str = None,
                 db: str = None):
        """ 创建一个DataSource 对象，确定本地数据存储方式，
            如果存储方式是文件，确定文件存储位置、文件类型
            如果存储方式是数据库，建立数据库的连接

        :param kwargs: the args can be improved in the future
        """

        assert source_type in ['file', 'database', 'db'], ValueError()
        if source_type == 'database':
            source_type = 'db'
        self.source_type = source_type
        self._table_list = []

        if self.source_type == 'file':
            # set up file type and file location
            if file_type is None:
                file_type = 'fth'
            if not isinstance(file_type, str):
                raise TypeError(f'file type should be a string, got {type(file_type)} instead!')
            file_type = file_type.lower()
            if file_type not in AVAILABLE_DATA_FILE_TYPES:
                raise KeyError(f'file type not recognized, supported file types are csv / hdf / feather')
            if file_type == 'feather':
                file_type = 'fth'
            self.connection_type = file_type

            from qteasy import QT_ROOT_PATH
            if file_loc is None:
                file_loc = 'qteasy/data/'
            # if not self.file_exists(file_loc):
            #     raise SystemError('specified file path does not exist')
            self.file_path = QT_ROOT_PATH + file_loc
            self.engine = None

        elif source_type == 'db':
            # set up connection to the data base
            if host is None:
                host = 'localhost'
            if port is None:
                port = 3306
            if db is None:
                db = 'qt_db'
            if user is None:
                raise ValueError(f'Missing user name for database connection')
            if password is None:
                raise ValueError(f'Missing password for database connection')
            # try to create pymysql connections
            try:
                self.con = pymysql.connect(host=host,
                                           port=port,
                                           user=user,
                                           password=password)
                # 标准的db名称为"qteasy_db"，当db不存在时创建新的db
                self.cursor = self.con.cursor()
                sql = f"CREATE DATABASE IF NOT EXISTS {db}"
                self.cursor.execute(sql)
                self.con.commit()
                sql = f"USE {db}"
                self.cursor.execute(sql)
                self.con.commit()
            except Exception as e:
                print(f'{str(e)}, fall back to file system - NotImplemented')
                raise e
            # if cursor and connect created then create sqlalchemy engine for dataframe
            self.engine = create_engine(f'mysql+pymysql://{user}:{password}@{host}:{port}/{db}')
            self.connection_type = f'mysql://{host}@{port}'
            self.file_path = None
        else:
            # for unexpected cases
            raise KeyError(f'invalid source type: {source_type}')

    # 属性
    @property
    def tables(self):
        """ 所有已经建立的tables的清单"""
        return self._table_list

    def table_schema(self, table):
        """ 显示或打印table schema

        :param table:
        :return:
        """
        tbl_struct = TABLE_SOURCE_MAPPING[table][0]
        df = pd.DataFrame(TABLE_STRUCTURES[tbl_struct])
        print(df)

    # 文件操作层函数，只操作文件，不修改数据
    def file_exists(self, file_name):
        """ 检查文件是否已存在

        :param file_name: 需要检查的文件名（不含扩展名）
        :return:
        Boolean: 文件存在时返回真，否则返回假
        """
        if self.source_type == 'db':
            raise RuntimeError('can not check file system while source type is "db"')
        if not isinstance(file_name, str):
            raise TypeError(f'file_name name must be a string, {file_name} is not a valid input!')
        file_path_name = self.file_path + file_name + '.' + self.connection_type
        return path.exists(file_path_name)

    def write_file(self, df, file_name):
        """ 将df写入本地文件

        :param df: 待写入文件的DataFrame
        :param file_name: 本地文件名（不含扩展名）
        :return:
        str: file_name 如果数据保存成功，返回完整文件路径名称
        """
        if not isinstance(file_name, str):
            raise TypeError(f'file_name name must be a string, {file_name} is not a valid input!')

        file_path_name = self.file_path + file_name
        if self.connection_type == 'csv':
            df.to_csv(file_path_name + '.csv')
        elif self.connection_type == 'fth':
            df.reset_index().to_feather(file_path_name + '.fth')
        elif self.connection_type == 'hdf':
            df.to_hdf(file_path_name + '.hdf', key='df')
        else:  # for some unexpected cases
            raise TypeError(f'Invalid file type: {self.connection_type}')
        return file_path_name

    def read_file(self, file_name, primary_key, pk_dtypes):
        """ open the file with name file_name and return the df

        :param file_name: str， 文件名
        :param primary_key:
            List, 用于生成primary_key index 的主键
        :param pk_dtypes:
            List，primary_key的数据类型
        :return:
            DataFrame：从文件中读取的DataFrame，如果数据有主键，将主键设置为df的index
        """
        if not isinstance(file_name, str):
            raise TypeError(f'file_name name must be a string, {file_name} is not a valid input!')
        if not self.file_exists(file_name):
            # 如果文件不存在，则返回空的DataFrame
            return pd.DataFrame()

        file_path_name = self.file_path + file_name
        if self.connection_type == 'csv':
            df = pd.read_csv(file_path_name + '.csv')
            set_primary_key_index(df, primary_key=primary_key, pk_dtypes=pk_dtypes)
        elif self.connection_type == 'hdf':
            df = pd.read_hdf(file_path_name + '.hdf', 'df')
        elif self.connection_type == 'fth':
            df = pd.read_feather(file_path_name + '.fth')
            set_primary_key_index(df, primary_key=primary_key, pk_dtypes=pk_dtypes)
        else:  # for some unexpected cases
            raise TypeError(f'Invalid file type: {self.connection_type}')
        return df

    def drop_file(self, file_name):
        """ 删除本地文件

        :param file_name: 将被删除的文件名
        :return:
            None
        """
        import os
        if self.file_exists(file_name):
            file_path_name = self.file_path + file_name + '.' + self.connection_type
            os.remove(file_path_name)

    # 数据库操作层函数，只操作具体的数据表，不操作数据
    def read_database(self, db_table, share_like_pk=None, shares=None, date_like_pk=None, start=None, end=None):
        """ 从一张数据库表中读取数据，读取时根据share（ts_code）和dates筛选
            具体筛选的字段通过share_like_pk和date_like_pk两个字段给出

        :param db_table: 需要读取数据的数据表
        :param share_like_pk:
            用于筛选证券代码的字段名，不同的表中字段名可能不同，用这个字段筛选不同的证券、如股票、基金、指数等
            当这个参数给出时，必须给出shares参数
        :param shares: 如果给出shares，则按照"WHERE share_like_pk IN shares"筛选
        :param date_like_pk:
            用于筛选日期的主键字段名，不同的表中字段名可能不同，用这个字段筛选需要的记录的时间段
            当这个参数给出时，必须给出start和end参数
        :param start:  如果给出start同时又给出end，按照"WHERE date_like_pk BETWEEEN start AND end"的条件筛选
        :param end:    当没有给出start时，单独给出end无效
        :return:
            DataFrame，从数据库中读取的DataFrame
        """
        if not self.db_table_exists(db_table):
            return pd.DataFrame()
        ts_code_filter = ''
        has_ts_code_filter = False
        date_filter = ''
        has_date_filter = False
        if shares is not None:
            has_ts_code_filter = True
            share_count = len(shares)
            if share_count > 1:
                ts_code_filter = f'{share_like_pk} in {tuple(shares)}'
            else:
                ts_code_filter = f'{share_like_pk} = "{shares[0]}"'
        if (start is not None) and (end is not None):
            # assert start and end are date-like
            has_date_filter = True
            date_filter = f'{date_like_pk} BETWEEN {start} AND {end}'

        sql = f'SELECT * ' \
              f'FROM {db_table}\n'
        if not (has_ts_code_filter or has_date_filter):
            # No WHERE clause
            pass
        elif has_ts_code_filter and has_date_filter:
            # both WHERE clause
            sql += f'WHERE {ts_code_filter}' \
                   f' AND {date_filter}\n'
        elif has_ts_code_filter and not has_date_filter:
            # only one WHERE clause
            sql += f'WHERE {ts_code_filter}\n'
        elif not has_ts_code_filter and has_date_filter:
            # only one WHERE clause
            sql += f'WHERE {date_filter}'
        sql += ''
        # debug
        # print(f'trying to get data from database with SQL: \n"{sql}"')

        df = pd.read_sql_query(sql, con=self.engine)
        return df

    def write_database(self, df, db_table):
        """ 将DataFrame中的数据添加到数据库表的末尾，假定df的列
        与db_table的schema相同

        :param df: 需要添加的DataFrame
        :param db_table: 需要添加数据的数据库表
        :return:
            None
        """
        df.to_sql(db_table, self.engine, index=False, if_exists='append', chunksize=5000)

    def update_database(self, df, db_table, primary_key):
        """ 用DataFrame中的数据更新数据表中的数据记录，假定
            df的列与db_table的列相同且顺序也相同
            在插入数据之前，必须确保表的primary_key已经正确设定

        :param df: 用于更新数据表的数据DataFrame
        :param db_table: 需要更新的数据表
        :param primary_key: 数据表的primary_key，必须定义在数据表中，如果数据库表没有primary_key，将append所有数据
        :return:
            None
        """
        tbl_columns = tuple(self.get_db_table_schema(db_table).keys())
        update_cols = [item for item in tbl_columns if item not in primary_key]
        if (len(df.columns) != len(tbl_columns)) or (any(i_d != i_t for i_d, i_t in zip(df.columns, tbl_columns))):
            raise KeyError(f'df columns {df.columns.to_list()} does not fit table schema {list(tbl_columns)}')
        df = df.where(pd.notna(df), None)
        df_tuple = tuple(df.itertuples(index=False, name=None))
        sql = f"INSERT INTO `{db_table}` ("
        for col in tbl_columns[:-1]:
            sql += f"`{col}`, "
        sql += f"`{tbl_columns[-1]}`)\nVALUES\n("
        for val in tbl_columns[:-1]:
            sql += "%s, "
        sql += "%s)\n" \
               "ON DUPLICATE KEY UPDATE\n"
        for col in update_cols[:-1]:
            sql += f"`{col}`=VALUES(`{col}`),\n"
        sql += f"`{update_cols[-1]}`=VALUES(`{update_cols[-1]}`)"
        try:
            self.cursor.executemany(sql, df_tuple)
            self.con.commit()
        except Exception as e:
            self.con.rollback()
            raise RuntimeError(f'Error during inserting data to table {db_table} with following sql:\n'
                               f'{sql} \nwith parameters (first 50 shown):\n{df_tuple[:50]}')

    # 以下几个数据库操作函数用于操作数据库表，可用于优化表结构以提升查询速度，如修改数据格式并建立索引等
    def db_table_exists(self, db_table):
        """ 检查数据库中是否存在db_table这张表

        :param db_table:
        :return:
        """
        if self.source_type == 'file':
            raise RuntimeError('can not connect to database while source type is "file"')
        sql = f"SHOW TABLES LIKE '{db_table}'"
        # debug
        # print(f'will execute this SQL:\n{sql}')
        self.cursor.execute(sql)
        self.con.commit()
        res = self.cursor.fetchall()
        return len(res) > 0

    def new_db_table(self, db_table, columns, dtypes, primary_key):
        """ 在数据库中新建一个数据表(如果该表不存在)，并且确保数据表的schema与设置相同

        :param db_table:
            Str: 数据表名
        :param columns:
            List: 一个包含若干str的list，表示数据表的所有字段名
        :param dtypes:
            List: 一个包含若干str的list，表示数据表所有字段的数据类型
        :param primary_key:
            List: 一个包含若干str的list，表示数据表的所有primary_key
        :return:
            None
        """
        if self.source_type != 'db':
            raise TypeError(f'Datasource is not connected to a database')

        sql = f"CREATE TABLE IF NOT EXISTS {db_table} (\n"
        for col_name, dtype in zip(columns, dtypes):
            sql += f"`{col_name}` {dtype}"
            if col_name in primary_key:
                sql += " NOT NULL,\n"
            else:
                sql += ",\n"
        if primary_key is not None:
            sql += f"PRIMARY KEY ("
            for pk in primary_key[:-1]:
                sql += f"{pk}, "
            sql += f"{primary_key[-1]})\n)"
        # debug
        try:
            self.cursor.execute(sql)
        except Exception as e:
            print(f'error encountered during executing sql: \n{sql}\n error codes: \n{e}')
        self.con.commit()

    def alter_db_table(self, db_table, columns, dtypes, primary_key):
        """ 修改db_table的schema，按照输入参数设置表的字段属性

        :param db_table:
            Str: 数据表名
        :param columns:
            List: 一个包含若干str的list，表示数据表的所有字段名
        :param dtypes:
            List: 一个包含若干str的list，表示数据表所有字段的数据类型
        :param primary_key:
            List: 一个包含若干str的list，表示数据表的所有primary_key
        :return:
            None
        """
        if self.source_type != 'db':
            raise TypeError(f'Datasource is not connected to a database')

        # 获取数据表的columns和data types：
        cur_columns = self.get_db_table_schema(db_table)
        # 将新的columns和dtypes写成Dict形式
        new_columns = {}
        for col, typ in zip(columns, dtypes):
            new_columns[col] = typ
        # debug
        # print(f'fetched columns and types are: \n{cur_columns}')
        # to drop some columns
        col_to_drop = [col for col in cur_columns if col not in columns]
        # debug
        # print(f'following cols will be dropped from table:\n{col_to_drop}')
        for col in col_to_drop:
            sql = f"ALTER TABLE {db_table} \n" \
                  f"DROP COLUMN `{col}`"
            # debug
            # print(f'will execute following sql: \n{sql}\n')
            # 需要同步删除cur_columns字典中的值，否则modify时会产生错误
            del cur_columns[col]
            self.cursor.execute(sql)
            self.con.commit()

        # to add some columns
        col_to_add = [col for col in columns if col not in cur_columns]
        print(f'following cols will be added to the table:\n{col_to_add}')
        for col in col_to_add:
            sql = f"ALTER TABLE {db_table} \n" \
                  f"ADD {col} {new_columns[col]}"
            # debug
            # print(f'will execute following sql: \n{sql}\n')
            self.cursor.execute(sql)
            self.con.commit()

        # to modify some columns
        col_to_modify = [col for col in cur_columns if cur_columns[col] != new_columns[col]]
        print(f'following cols will be modified:\n{col_to_modify}')
        for col in col_to_modify:
            sql = f"ALTER TABLE {db_table} \n" \
                  f"MODIFY COLUMN {col} {new_columns[col]}"
            # debug
            # print(f'will execute following sql: \n{sql}\n')
            self.cursor.execute(sql)
            self.con.commit()

        # TODO: should also modify the primary keys, to be updated
        pass

    def get_db_table_schema(self, db_table):
        """ 获取数据库表的列名称和数据类型

        :param db_table: 需要获取列名的数据库表
        :return:
            dict: 一个包含列名和数据类型的Dict: {column1: dtype1, column2: dtype2, ...}
        """
        sql = f"SELECT COLUMN_NAME, DATA_TYPE " \
              f"FROM INFORMATION_SCHEMA.COLUMNS " \
              f"WHERE TABLE_SCHEMA = Database() " \
              f"AND table_name = '{db_table}'" \
              f"ORDER BY ordinal_position"
        # debug
        # print(f'will execute following sql: \n{sql}\n')

        self.cursor.execute(sql)
        self.con.commit()
        results = self.cursor.fetchall()
        # 为了方便，将cur_columns和new_columns分别包装成一个字典
        columns = {}
        for col, typ in results:
            columns[col] = typ
        return columns

    def drop_db_table(self, db_table):
        """ 修改优化db_table的schema，建立index，从而提升数据库的查询速度提升效能

        :param db_table:
        :return:
        """
        if self.source_type != 'db':
            raise TypeError(f'Datasource is not connected to a database')
        if not isinstance(db_table, str):
            raise TypeError(f'db_table name should be a string, got {type(db_table)} instead')
        sql = f"DROP TABLE IF EXISTS {db_table}"
        self.cursor.execute(sql)
        self.con.commit()

    # (逻辑)数据表操作层函数，只在逻辑表层面读取或写入数据，调用文件操作函数或数据库函数存储数据
    def table_data_exists(self, table):
        """ 逻辑层函数，判断数据表是否存在

        :param table: 数据表名称
        :return:
        """
        if self.source_type == 'db':
            return self.db_table_exists(db_table=table)
        elif self.source_type == 'file':
            return self.file_exists(table)
        else:
            raise KeyError(f'invalid source_type: {self.source_type}')

    def read_table_data(self, table, shares=None, start=None, end=None):
        """ 从指定的一张本地数据表（文件或数据库）中读取数据并返回DataFrame，不修改数据格式
        在读取数据表时读取所有的列，但是返回值筛选ts_code以及trade_date between start 和 end

            TODO: potentially: 如果一张数据表的数据量过大，查询或读取数据将花费太多的时间
            TODO: 此时应该将表格存储在多张数据库表或多个文件中，本函数应该执行这一项管理工作
            TODO: 根据所需的数据，从不同的文件或数据库中读取数据并组合成一个DataFrame, 此
            TODO: 时需要建立索引文件、并通过索引文件快速获取所需的数据，这些工作都在本函数
            TODO: 中执行

        :param table: str 数据表名称
        :param shares: list，ts_code筛选条件，为空时给出所有记录
        :param start: str，YYYYMMDD格式日期，为空时不筛选
        :param end: str，YYYYMMDD格式日期，当start不为空时有效，筛选日期范围

        :return
        pd.DataFrame 返回的数据为DataFrame格式

        """
        if not isinstance(table, str):
            raise TypeError(f'table name should be a string, got {type(table)} instead.')
        if table not in TABLE_SOURCE_MAPPING.keys():
            raise KeyError(f'Invalid table name.')

        if shares is not None:
            assert isinstance(shares, (str, list))
            if isinstance(shares, str):
                shares = str_to_list(shares)

        if (start is not None) and (end is not None):
            start = regulate_date_format(start)
            end = regulate_date_format(end)
            assert pd.to_datetime(start) <= pd.to_datetime(end)

        columns, dtypes, primary_key, pk_dtypes = get_built_in_table_schema(table)
        # 识别primary key中的证券代码列名和日期类型列名，确认是否需要筛选证券代码及日期
        share_like_pk = None
        date_like_pk = None
        if shares is not None:
            try:
                varchar_like_dtype = [item for item in pk_dtypes if item[:7] == 'varchar'][0]
                share_like_pk = primary_key[pk_dtypes.index(varchar_like_dtype)]
            except:
                warnings.warn(f'can not find share-like primary key in the table {table}!\n'
                              f'passed argument shares will be ignored!', RuntimeWarning)
        # 识别Primary key中的，并确认是否需要筛选日期型pk
        if (start is not None) and (end is not None):
            try:
                date_like_pk = primary_key[pk_dtypes.index('date')]
            except:
                warnings.warn(f'can not find date-like primary key in the table {table}!\n'
                              f'passed start and end arguments will be ignored!', RuntimeWarning)

        if self.source_type == 'file':
            # 读取table数据, 从本地文件中读取的DataFrame已经设置好了primary_key index
            # 但是并未按shares和start/end进行筛选，需要手动筛选
            df = self.read_file(file_name=table, primary_key=primary_key, pk_dtypes=pk_dtypes)
            if df.empty:
                return df
            if share_like_pk is not None:
                df = df.loc[df.index.isin(shares, level=share_like_pk)]

            if date_like_pk is not None:
                # 两种方法实现筛选，分别是df.query 以及 df.index.get_level_values()
                # 第一种方法， df.query
                # df = df.query(f"{date_like_pk} >= {start} and {date_like_pk} <= {end}")
                # 第二种方法：df.index.get_level_values()
                m1 = df.index.get_level_values(date_like_pk) >= start
                m2 = df.index.get_level_values(date_like_pk) <= end
                df = df[m1 & m2]
        elif self.source_type == 'db':
            # 读取数据库表，从数据库表中读取的DataFrame并未设置primary_key index，因此
            # 需要手动设置index，但是读取的数据已经按shares/start/end筛选，无需手动筛选
            self.new_db_table(db_table=table, columns=columns, dtypes=dtypes, primary_key=primary_key)
            if share_like_pk is None:
                shares = None
            if date_like_pk is None:
                start = None
                end = None
            df = self.read_database(db_table=table,
                                    share_like_pk=share_like_pk,
                                    shares=shares,
                                    date_like_pk=date_like_pk,
                                    start=start,
                                     end=end)
            if df.empty:
                return df
            set_primary_key_index(df, primary_key, pk_dtypes)
        else:  # for unexpected cases:
            raise TypeError(f'Invalid value DataSource.source_type: {self.source_type}')

        return df

    def write_table_data(self, df, table, on_duplicate='ignore'):
        """ 将df中的数据写入本地数据表（本地文件或数据库）
            如果本地数据表不存在则新建数据表，如果本地数据表已经存在，则将df数据添加在本地表中
            如果添加的数据主键与已有的数据相同，处理方式由on_duplicate参数确定

            注意！！不应直接使用该函数将数据写入本地数据库，因为写入的数据不会被检查
            请使用update_table_data()来更新或写入数据到本地数据库

            TODO: potentially: 如果一张数据表的数据量过大，除非将数据存储在数据库中，
            TODO: 如果将所有数据存储在一个文件中将导致读取速度下降，本函数应该进行分表工作，
            TODO: 即将数据分成不同的DataFrame，分别保存在不同的文件中。 此时需要建立
            TODO: 索引数据文件、并通过索引表快速获取所需的数据，这些工作都在本函数中执行

        :param df: pd.DataFrame 一个数据表，数据表的列名应该与本地数据表定义一致
        :param table: str 本地数据表名，
        :param on_duplicate: str 重复数据处理方式（仅当mode==db的时候有效）
            -ignore: 默认方式，将全部数据写入数据库表的末尾
            -update: 将数据写入数据库表中，如果遇到重复的pk则修改表中的内容

        :return
        None

        """
        assert isinstance(df, pd.DataFrame)
        if not isinstance(table, str):
            raise TypeError(f'table name should be a string, got {type(table)} instead.')
        if table not in TABLE_SOURCE_MAPPING.keys():
            raise KeyError(f'Invalid table name.')
        columns, dtypes, primary_key, pk_dtype = get_built_in_table_schema(table)
        if self.source_type == 'file':
            df = set_primary_key_frame(df, primary_key=primary_key, pk_dtypes=pk_dtype)
            set_primary_key_index(df, primary_key=primary_key, pk_dtypes=pk_dtype)
            self.write_file(df, file_name=table)
        elif self.source_type == 'db':
            self.new_db_table(db_table=table, columns=columns, dtypes=dtypes, primary_key=primary_key)
            if on_duplicate == 'ignore':
                self.write_database(df, db_table=table)
            elif on_duplicate == 'update':
                self.update_database(df, db_table=table, primary_key=primary_key)
            else:  # for unexpected cases
                raise KeyError(f'Invalid process mode on duplication: {on_duplicate}')

    def acquire_table_data(self, table, channel, df=None, f_name=None, **kwargs):
        """从网络获取本地数据表的数据，并进行内容写入前的预检查：包含以下步骤：
            1，根据channel确定数据源，根据table名下载相应的数据表
            2，处理获取的df的格式，确保为只含简单range-index的格式

        :param table: str, 数据表名，必须是database中定义的数据表
        :param channel:
            str: 数据获取渠道，指定需要连接的金融数据API，或直接给出local_df，支持以下选项：
            - 'local_df': 通过参数传递一个df，该df的columns必须与table的定义相同
            - 'tushare' : 从Tushare API获取金融数据，请自行申请相应权限和积分
            - 'other'   : 其他金融数据API，尚未开发
        :param df: pd.DataFrame 通过传递一个DataFrame获取数据
            如果数据获取渠道为"df"，则必须给出此参数
        :param f_name: str 通过本地csv文件或excel文件获取数据
            如果数据获取方式为"csv"或者"excel"时，必须给出此参数，表示文件的路径
        :param kwargs:
            用于下载金融数据的函数参数

        :return:
            pd.DataFrame: 下载后并处理完毕的数据，DataFrame形式，仅含简单range-index格式
        """
        if not isinstance(table, str):
            raise TypeError(f'table name should be a string, got {type(table)} instead.')
        if table not in TABLE_SOURCE_MAPPING.keys():
            raise KeyError(f'Invalid table name {table}')
        if not isinstance(channel, str):
            raise TypeError(f'channel should be a string, got {type(channel)} instead.')
        if channel not in AVAILABLE_CHANNELS:
            raise KeyError(f'Invalid channel name {channel}')

        column, dtypes, primary_keys, pk_dtypes = get_built_in_table_schema(table)
        # 从指定的channel获取数据
        if channel == 'df':
            # 通过参数传递的DF获取数据
            if df is None:
                raise ValueError(f'a DataFrame must be given while channel == "df"')
            if not isinstance(df, pd.DataFrame):
                raise TypeError(f'local df should be a DataFrame, got {type(df)} instead.')
            dnld_data = df
        elif channel == 'csv':
            # 读取本地csv数据文件获取数据
            if f_name is None:
                raise ValueError(f'a file path and name must be given while channel == "csv"')
            if not isinstance(f_name, str):
                raise TypeError(f'file name should be a string, got {type(df)} instead.')
            raise NotImplementedError
        elif channel == 'excel':
            # 读取本地Excel文件获取数据
            assert f_name is not None, f'a file path and name must be given while channel == "excel"'
            assert isinstance(f_name, str), \
                f'file name should be a string, got {type(df)} instead.'
            raise NotImplementedError
        elif channel == 'tushare':
            # 通过tushare的API下载数据
            dnld_data = acquire_data(table, **kwargs)
        else:
            raise NotImplementedError
        res = dnld_data
        res = set_primary_key_frame(dnld_data, primary_key=primary_keys, pk_dtypes=pk_dtypes)
        return res

    def update_table_data(self, table, df, merge_type='update'):
        """ 检查输入的df，去掉不符合要求的列或行后，将数据合并到table中，包括以下步骤：

            1，检查下载后的数据表的列名是否与数据表的定义相同，删除多余的列
            2，如果datasource type是"db"，删除下载数据中与本地数据重复的部分，仅保留新增数据
            3，如果datasource type是"file"，将下载的数据与本地数据合并并去重
            返回处理完毕的dataFrame

        :param table: str, 数据表名，必须是database中定义的数据表
        :param merge_type: str
            指定如何合并下载数据和本地数据：
            - 'update': 默认值，如果下载数据与本地数据重复，用下载数据替代本地数据
            - 'ignore' : 如果下载数据与本地数据重复，忽略重复部分
        :param df: pd.DataFrame 通过传递一个DataFrame获取数据
            如果数据获取渠道为"df"，则必须给出此参数

        :return:
            pd.DataFrame: 下载后并处理完毕的数据，DataFrame形式
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f'df should be a dataframe, got {type(df)} instead')
        if not isinstance(merge_type, str):
            raise TypeError(f'merge type should be a string, got {type(merge_type)} instead.')
        if merge_type not in ['ignore', 'update']:
            raise KeyError(f'Invalid merge type, should be either "ignore" or "update"')

        dnld_data = df
        if dnld_data.empty:
            return

        table_columns, dtypes, primary_keys, pk_dtypes = get_built_in_table_schema(table)
        dnld_data = set_primary_key_frame(dnld_data, primary_key=primary_keys, pk_dtypes=pk_dtypes)
        dnld_columns = dnld_data.columns.to_list()
        # 如果table中的相当部分（25%）不能从df中找到，判断df与table完全不匹配，报错
        # 否则判断df基本与table匹配，根据Constraints，添加缺少的列（通常为NULL列）
        missing_columns = [col for col in table_columns if col not in dnld_columns]
        if len(missing_columns) >= (len(table_columns) * 0.25):
            raise ValueError(f'there are too many missing columns in downloaded df, can not merge to local table')
        else:
            pass  # 在后面调整列顺序时会同时添加缺的列并调整顺序
        # 删除数据中过多的列，不允许出现缺少列
        columns_to_drop = [col for col in dnld_columns if col not in table_columns]
        if len(columns_to_drop) > 0:
            # debug
            # print(f'there are columns to drop, they are\n{columns_to_drop}')
            dnld_data.drop(columns=columns_to_drop, inplace=True)
        # 确保df与table的column顺序一致
        if len(missing_columns)>0 or any(item_d != item_t for item_d, item_t in zip(dnld_columns, table_columns)):
            dnld_data = dnld_data.reindex(columns=table_columns, copy=False)
            # print(f'downloaded data does not fit table schema:\n'
            #       f'df columns: {dnld_columns}\n'
            #       f'tbl schema: {table_columns}')
        if self.source_type == 'file':
            # 如果source_type == 'file'，需要将下载的数据与本地数据合并，本地数据必须全部下载，
            # 数据量大后非常费时
            # 因此本地文件系统承载的数据量非常有限
            local_data = self.read_table_data(table)
            set_primary_key_index(dnld_data, primary_key=primary_keys, pk_dtypes=pk_dtypes)
            # 根据merge_type处理重叠部分：
            if merge_type == 'ignore':
                # 丢弃下载数据中的重叠部分
                dnld_data = dnld_data[~dnld_data.index.isin(local_data.index)]
            elif merge_type == 'update':  # 用下载数据中的重叠部分覆盖本地数据，下载数据不变，丢弃本地数据中的重叠部分（仅用于本地文件保存的情况）
                local_data = local_data[~local_data.index.isin(dnld_data.index)]
            else:  # for unexpected cases
                raise KeyError(f'Invalid merge type, got "{merge_type}"')
            self.write_table_data(pd.concat([local_data, dnld_data]), table=table)
        elif self.source_type == 'db':
            # 如果source_type == 'db'，不需要合并数据，当merge_type == 'update'时，甚至不需要下载
            # 本地数据
            if merge_type == 'ignore':
                dnld_data_range = get_primary_key_range(dnld_data, primary_key=primary_keys, pk_dtypes=pk_dtypes)
                local_data = self.read_table_data(table, **dnld_data_range)
                set_primary_key_index(dnld_data, primary_key=primary_keys, pk_dtypes=pk_dtypes)
                dnld_data = dnld_data[~dnld_data.index.isin(local_data.index)]
            dnld_data = set_primary_key_frame(dnld_data, primary_key=primary_keys, pk_dtypes=pk_dtypes)
            self.write_table_data(dnld_data, table=table, on_duplicate=merge_type)
        else:  # unexpected case
            raise KeyError(f'invalid data source type')

        return

    def drop_table_data(self, table):
        """ 删除本地存储的数据表（操作不可撤销，谨慎使用）

        :param table: 本地数据表的名称
        :return:
            None
        """
        if self.source_type == 'db':
            self.drop_db_table(db_table=table)
        elif self.source_type == 'file':
            self.drop_file(file_name=table)
        return None

    def get_table_data_coverage(self, table):
        """ 获取本地数据表内容的覆盖范围，对于时间类型，返回min/max/count

        :param table:
        :return:
        """
        raise NotImplementedError

    # 顶层函数，包括用于组合HistoryPanel的数据获取接口函数，以及自动或手动下载本地数据的操作函数
    def get_history_dataframes(self, shares, htypes, start, end, freq, asset_type='any', adj='none'):
        """ 根据给出的参数从不同的本地数据表中获取数据，并打包成一系列的DataFrame，以便组装成
            HistoryPanel对象，用于策略的运行、回测或优化测试。

        :param shares: [str, list]
            需要获取历史数据的证券代码集合，可以是以逗号分隔的证券代码字符串或者证券代码字符列表，
            如以下两种输入方式皆合法且等效：
             - str:     '000001.SZ, 000002.SZ, 000004.SZ, 000005.SZ'
             - list:    ['000001.SZ', '000002.SZ', '000004.SZ', '000005.SZ']
        :param htypes: [str, list]
            需要获取的历史数据类型集合，可以是以逗号分隔的数据类型字符串或者数据类型字符列表，
            如以下两种输入方式皆合法且等效：
             - str:     'open, high, low, close'
             - list:    ['open', 'high', 'low', 'close']
        :param start: str
            YYYYMMDD HH:MM:SS 格式的日期/时间，获取的历史数据的开始日期/时间（如果可用）
        :param end: str
            YYYYMMDD HH:MM:SS 格式的日期/时间，获取的历史数据的结束日期/时间（如果可用）
        :param freq: str
            获取的历史数据的频率，包括以下选项：
             - 1/5/15/30min 1/5/15/30分钟频率周期数据（如K线）
             - H/D/W/M 分别代表小时/天/周/月 周期数据（如K线）
        :param asset_type: str, list
            限定获取的数据中包含的资产种类，包含以下选项或下面选项的组合，合法的组合方式包括
            逗号分隔字符串或字符串列表，例如: 'E, IDX' 和 ['E', 'IDX']都是合法输入
             - any: 可以获取任意资产类型的证券数据（默认值）
             - E:   只获取股票类型证券的数据
             - IDX: 只获取指数类型证券的数据
             - FT:  只获取期货类型证券的数据
             - FD:  只获取基金类型证券的数据
        :param adj: str
            对于某些数据，可以获取复权数据，需要通过复权因子计算，复权选项包括：
             - none: 不复权（默认值）
             - back: 后复权
             - forward: 前复权

        :return:
        Dict 一个标准的DataFrame-Dict，满足stack_dataframes()函数的输入要求，以便组装成
            HistoryPanel对象
        """
        # 检查数据合法性：
        if not isinstance(shares, (str, list)):
            raise TypeError(f'shares should be a string or list of strings, got {type(shares)}')
        if isinstance(shares, str):
            shares = str_to_list(shares)
        if isinstance(shares, list):
            if not all(isinstance(item, str) for item in shares):
                raise TypeError(f'all items in shares list should be a string, got otherwise')

        if not isinstance(htypes, (str, list)):
            raise TypeError(f'htypes should be a string or list of strings, got {type(htypes)}')
        if isinstance(htypes, str):
            htypes = str_to_list(htypes)
        if isinstance(htypes, list):
            if not all(isinstance(item, str) for item in htypes):
                raise TypeError(f'all items in htypes list should be a string, got otherwise')

        if (not isinstance(start, str)) and (not isinstance(end, str)):
            raise TypeError(f'start and end should be both datetime string in format "YYYYMMDD hh:mm:ss"')

        if not isinstance(freq, str):
            raise TypeError(f'freq should be a string, got {type(freq)} instead')
        if freq.upper() not in TIME_FREQ_STRINGS:
            raise KeyError(f'invalid freq, valid freq should be anyone in {TIME_FREQ_STRINGS}')

        if not isinstance(asset_type, (str, list)):
            raise TypeError(f'asset type should be a string, got {type(asset_type)} instead')
        if isinstance(asset_type, str):
            asset_type = str_to_list(asset_type)
        if not all(isinstance(item, str) for item in asset_type):
            raise KeyError(f'not all items in asset type are strings')
        if not all(item.upper() in ['ANY'] + AVAILABLE_ASSET_TYPES for item in asset_type):
            raise KeyError(f'invalid asset_type, asset types should be one or many in {AVAILABLE_ASSET_TYPES}')
        if any(item.upper() == 'ANY' for item in asset_type):
            asset_type = AVAILABLE_ASSET_TYPES

        if not isinstance(adj, str):
            raise TypeError(f'adj type should be a string, got {type(adj)} instead')
        if adj.upper() not in ['NONE', 'BACK', 'FORWARD']:
            raise KeyError(f"invalid adj type, which should be anyone of ['NONE', 'BACK', 'FORWARD']")

        # 根据资产类型、数据类型和频率找到应该下载数据的目标数据表
        table_map = pd.DataFrame(TABLE_SOURCE_MAPPING).T
        table_map.columns = TABLE_SOURCE_MAPPING_COLUMNS
        tables_to_read = table_map.loc[(table_map.table_usage == 'data') &
                                       (table_map.asset_type.isin(asset_type)) &
                                       (table_map.freq == freq)].index.to_list()
        # debug
        # print(f'tables to read: {tables_to_read}\n')
        # 根据资产代码、起止日期查询所需的数据,删除不需要的数据
        table_data_read = {}
        table_data_columns = {}
        for tbl in tables_to_read:
            df = self.read_table_data(tbl, shares=shares, start=start, end=end)
            if not df.empty:
                cols_to_remove = [col for col in df.columns if col not in htypes]
                df.drop(columns=cols_to_remove, inplace=True)
            table_data_read[tbl] = df
            table_data_columns[tbl] = df.columns
            # debug
            # print(f'got data from table {tbl}:\n{df}\n')

        # 提取数据，生成单个数据类型的dataframe
        df_by_htypes = {k: v for k, v in zip(htypes, [pd.DataFrame()] * len(htypes))}
        for htyp in htypes:
            for tbl in tables_to_read:
                if htyp in table_data_columns[tbl]:
                    df = table_data_read[tbl]
                    if not df.empty:
                        htyp_series = df[htyp]
                        new_df = htyp_series.unstack(level=0)
                        old_df = df_by_htypes[htyp]
                        # 使用两种方法实现df的合并，分别是merge()和join()
                        # df_by_htypes[htyp] = old_df.merge(new_df,
                        #                                   how='outer',
                        #                                   left_index=True,
                        #                                   right_index=True,
                        #                                   suffixes=('', '_y'))
                        df_by_htypes[htyp] = old_df.join(new_df,
                                                         how='outer',
                                                         rsuffix='_y')
                        # debug
                        # print(f'got un stacked dataframe for htype {htyp} from table {tbl}:\n'
                        #       f'{new_df}\n'
                        #       f'=============================================================')
        # 如果在历史数据合并时发现列名称冲突，发出警告信息，并删除后添加的列
        conflict_cols = ''
        for htyp in htypes:
            df_columns = df_by_htypes[htyp].columns.to_list()
            col_with_suffix = [col for col in df_columns if col[-2:] == '_y']
            if len(col_with_suffix) > 0:
                df_by_htypes[htyp].drop(columns=col_with_suffix, inplace=True)
                conflict_cols += f'd-type {htyp} conflicts in {list(set(col[:-2] for col in col_with_suffix))};\n'
            # debug
            # print(f'got dataframe data for htype {htyp}:\n'
            #       f'columns: {df_by_htypes[htyp].columns}\n'
            #       f'{df_by_htypes[htyp].head()}\n')
        if conflict_cols != '':
            warnings.warn(f'\nConflict data encountered, some types of data are loaded from multiple tables, '
                          f'conflicting data might be discarded:\n'
                          f'{conflict_cols}', DataConflictWarning)

        # 如果需要复权数据，计算复权价格
        if adj != 'none':
            # 下载复权因子
            adj_factors = {}
            adj_tables_to_read = table_map.loc[(table_map.table_usage == 'adj') &
                                               table_map.asset_type.isin(asset_type)].index.to_list()
            # debug
            # print(f'adj tables to read: {adj_tables_to_read}\n')
            for tbl in adj_tables_to_read:
                adj_df = self.read_table_data(tbl, shares=shares, start=start, end=end)
                if not adj_df.empty:
                    adj_df = adj_df['adj_factor'].unstack(level=0)
                adj_factors[tbl] = adj_df
                # debug
                # print(f'got adj data from table {tbl}:\n{adj_df}')
                # 后复权 = 当日最新价 × 当日复权因子
                # 前复权 = 当日复权价 ÷ 最新复权因子

            # 根据复权因子更新所有可复权数据
            prices_to_adjust = [item for item in htypes if item in ADJUSTABLE_PRICE_TYPES]
            # debug
            # print(f'prices to adjust is: {prices_to_adjust}')
            for htyp in prices_to_adjust:
                price_df = df_by_htypes[htyp]
                all_ts_codes = price_df.columns
                comb_factors = 1.0
                for af in adj_factors:
                    comb_factors *= adj_factors[af].reindex(columns=all_ts_codes).fillna(1.0)
                # debug
                # print(f'got combined adj factors: \n{comb_factors}')
                price_df *= comb_factors
                if adj == 'forward' and len(comb_factors) > 1:
                    price_df /= comb_factors.iloc[-1]
                # print(f'got adjusted prices for {htyp} like: \n{price_df}')

        result_hp = stack_dataframes(df_by_htypes, stack_along='htypes')
        # debug
        # print(f'got history panel: \n{result_hp}')
        return result_hp

    # 顶层函数，用于定期计划性获取数据的操作函数
    def refill_local_source(self,
                            tables,
                            date_fill_to=None,
                            date_fill_back_to=None,
                            start_date=None,
                            end_date=None,
                            merge_type='update',
                            parallel=True,
                            process_count=16):
        """ 补充本地数据，手动或自动运行补充本地数据库

        :param tables:
        :param date_fill_to:
        :param date_fill_back_to:
        :param start_date:
        :param end_date:
        :param merge_type:
        :param parallel:
        :param process_count:
        :return:
        """
        if not isinstance(tables, (str, list)):
            raise TypeError(f'tables should be a list or a string, got {type(tables)} instead.')
        if isinstance(tables, str):
            if len(tables) == 0:
                raise KeyError(f'invalid input, tables can not be empty string')
            tables = str_to_list(tables)
        if not all(isinstance(item, str) for item in tables):
            raise TypeError(f'some items in tables list are not string: '
                            f'{[item for item in tables if not isinstance(item, str)]}')
        if not all(item in TABLE_SOURCE_MAPPING for item in tables):
            raise KeyError(f'some items in tables list are not valid: '
                           f'{[item for item in tables if item not in TABLE_SOURCE_MAPPING]}')
        if tables == 'all':
            tables = list(TABLE_SOURCE_MAPPING.keys())

        table_map = pd.DataFrame(TABLE_SOURCE_MAPPING).T
        table_map.columns = TABLE_SOURCE_MAPPING_COLUMNS
        # print(table_map)
        import time
        for table in tables:
            # debug
            # print(f'started to refill data table {table}...')
            if self.table_data_exists(table):
                pass
                # tbl_start_date, tbl_end_date, tbl_date_count = self.get_table_data_coverage(table)
            arg_names = str_to_list(table_map.loc[table].fill_arg_name)
            if (len(arg_names) > 1) or (len(arg_names) <= 0):
                print(f'warning: currently only one data coverage fill argument is supported, got '
                      f'{len(arg_names)} arguments are defined for table {table}, will skip this '
                      f'table')
                continue
            fill_type = table_map.loc[table].fill_arg_type
            if fill_type != 'datetime':
                print(f'warning: table fill type ({fill_type}) for table {table} is not datetime, '
                      f'can not be filled at the moment! currently only datetime type of tables can '
                      f'be filled.')
                continue
            freq = table_map.loc[table].freq
            print(f'filling table: \n'
                  f'table: <{table}>, with {fill_type} type argument: {arg_names[0]} @  {freq} ... ')
            if freq == 'w':
                freq = 'w-Fri'  # 确保通过w获取的数据都在周五

            # 开始生成所有的参数
            all_kwargs = None
            date_coverage = []
            if (date_fill_to is None) and (date_fill_back_to is None):
                # 根据start_date和end_date生成数据获取区间
                date_coverage = pd.date_range(start=start_date, end=end_date, freq=freq)
                if (freq == 'm') or (freq == 'w-Fri'):
                    # 当freq为m或者w时，生成的日期并不连续，不一定会找到交易日，需要找到最近的交易日
                    date_coverage = map(nearest_market_trade_day, date_coverage)
                date_coverage = list(pd.to_datetime(list(date_coverage)).strftime('%Y%m%d'))
                arg_name = arg_names[0]
                all_kwargs = ({arg_name: val} for val in date_coverage)

            else:
                print(f'currently date_fill_to and date_fill_back_to should only be None, otherwise '
                      f'not supported')
            # 开始循环下载并更新数据
            completed = 0
            total = len(date_coverage)
            # print(f'filling started, kwargs are:')
            # for kw in all_kwargs:
            #     print(kw)
            st = time.time()
            if parallel:
                proc_pool = ProcessPoolExecutor(max_workers=process_count)
                futures = {proc_pool.submit(acquire_data, table, **kw): kw
                           for kw in all_kwargs}
                for f in as_completed(futures):
                    df = f.result()
                    completed += 1
                    self.update_table_data(table, df, merge_type=merge_type)
                    time_elapsed = time.time() - st
                    time_remain = time_str_format((total - completed) * time_elapsed / completed,
                                                  estimation=True, short_form=False)
                    progress_bar(completed, total, f'time left: {time_remain}')
            else:
                for kwargs in all_kwargs:
                    df = self.acquire_table_data(table, 'tushare', **kwargs)
                    completed += 1
                    self.update_table_data(table, df, merge_type=merge_type)
                    time_elapsed = time.time() - st
                    time_remain = time_str_format((total - completed) * time_elapsed / completed,
                                                  estimation=True, short_form=False)
                    progress_bar(completed, total, f'time left: {time_remain}')
            print('task completed!')


# 以下函数是通用df操作函数
def set_primary_key_index(df, primary_key, pk_dtypes):
    """ df是一个DataFrame，primary key是df的某一列或多列的列名，将primary key所指的
    列设置为df的行标签，设置正确的时间日期格式，并删除primary key列后返回新的df

    :param df: 需要操作的DataFrame
    :param primary_key:
        List，需要设置为行标签的列名，所有列名必须出现在df的列名中
    :param pk_dtypes:
        List, 需要设置为行标签的列的数据类型，日期数据需要小心处理
    :return:
        None
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f'df should be a pandas DataFrame, got {type(df)} instead')
    if not isinstance(primary_key, list):
        raise TypeError(f'primary key should be a list, got {type(primary_key)} instead')
    all_columns = df.columns
    if not all(item in all_columns for item in primary_key):
        raise KeyError(f'primary key contains invalid value')

    # 设置正确的时间日期格式（找到pk_dtype中是否有"date"或"TimeStamp"类型，将相应的列设置为TimeStamp
    set_datetime_format_frame(df, primary_key, pk_dtypes)

    # 设置正确的Index或MultiIndex
    pk_count = len(primary_key)
    if pk_count == 1:
        # 当primary key只包含一列时，创建single index
        df.index = df[primary_key[0]]
    elif pk_count > 1:
        # 当primary key包含多列时，创建MultiIndex
        m_index = pd.MultiIndex.from_frame(df[primary_key])
        df.index = m_index
    else:
        # for other unexpected cases
        raise ValueError(f'wrong input!')
    df.drop(columns=primary_key, inplace=True)

    return None


# noinspection PyUnresolvedReferences
def set_primary_key_frame(df, primary_key, pk_dtypes):
    """ 与set_primary_key_index的功能相反，将index中的值放入DataFrame中，
        并重设df的index为0，1，2，3，4...


    :param df: 需要操作的df
    :param primary_key:
    :param pk_dtypes:
    :return:
        DataFrame
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f'df should be a pandas DataFrame, got {type(df)} instead')
    if not isinstance(primary_key, list):
        raise TypeError(f'primary key should be a list, got {type(primary_key)} instead')
    if not isinstance(pk_dtypes, list):
        raise TypeError(f'primary key should be a list, got {type(primary_key)} instead')
    idx_columns = list(df.index.names)
    pk_columns = primary_key
    if idx_columns != [None]:
        index_frame = df.index.to_frame()
        for col in idx_columns:
            df[col] = index_frame[col]
    df.index = range(len(df))
    # 此时primary key有可能被放到了columns的最后面，需要将primary key移动到columns的最前面：
    columns = df.columns.to_list()
    new_col = [col for col in columns if col not in pk_columns]
    new_col = pk_columns + new_col
    df = df.reindex(columns=new_col, copy=False)

    # 设置正确的时间日期格式（找到pk_dtype中是否有"date"或"TimeStamp"类型，将相应的列设置为TimeStamp
    set_datetime_format_frame(df, primary_key, pk_dtypes)

    return df


def set_datetime_format_frame(df, primary_key, pk_dtypes):
    """ 根据primary_key的rule为df的主键设置正确的时间日期类型

    :param df: 需要操作的df
    :param primary_key: 主键列
    :param pk_dtypes: 主键数据类型，主要关注"date" 和"TimeStamp"
    :return:
        None
    """
    # 设置正确的时间日期格式（找到pk_dtype中是否有"date"或"TimeStamp"类型，将相应的列设置为TimeStamp
    if ("date" in pk_dtypes) or ("TimeStamp" in pk_dtypes):
        # 需要设置正确的时间日期格式：
        # 有时候pk会包含多列，可能有多个时间日期，因此需要逐个设置
        for pk_item, dtype in zip(primary_key, pk_dtypes):
            if dtype in ['date', 'TimeStamp']:
                df[pk_item] = pd.to_datetime(df[pk_item])
    return None


def get_primary_key_range(df, primary_key, pk_dtypes):
    """ 给定一个dataframe，给出这个df表的主键的范围，用于下载数据时用作传入参数
        如果主键类型为string，则给出一个list，包含所有的元素
        如果主键类型为date，则给出上下界

    :param df: 需要操作的df
    :param primary_key: 以列表形式给出的primary_key列名
    :param pk_dtypes: primary_key的数据类型
    :return:
        dict，形式为{primary_key1: [values], 'start': start_date, 'end': end_date}
    """
    if df.index.name is not None:
        df = set_primary_key_frame(df, primary_key=primary_key, pk_dtypes=pk_dtypes)
    res = {}
    for pk, dtype in zip(primary_key, pk_dtypes):
        if (dtype == 'str') or (dtype[:7] == 'varchar'):
            res['shares'] = (list(set(df[pk].values)))
        elif dtype.lower() in ['date', 'timestamp', 'datetime']:
            res['start'] = df[pk].min()
            res['end'] = df[pk].max()
        else:
            raise KeyError(f'invalid dtype: {dtype}')
    return res


# noinspection PyTypeChecker
def get_built_in_table_schema(table):
    """ 给出数据表的名称，从相关TABLE中找到表的主键名称及其数据类型
    :param table:
        str, 表名称（注意不是表的结构名称）
    :return
        Tuple: 包含四个List，包括:
            columns: 整张表的列名称
            dtypes: 整张表所有列的数据类型
            primary_keys: 主键列名称
            pk_dtypes: 主键列的数据类型
    """
    if not isinstance(table, str):
        raise TypeError(f'table name should be a string, got {type(table)} instead')
    if table not in TABLE_SOURCE_MAPPING.keys():
        raise KeyError(f'invalid table name')

    table_structure = TABLE_SOURCE_MAPPING[table][TABLE_SOURCE_MAPPING_COLUMNS.index('structure')]
    structure = TABLE_STRUCTURES[table_structure]
    columns = structure['columns']
    dtypes = structure['dtypes']
    pk_loc = structure['prime_keys']
    primary_keys = [columns[i] for i in pk_loc]
    pk_dtypes = [dtypes[i] for i in pk_loc]

    return columns, dtypes, primary_keys, pk_dtypes