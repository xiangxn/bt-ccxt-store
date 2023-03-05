import sys
sys.path.append(".")
import time
from datetime import datetime

import backtrader as bt

from ccxtbt import CCXTFeed


def main():
    class TestStrategy(bt.Strategy):
        def __init__(self):
            self.next_runs = 0

        def next(self, dt=None):
            dt = dt or self.datas[0].datetime.datetime(0)
            print('%s closing price: %s' % (dt.isoformat(), self.datas[0].close[0]))
            self.next_runs += 1

    cerebro = bt.Cerebro()

    cerebro.addstrategy(TestStrategy)

    # Add the feed
    cerebro.adddata(CCXTFeed(
                            debug=True,
                            exchange='binance',
                             dataname='BNB/USDT',
                             timeframe=bt.TimeFrame.Minutes,
                            #  fromdate=datetime(2019, 1, 1, 0, 0),
                            #  todate=datetime(2019, 1, 1, 0, 2),
                             compression=5,
                             ohlcv_limit=2,
                             currency='BNB',
                             retries=5,

                             # 'apiKey' and 'secret' are skipped
                             config={'proxies':{ 'https': "http://127.0.0.1:8001", 'http': "http://127.0.0.1:8001"},'enableRateLimit': True, 'nonce': lambda: str(int(time.time() * 1000))}))

    # Run the strategy
    cerebro.run()


if __name__ == '__main__':
    main()
