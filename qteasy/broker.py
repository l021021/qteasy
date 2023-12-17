# coding=utf-8
# ======================================
# File:     broker.py
# Author:   Jackie PENG
# Contact:  jackie.pengzhao@gmail.com
# Created:  2023-04-09
# Desc:
#   class Broker for trader to submit
# trading orders and get trading results
# Broker classes are supposed to be
# inherited from Broker, representing
# different trading platforms or brokers
# ======================================

from queue import Queue
from abc import abstractmethod, ABCMeta
from threading import Thread

import pandas as pd
import numpy as np
import time

from qteasy import QT_CONFIG
from .utilfuncs import get_current_tz_datetime

CASH_DECIMAL_PLACES = QT_CONFIG['cash_decimal_places']
AMOUNT_DECIMAL_PLACES = QT_CONFIG['amount_decimal_places']


def _verify_trade_result(trade_result, order_qty):
    """ 检查result，确认是否符合基本要求:
    包括trade_result各个组份的类型是否正确、数据是否超过范围

    Parameters:
    -----------
    trade_result: tuple: (result_type, qty, filled_price, fee)
        result_type: str
        qty: float
        filled_price: float
        fee: float
    order_qty: float
        订单的报价数量
    """
    result_type, qty, filled_price, fee = trade_result

    if not isinstance(result_type, str):
        raise TypeError(f'result_type should be str, but got {type(result_type)}')
    if result_type not in ['filled', 'partial-filled', 'canceled']:
        raise ValueError(f'result_type should be one of ["filled", "canceled"], but got {result_type}')
    if not isinstance(qty, (int, float)):
        raise TypeError(f'qty should be int or float, but got {type(qty)}')
    if qty <= 0:
        raise ValueError(f'qty should be greater than 0, but got {qty}')
    if qty > order_qty:
        raise ValueError(f'qty should be less than or equal to order["qty"], but got {qty}')
    if not isinstance(filled_price, (int, float)):
        raise TypeError(f'filled_price should be int or float, but got {type(filled_price)}')
    if filled_price < 0:
        raise ValueError(f'filled_price should be greater than 0, but got {filled_price}')
    if result_type == 'canceled' and filled_price != 0:
        raise ValueError(f'filled_price should be 0 when result_type is "canceled", but got {filled_price}')
    if not isinstance(fee, (int, float)):
        raise TypeError(f'fee should be int or float, but got {type(fee)}')
    if fee < 0:
        raise ValueError(f'fee should be greater than 0, but got {fee}')

    return True


class Broker(object):
    """ Broker是交易所的抽象，它接受交易订单并返回交易结果

    BaseBroker定义了Broker的基本接口，所有的Broker都必须继承自BaseBroker，
    以实现不同交易所的接口

    Attributes:
    -----------
    order_queue: Queue
        交易订单队列，每个交易订单都是一个list，包含多个交易订单
    result_queue: Queue
        交易结果队列，每个交易结果都是一个list，包含多个交易结果
    status: str
        Broker的状态，可以是 'init', 'running', 'stopped', 'paused'
        - init: Broker刚刚创建，还没有开始运行
        - running: Broker正在运行, 接受交易订单并返回交易结果
        - stopped: Broker已经停止运行, 停止所有操作，未完成的订单将被丢弃，并退出主循环
        - paused: Broker暂停运行，未完成的订单将被暂停，可以接受交易订单，但不会返回交易结果

    Methods:
    --------
    register(debug=False, **kwargs):
        交易所的初始化程序，可以
    run()
        Broker的主循环，从order_queue中获取交易订单并处理，获得交易结果并放入result_queue中
    transaction(symbol, order_qty, order_price, direction, position='long', order_type='market'): abstract method
        一个Generator方法。交易所处理交易订单并获取交易结果, 在子类中必须实现这个方法
        这个方法在接受交易订单后，会以generator形式返回订单的处理结果，直至订单处理完毕或出现错误
    """
    __metaclass__ = ABCMeta

    def __init__(self):
        self.broker_name = 'BaseBroker'
        self.user_name = ''
        self.password = ''
        self.token = ''
        self.status = 'init'  # init, running, stopped, paused
        self.debug = False
        self.is_registered = False

        self.time_zone = 'local'
        self.init_time = get_current_tz_datetime(self.time_zone).strftime('%Y-%m-%d %H:%M:%S')

        self.order_queue = Queue()
        self.result_queue = Queue()
        self.broker_messages = Queue()

    def register(self, debug=False, **kwargs):
        """ Broker对象在开始运行前的注册过程，作用是设置broker的状态为is_registered
        Override这个函数，以添加更多处理

        只有is_registered == True时，broker才能够运行

        Parameters
        ----------
        debug: bool, default: False
            是否进入debug mode
        kwargs:

        Return
        ------
        None
        """
        # override this function if necessary
        self.is_registered = True
        self.debug = debug

    def log_out_broker(self):
        """ Broker对象在关闭前的处理过程。
        Override这个函数，以添加更多处理
        """
        # override this function if necessary
        pass

    def run(self):
        """ Broker的主循环，从order_queue中获取交易订单并处理，获得交易结果并放入result_queue中
        order_queue中的每一个交易订单都由transaction函数来处理并获取交易结果，transaction函数是
        一个Generator，可以分批返回交易结果，直至订单处理完毕或出现错误。每一个transaction都会在单
        独的线程中运行
        """
        if not self.is_registered:
            raise RuntimeError(f'broker is not registered!')
        if self.debug:
            self.post_message(f'is running...')
        self.status = 'init'
        while True:
            try:
                time.sleep(0.05)
                # 如果Broker处于暂停状态，则不处理交易订单
                if self.status == 'paused':
                    continue
                # 如果order_queue为空，则不处理交易订单
                if self.order_queue.empty():
                    continue

                # order_queue不为空，提取交易订单，在一个单独的thread中调用self._get_result()处理交易订单
                order = self.order_queue.get()
                t = Thread(target=self._get_result, args=order, daemon=True)
                # 启动get_result()，在得到result后将其放入result_queue中，直至运行结束
                t.start()

                if self.status == 'stopped':
                    # 如果Broker正常退出，处理尚未提取的交易订单，这些订单将不会被处理，会提示用户取消订单
                    if self.debug:
                        self.post_message(f'Broker is stopped, will check for un-processed orders...')
                    un_processed_orders = []
                    while not self.order_queue.empty():
                        un_processed_orders.append(self.order_queue.get())
                        self.order_queue.task_done()

                    if len(un_processed_orders) > 0:
                        self.post_message(f'Un-processed orders: {un_processed_orders}')

                    # 交易所关闭后的处理程序
                    self.log_out_broker()

            except KeyboardInterrupt:
                # 如果Broker被用户强制退出，处理尚未完成的交易订单
                if self.debug:
                    self.post_message('Broker will be stopped by user.')
                self.status = 'stopped'
                continue
            except Exception as e:
                # 如果Broker出现异常，打印异常信息，并继续运行
                self.post_message(f'Runtime exception: {e}, please check system log for details')
                if self.debug:
                    import traceback
                    traceback.print_exc()
                continue

        return

    def post_message(self, message: str, new_line=True):
        """ 将消息放入broker的消息队列
        """
        if self.debug:
            message = f'[DEBUG]-{message}'
        message = f'[{self.broker_name}]: {message}'
        if not new_line:
            message += '_R'
        self.broker_messages.put(message)

    def _parse_order(self, order):
        """ 解析交易订单，提取其关键信息，并将order的状态改为"submitted"

        Parameters:
        -----------
        order: dict 交易订单dict，详细信息如下:
            {'order_id': 订单ID,
             'pos_id': position ID,
             'direction',
             'order_type',
             'qty',
             'price',
             'submitted_time',
             'status'}

        Returns:
        --------
        order info: tuple(symbol, qty, price, direction, position)
        symbol:
        qty:
        price:
        direction:
        position:
        """

        if self.debug:
            self.post_message(f'_get_result():\nsubmit order components of order(ID) {order["order_id"]}:\n'
                              f'quantity:{order["qty"]}\norder_price={order["price"]}\n'
                              f'order_direction={order["direction"]}\n')
        pos_id = order['pos_id']
        from qteasy.trade_recording import get_position_by_id
        from qteasy import QT_DATA_SOURCE
        try:
            position = get_position_by_id(pos_id=pos_id, data_source=QT_DATA_SOURCE)
        except RuntimeError as e:
            raise RuntimeError(e)
        symbol = position['symbol']
        position = position['positions']
        qty = order['qty']
        price = order['price']
        direction = order['direction']
        order_type = order['order_type']
        return order_type, symbol, qty, price, direction, position

    def _get_result(self, order):
        """ 解析订单信息，将关键信息提交给transaction，获取交易结果后，解析交易结果，将结果放入result_queue

        Parameters:
        -----------
        order: dict 交易订单dict，详细信息如下:
            {'order_id': 订单ID,
             'pos_id': position ID,
             'direction',
             'order_type',
             'qty',
             'price',
             'submitted_time',
             'status'}

        Returns:
        --------
        raw_trade_result: dict, 初步交易结果dict,详细信息如下：
            {'order_id',
             'filled_qty',
             'price',
             'transaction_fee',
             'execution_time',
             'canceled_qty',
             'delivery_amount',
             'delivery_status'
             }
        """

        order_type, symbol, qty, price, direction, position = self._parse_order(order)
        for trade_result in self.transaction(
                order_type=order_type,
                symbol=symbol,
                order_qty=qty,
                order_price=price,
                direction=direction,
                position=position
        ):
            result_type, qty, filled_price, fee = trade_result
            _verify_trade_result(trade_result, qty)

            # 确认数据格式正确后，将数据圆整到合适的精度，并组装为raw_trade_result
            if self.debug:
                self.post_message(f'method: _get_result(): got transaction result for order(ID) {order["order_id"]}\n'
                                  f'result_type={result_type}, \nqty={qty}, \n'
                                  f'filled_price={filled_price}, \nfee={fee}')
            # 圆整qty、filled_qty和fee
            qty = round(qty, AMOUNT_DECIMAL_PLACES)
            filled_price = round(filled_price, CASH_DECIMAL_PLACES)
            transaction_fee = round(fee, CASH_DECIMAL_PLACES)

            filled_qty = 0
            canceled_qty = 0
            if result_type in ['filled', 'partial-filled']:
                filled_qty = qty
            elif result_type == 'canceled':
                canceled_qty = qty
            else:
                raise ValueError(f'Unknown result_type: {result_type}, should be one of ["filled", "canceled"]')

            current_datetime = get_current_tz_datetime(self.time_zone)
            raw_trade_result = {
                'order_id':        order['order_id'],
                'filled_qty':      filled_qty,
                'price':           filled_price,
                'transaction_fee': transaction_fee,
                'execution_time':  current_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                'canceled_qty':    canceled_qty,
                'delivery_amount': 0,
                'delivery_status': 'ND',
            }

            # 将trade_result放入result_queue
            if self.debug:
                self.post_message(f'method _get_result(): created raw trade result for order(ID) {order["order_id"]}:\n'
                                  f'{raw_trade_result}')
            self.result_queue.put(raw_trade_result)

        # 全部订单处理完毕或发生错误后结束
        return

    @abstractmethod
    def transaction(self, symbol, order_qty, order_price, direction, position='long', order_type='market'):
        """ 交易所处理交易订单并获取交易结果, 抽象方法，需要由用户在子类中实现
        应该将transaction定义为Generator，分批完成交易，并分批返回

        Parameters:
        -----------
        symbol: str
            交易标的股票代码
        order_qty: float
            挂单数量
        order_price: float
            交易报价
        direction: str
            交易订单方向，'buy' 或者 'sell'
        position: str, default 'long'
            交易订单的持仓方向，'long' 或者 'short'
        order_type: str, default 'market'
            交易订单类型，'market' 或者 'limit'

        Returns / Yields:
        -----------------
        tuple: (result_type, qty, price, fee)
            result_type: str 交易结果类型:
                'filled' - 成交,
                'partial_filled' - 部分成交,
                'canceled' - 取消
                'failed' - 失败
            qty: float
                成交/取消数量，这个数字应该小于等于order_qty，且大于等于0
            price: float
                成交价格, 如果是取消交易，价格为0或任意数字
            fee: float
                交易费用，交易费用应该大于等于0

        Notes:
        ------
        1. 成交结果可以分多次返回，直至运行结束或交易失败/取消
        2. 如果多次返回成交结果，需要使用yield关键字将method定义为一个generator

        Examples:
        ---------
        >>> broker = Broker()
        >>> # 交易所返回完全成交结果
        >>> broker.transaction(100, 10, 'buy')
        ('filled', 100, 10, 5)
        >>> # 交易所返回部分成交结果
        >>> broker.transaction(100, 10, 'buy')
        ('partial_filled', 50, 10, 5)
        >>> # 交易所返回分批成交结果
        >>> broker.transaction(200, 10, 'buy')
        ('partial_filled', 100, 10, 5)
        ('filled', 100, 1)
        >>> # 交易所返回取消结果
        >>> broker.transaction(100, 10, 'buy')
        ('canceled', 100, 0, 0)
        >>> # 交易所返回失败结果
        >>> broker.transaction(100, 10, 'buy')
        ('failed', 0, 0, 0)
        """
        pass


class SimpleBroker(Broker):
    """ SimpleBroker接到交易订单后，立即返回交易结果
    交易结果总是完全成交，根据moq调整交易批量，根据设定的交易费率计算交易费用，滑点是按照百分比计算的

    Parameters
    ----------
    """

    def __init__(self):
        super(SimpleBroker, self).__init__()
        self.broker_name = 'SimpleBroker'

    def transaction(self, symbol, order_qty, order_price, direction, position='long', order_type='market'):
        """ 订单立即成交

        Parameters:
        ----------
        symbol: str
            挂单交易标的股票代码
        order_qty: float
            挂单数量
        order_price: float
            挂单报价
        direction: str
            交易订单方向，'buy' 或者 'sell'
        position: str, default 'long'
            交易订单的持仓方向，'long' 或者 'short'
        order_type: str, default 'market'
            交易订单类型，'market' 或者 'limit'

        Yields:
        -------
        trade_results: tuple: (result_type, qty, price, fee)
            result_type: str 交易结果类型:
                'filled' - 成交,
                'partial_filled' - 部分成交,
                'canceled' - 取消
                'failed' - 失败
            qty: float
                成交/取消数量，这个数字应该小于等于order_qty，且大于等于0
            price: float
                成交价格, 如果是取消交易，价格为0或任意数字
            fee: float
                交易费用，交易费用应该大于等于0
        """
        total_filled = 0
        while total_filled < order_qty:
            qty = order_qty
            price = order_price
            fee: float = 5.
            trade_result = ('filled', qty, price, fee)
            yield trade_result

            total_filled += qty


class SimulatorBroker(Broker):
    """ QT 默认的模拟交易所，该交易所模拟真实的交易情况，从qt_config中读取交易费率、滑点等参数

    根据这些参数尽可能真实地模拟成交结果，特点如下：

    - 在收到交易订单后，根据订单类型和当前价格确认成交类型：
        - 如果订单类型是市价单：以当前价成交
        - 如果订单类型是限价单：若当前格低于叫买价，以当前价买入，若当前价高于叫卖价，以当前价卖出
    - 股票涨停时大概率买入交易失败，跌停时大概率卖出交易失败
    - 交易费率根据参数中的设置计算，包括固定费率、最低费用、滑点等
    """

    def __init__(self,
                 fee_rate_buy=0.0003,
                 fee_rate_sell=0.0001,
                 fee_min_buy=0.0,
                 fee_min_sell=0.0,
                 fee_fix_buy=0.0,
                 fee_fix_sell=0.0,
                 slipage=0.0,
                 moq_buy=0.0,
                 moq_sell=0.0,
                 delay=1.0,
                 price_deviation=0.0,
                 probabilities=(0.9, 0.08, 0.02)):
        """ 生成一个Broker对象

        Parameters
        ----------
        fee_rate_buy: float,
            买入操作的交易费率
        fee_rate_sell: float,
            卖出操作的交易费率
        fee_min_buy: float, default 0.0
            买入操作的最低交易费用
        fee_min_sell: float, default 0.0
            卖出操作的最低交易费用
        fee_fix_buy: float, default 0.0
            买入操作的固定交易费用，如果不为0，则忽略交易费率和最低费用
        fee_fix_sell: float, default 0.0
            卖出操作的固定交易费用，如果不为0，则忽略交易费率和最低费用
        slipage: float, default 0.0
            交易滑点, 当交易数量很大时，交易费用会被放大 slipage * (qty / 100) ** 2 倍
        moq_buy: float, default 0.0
            买入操作最小数量
        moq_sell: float, default 0.0
            卖出操作最小数量
        delay: float, default 1.0
            模拟交易延迟，单位为秒
        price_deviation: float, default 0.0
            模拟成交价格允许误差值。例如，当前价格100元，误差值为0.01，即允许价格误差为100*0.01 = 1元
            此时买入报价大于100-1元即可成交
            卖出报价小于100+1元即可成交
        probabilities: tuple of 3 floats, default (0.90, 0.08, 0.02)
            模拟完全成交、部分成交和未成交三种情况出现的概率

        """
        super(SimulatorBroker, self).__init__()
        self.broker_name = 'SimulatorBroker'
        self.fee_rate_buy = fee_rate_buy
        self.fee_rate_sell = fee_rate_sell
        self.fee_min_buy = fee_min_buy
        self.fee_min_sell = fee_min_sell
        self.fee_fix_buy = fee_fix_buy
        self.fee_fix_sell = fee_fix_sell
        self.slipage = slipage
        self.moq_buy = moq_buy
        self.moq_sell = moq_sell
        self.delay = delay
        self.price_deviation = price_deviation
        self.probabilities = probabilities

    def transaction(self, symbol, order_qty, order_price, direction, position='long', order_type='market'):
        """ 读取实时价格模拟成交结果
        """

        total_filled = 0

        while total_filled < order_qty:

            import time
            time.sleep(1)  # 每秒进行一次检查
            # 获取当前实时价格
            from .emfuncs import stock_live_kline_price
            live_prices = stock_live_kline_price(symbol, freq='D', verbose=True, parallel=False)
            if not live_prices.empty:
                live_prices['close'] = live_prices['close'].astype('float')
                change = (live_prices['close'] / live_prices['pre_close'] - 1).iloc[-1]
                live_price = live_prices.close.iloc[-1]
                price_deviation = live_price * self.price_deviation
            else:
                raise ValueError(f'live price of symbol {symbol} can not be acquired at the moment...')

            # 如果当前价高于挂卖价(允许误差由price_deviation控制)，大概率成交或部分成交
            if (live_price >= order_price - price_deviation) and (direction == 'sell'):
                result_type = np.random.choice(['filled', 'partial-filled', 'canceled'], p=self.probabilities)
                # 如果change非常接近-10%(跌停)，则非常大概率canceled
                if abs(change + 0.1) <= 0.001:
                    self.post_message(f'order will be probably canceled because -10% sell-limit')
                    result_type = np.random.choice(['filled', 'partial-filled', 'canceled'], p=(0.01, 0.01, 0.98))
            # 如果当前价低于挂买价(允许误差由price_deviation控制), 大概率成交或部分成交
            elif (live_price <= order_price + price_deviation) and (direction == 'buy'):
                result_type = np.random.choice(['filled', 'partial-filled', 'canceled'], p=self.probabilities)
                # 如果change非常接近+10%(涨停)，则非常大概率canceled
                if abs(change - 0.1) <= 0.001:
                    self.post_message(f'order will be probably canceled because +10% buy-limit')
                    result_type = np.random.choice(['filled', 'partial-filled', 'canceled'], p=(0.01, 0.01, 0.98))

            elif (order_type == 'market') and (-0.098 < change < 0.098):
                # 市价单，只要不涨停跌停即可市价成交
                result_type = np.random.choice(['filled', 'partial-filled', 'canceled'], p=self.probabilities)
            else:
                # 当前无法成交，等待下次成交
                self.post_message('quoted price does not meet current price, order will be canceled')
                result_type = 'canceled'

            # 根据成交类型生成成交结果，并yield结果
            if result_type in ['filled', 'partial-filled']:
                # 部分成交及全部成交，计算成交数量
                filled_proportion = 1
                if result_type == 'partial-filled':
                    filled_proportion = np.random.choice([0.25, 0.5, 0.75], p=[0.3, 0.5, 0.2])  # 模拟交易所的部分成交
                remain_qty = order_qty - total_filled
                qty = remain_qty * filled_proportion
                if self.moq_buy > 0:
                    qty = np.trunc(qty / self.moq_buy) * self.moq_buy
                    if (qty < self.moq_buy) and (remain_qty > self.moq_buy):
                        qty = self.moq_buy  # 如果成交数量小于moq，但是剩余数量大于moq，那么成交数量就是moq
                    elif (qty < self.moq_buy) and (remain_qty <= self.moq_buy):
                        qty = remain_qty  # 如果成交数量小于moq，且剩余数量也小于moq，那么成交数量就是剩余数量
                        result_type = 'filled'
                # 如果确认成交，成交价格为当前价格
                order_price = live_price
                # 计算交易费用，根据买入/卖出费率计算
                if direction == 'buy':
                    transaction_fee = \
                        max(qty * order_price * self.fee_rate_buy, self.fee_min_buy) \
                            if self.fee_fix_buy == 0 \
                            else self.fee_fix_buy
                elif direction == 'sell':
                    transaction_fee = \
                        max(qty * order_price * self.fee_rate_sell, self.fee_min_sell) \
                            if self.fee_fix_sell == 0 \
                            else self.fee_min_sell
                else:
                    raise RuntimeError(f'invalid direction: {direction}')
                # 模拟交易滑点, 交易数量越大，对交易费用产生的影响越大
                if self.slipage > 0:
                    transaction_fee *= (1 + self.slipage * (qty / 100) ** 2)

                total_filled += qty

            elif result_type in ['canceled']:  # result_type == 'canceled'
                transaction_fee = 0
                order_price = 0
                qty = order_qty - total_filled

            else:
                # 本次无法成交，等待下次
                continue

            order_result = (result_type, qty, order_price, transaction_fee)
            yield order_result


class NotImplementedBroker(Broker):
    """ NotImplementedBroker raises NotImplementedError when __init__() is called
    """

    def __init__(self):
        super(NotImplementedBroker, self).__init__()
        raise NotImplementedError('NotImplementedBroker is not implemented yet')

    def transaction(self, symbol, order_qty, order_price, direction, position='long', order_type='market'):
        pass


def get_broker(name: str = 'simulator', params=None):
    """ get broker object by broker name

    Parameters
    ----------
    name:str default: simulator
        the broker name
    params: dict or None
        the parameters of broker

    Return
    ------
    Broker
    """
    all_brokers = {
        'random':    SimulatorBroker,
        'simple':    SimpleBroker,
        'manual':    NotImplementedBroker,
        'simulator': SimulatorBroker,
    }
    names_to_be_deprecated = {'random': 'simulator'}

    if not isinstance(name, str):
        raise TypeError(f'name must be a string, got {type(name)}')

    if name in names_to_be_deprecated:
        import warnings
        warnings.warn(f'the broker {name} will be deprecated in next version, '
                      f'use {names_to_be_deprecated[name]} instead')
    broker_func = all_brokers.get(name, SimulatorBroker)
    if params is not None:
        return broker_func(**params)
    return broker_func()
