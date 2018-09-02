#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015, 2016, 2017 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import collections
from backtrader.position import Position
from backtrader import BrokerBase, OrderBase, Order
from backtrader.utils.py3 import queue, with_metaclass
from .ccxtstore import CCXTStore

class CCXTOrder(OrderBase):
    def __init__(self, owner, data, ccxt_order):
        self.owner = owner
        self.data = data
        self.ccxt_order = ccxt_order
        self.ordtype = self.Buy if ccxt_order['side'] == 'buy' else self.Sell
        self.size = float(ccxt_order['amount'])

        super(CCXTOrder, self).__init__()

class MetaCCXTBroker(BrokerBase.__class__):
    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaCCXTBroker, cls).__init__(name, bases, dct)
        CCXTStore.BrokerCls = cls

class CCXTBroker(with_metaclass(MetaCCXTBroker, BrokerBase)):
    '''Broker implementation for CCXT cryptocurrency trading library.
    This class maps the orders/positions from CCXT to the
    internal API of ``backtrader``.

    Broker mapping added as I noticed that there differences between the expected
    order_types and retuned status's from canceling an order

    Added a new mappings parameter to the script with defaults.

    self.balance_checks can be overwritten in the strategy to stop making a getbalance()
    call. Useful when backfilling. It should be set by the strategy to pause and also
    restart the checks

    The broker mapping should contain a new dict for order_types and mappings like below:

    broker_mapping = {
        'order_types': {
            bt.Order.Market: 'market',
            bt.Order.Limit: 'limit',
            bt.Order.Stop: 'stop-loss', #stop-loss for kraken, stop for bitmex
            bt.Order.StopLimit: 'stop limit'
        },
        'mappings':{
            'closed_order':{
                'key': 'status',
                'value':'closed'
                },
            'canceled_order':{
                'key': 'result',
                'value':1}
                }
        }
    '''

    order_types = {Order.Market: 'market',
                   Order.Limit: 'limit',
                   Order.Stop: 'stop', #stop-loss for kraken, stop for bitmex
                   Order.StopLimit: 'stop limit'}

    mappings = {
        'closed_order':{
            'key': 'status',
            'value':'closed'
            },
        'canceled_order':{
            'key': 'status',
            'value':'canceled'}
            }


    def __init__(self, broker_mapping=None, **kwargs):
        super(CCXTBroker, self).__init__()
        if broker_mapping is not None:
            self.order_types = broker_mapping['order_types']
            self.mappings = broker_mapping['mappings']

        #self.o = oandav20store.OandaV20Store(**kwargs)
        #self.store = CCXTStore(exchange, config, retries)

        self.store = CCXTStore(**kwargs)

        self.currency = self.store.currency

        self.positions = collections.defaultdict(Position)

        self.notifs = queue.Queue()  # holds orders which are notified

        self.open_orders = list()

        self.balance_checks = True

        self.startingcash  = self.store._cash
        self.startingvalue = self.store._value


    def getcash(self):
        # Get cash seems to always be called before get value
        # Therefore it makes sense to add getbalance here.
        if self.balance_checks:
            self.store.getbalance(self.currency)
        #return self.store.getcash(self.currency)
        return self.store._cash

    def getvalue(self, datas=None):
        #return self.store.getvalue(self.currency)
        return self.store._value

    def get_notification(self):
        try:
            return self.notifs.get(False)
        except queue.Empty:
            return None

    def notify(self, order):
        self.notifs.put(order)

    def getposition(self, data, clone=True):
        # return self.o.getposition(data._dataname, clone=clone)
        pos = self.positions[data._dataname]
        if clone:
            pos = pos.clone()

        return pos

    def next(self):

        for o_order in list(self.open_orders):
            oID = o_order.ccxt_order['id']
            ccxt_order = self.store.fetch_order(oID)
            if ccxt_order[self.mappings['closed_order']['key']] == self.mappings['closed_order']['value']:
                pos = self.getposition(o_order.data, clone=False)
                pos.update(o_order.size, o_order.price)
                o_order.completed()
                self.notify(o_order)
                self.open_orders.remove(o_order)

    def _submit(self, owner, data, exectype, side, amount, price, params):
        order_type = self.order_types.get(exectype) if exectype else 'market'
        # Extract CCXT specific params if passed to the order
        params = params['params'] if 'params' in params else params
        _order = self.store.create_order(symbol=data.symbol, order_type=order_type, side=side,
                                         amount=amount, price=price, params=params)

        order = CCXTOrder(owner, data, _order)
        self.open_orders.append(order)
        #pos = self.getposition(data, clone=False)
        #pos.update(order.size, order.price)

        self.notify(order)
        return order

    def buy(self, owner, data, size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None,
            **kwargs):
        return self._submit(owner, data, exectype, 'buy', size, price, kwargs)

    def sell(self, owner, data, size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None,
             **kwargs):
        return self._submit(owner, data, exectype, 'sell', size, price, kwargs)

    def cancel(self, order):

        oID = order.ccxt_order['id']
        # check first if the order has already been filled otherwise an error
        # might be raised if we try to cancel an order that is not open.
        ccxt_order = self.store.fetch_order(oID)
        if ccxt_order[self.mappings['closed_order']['key']] == self.mappings['closed_order']['value']:
            return order

        ccxt_order = self.store.cancel_order(oID)
        if ccxt_order[self.mappings['canceled_order']['key']] == self.mappings['canceled_order']['value']:
            self.open_orders.remove(order)
            order.cancel()
            self.notify(order)
        return order

    def get_orders_open(self, safe=False):
        return self.store.fetch_open_orders()