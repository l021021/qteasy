.. qteasy documentation master file, created by
   sphinx-quickstart on Sun Nov 19 21:52:20 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

欢迎使用 ``QTEASY`` 文档!
================================

.. image:: img/qteasy_logo_horizontal.png
    :width: 900px
    :align: center

.. note::

   目前 ``qteays`` 正处于密集开发测试阶段，软件中不免存在一些漏洞和bug，如果大家使用中出现问题，欢迎 `报告Issue`_ 或者提交 `新功能需求`_ 给我，也可以进入 `讨论区`_ 参与讨论。欢迎各位贡献代码！

.. _报告Issue: https://github.com/shepherdpp/qteasy/issues/new?assignees=&labels=&projects=&template=bug-report---bug报告.md&title=
.. _新功能需求: https://github.com/shepherdpp/qteasy/issues/new?assignees=&labels=&projects=&template=feature-request--功能需求.md&title=
.. _讨论区: https://github.com/shepherdpp/qteasy/discussions

- Author: **Jackie PENG**
- email: *jackie_pengzhao@163.com*
- Created: 2019, July, 16
- Latest Version: `1.3.11`
- License: BSD 3-Clause

Introduction
------------

``QTEASY`` 是为量化交易人员开发的一套量化交易策略开发工具包，基本功能如下：

1. 金融历史数据的获取、清洗、整理、可视化、本地存储查询及应用；支持多种数据存储方式，包括本地文件、MySQL数据库等，数据来源包括 ``Tushare`` 、 ``EastMoney`` 等
2. 投资交易策略的创建、回测、性能评价，并且通过定义策略的可调参数，提供多种优化算法实现交易策略的参数调优
3. 交易策略的部署、实盘运行、模拟交易结果、并跟踪记录交易日志、股票持仓、账户资金变化等信息

What Can You Do with ``QTEASY`` ?
-----------------------------

获取并管理金融历史数据
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- 获取、清洗、本地存储大量金融历史数据
- 检索、处理、调用本地数据

.. image:: img/output_3_4.png
    :width: 900px
    :align: center

- 本地金融数据可视化


创建交易策略，模拟自动化交易
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- 快速搭建交易策略，使用超过70中内置交易策略或自行创建交易策略
- 获取实时市场数据，运行策略模拟自动化交易
- 跟踪记录交易日志、股票持仓、账户资金变化等信息
- 通过多种用户界面查看并控制交易程序
- 未来将通过QMT接口接入券商提供的实盘交易接口，实现自动化交易

.. image:: examples/img/trader_app_1.png
    :width: 900px
    :align: center


.. image:: examples/img/trader_app_light_theme.png
    :width: 900px
    :align: center



回测、评价、优化交易策略
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- 使用历史数据回测交易策略，生成完整的历史交易清单，生成交易结果
- 对交易结果进行多维度全方位评价，生成交易报告和结果图标
- 提供多种优化算法，帮助搜索最优的策略参数，提高策略表现

.. image:: img/output_14_3.png
    :width: 900px
    :align: center



.. toctree::
   :caption: GETTING STARTED 快速入门
   :maxdepth: 1
   :glob:

   getting_started
   help
   roadmap.rst
   CONTRIBUTING
   CODE_OF_CONDUCT


.. toctree::
   :caption: TUTORIALS 使用教程
   :numbered: 2
   :maxdepth: 1
   :glob:

   tutorials/*


.. toctree::
    :caption: REFERENCES 参考文档
    :numbered: 2
    :maxdepth: 1
    :glob:

    references/*


.. toctree::
    :caption: EXAMPLES 自定义策略示例
    :numbered: 2
    :maxdepth: 1
    :glob:

    examples/*


.. toctree::
   :caption: API REFERENCE 参考
   :numbered: 1
   :maxdepth: 1
   :glob:

   api/api_reference.rst
   api/history_data.rst
   api/history_data_types.rst
   api/built_in_strategies.rst
   api/Strategies.rst
   api/use_qteasy.rst


.. toctree::
   :caption: RELEASE HISTORY 发行版本历史
   :maxdepth: 1
   :glob:

   RELEASE_HISTORY


.. toctree::
   :caption: LICENSE

   LICENSE


.. toctree::
   :caption: ABOUT 关于
   :maxdepth: 1
   :glob:

   about

.. toctree::
   :caption: FAQ 常见问题
   :maxdepth: 1
   :glob:

   faq

