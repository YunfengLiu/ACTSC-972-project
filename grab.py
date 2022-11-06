import yfinance as yf
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
import plotly.graph_objects as go


class Grab:
    def __init__(self, use_close=False):
        # use_close is flag for improving the original exit procedure,
        # if use_close is true, we exit holding/shorted positions with close price instead
        self.use_close = use_close

    # feed is a dataframe of daily OHLC data

    def trade(self, N_near, N_far, feed):
        trend = 0
        shares = 0  # number of shares holding
        cash = 10  # cash balance. Start with 0 cash

        far_support = None
        far_resistance = None
        near_support = None
        near_resistance = None

        feed.loc[feed.index, "Trend"] = 0
        feed.loc[feed.index, "Near support"] = None
        feed.loc[feed.index, "Near resistance"] = None
        feed.loc[feed.index, "Far support"] = None
        feed.loc[feed.index, "Far resistance"] = None
        feed.loc[feed.index, "Shares"] = 0
        feed.loc[feed.index, "Price"] = None
        feed.loc[feed.index, "Cash"] = None

        dates = []

        for window in feed.rolling(window=N_far):
            market = window.iloc[-1]
            ts = market.name  # timestamp of the current market
            close = market["Close"]
            high = market["High"]
            low = market["Low"]
            price = None
            # if ts == pd.Timestamp('2022-10-13'):
            #     print("Pause")
            if len(window) < N_far:
                # feed.loc[ts, "Cash"] = cash
                continue

            if far_support is None:
                near = window.tail(N_near)
                far_support = window["Low"].min()
                far_resistance = window["High"].max()
                near_support = near["Low"].min()
                near_resistance = near["High"].max()
                continue

            feed.at[ts, "Far support"] = far_support
            feed.at[ts, "Far resistance"] = far_resistance
            feed.at[ts, "Near support"] = near_support
            feed.at[ts, "Near resistance"] = near_resistance

            # decide trend
            prev_trend = trend
            if close > far_resistance:
                trend = 1
            elif close < far_support:
                trend = -1

            # if trend is not triggered yet, continue to next day
            # until trend is triggered (i.e. not equal to 0)
            if trend == 0:
                continue

            # if trend is up
            if trend == 1:
                # if trend is switched, then exit any existing short positions
                # by buying back shorted position at near support level.
                # we are assuming we can always execute the trade at
                # the near support level.
                if prev_trend != trend and shares != 0:
                    # record the profit and loss for the exit trade
                    # note that this may not be executed in real trading environment
                    # when trend is reversed, the buy back at near_resistance is far
                    # below the spot price because spot is above the far resistance
                    # level.
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Exit buying back {shares} share at ${near_support}")
                    price = close if self.use_close else near_resistance
                    cash = cash + shares * price
                    shares = 0  # exit all positons

                # if trend is not switched
                # and if the close price breaks the near support
                # and we are not holding any share, then buy one share
                # at the near support level (assuming trades can always be executed)
                elif close <= near_support and shares == 0:
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Buying 1 share at ${near_support}")
                    price = near_support
                    shares = 1
                    cash = cash - shares * price
                # if trend is not switched
                # and if close price breaks the near resistance
                # and we are holding a share, then sell the holding shares
                # at the near resistance level
                elif close >= near_resistance and shares != 0:
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Selling 1 share at ${near_resistance}")
                    price = near_resistance
                    cash = cash + shares * price
                    shares = 0
            elif trend == -1:
                # if trend is switched, then exit any existing long positions
                # by selling any holding position at near resistence level.
                # we are assuming we can always execute the trade at
                # the near support level.
                if prev_trend != trend and shares != 0:
                    # record the profit and loss for the exit trade
                    # note that this may not be executed in real trading environment
                    # when trend is reversed, the selling at near_support
                    # level is far above the spot price because spot is below
                    # the far support level.
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Exit selling {shares} share at ${near_resistance}")
                    price = close if self.use_close else near_support
                    cash = cash + shares * price
                    shares = 0
                # if trend is not switched
                # and if close price breaks the near resistance
                # and we are not holding any share, then short sell a share
                # at the near resistance level
                elif close <= near_resistance and shares == 0:
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Shorting 1 share at ${near_resistance}")
                    price = near_resistance
                    shares = -1
                    cash = cash - shares * price
                # if trend is not switched
                # and if the close price breaks the near support
                # and we have short sell a share, then buy one share
                # at the near support level (assuming trades can always be executed)
                elif close >= near_support and shares == 0:
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Buying 1 share at ${near_support}")
                    price = near_support
                    cash = cash + shares * price
                    shares = 0

            feed.at[ts, "Price"] = price
            feed.at[ts, "Cash"] = cash
            feed.at[ts, "Trend"] = trend
            feed.at[ts, "Shares"] = shares

            # print(f"Time: {ts}, {trend}, shares:{shares}, cash:{cash}")

            near = window.tail(N_near)
            far_support = window["Low"].min()
            far_resistance = window["High"].max()
            near_support = near["Low"].min()
            near_resistance = near["High"].max()

        # if we are still holding or shorting any share, exit them all at close price
        if shares != 0:
            cash = cash + shares * close
            feed.at[ts, "Price"] = close
            feed.at[ts, "Cash"] = cash
            feed.at[ts, "Trend"] = trend
            feed.at[ts, "Shares"] = 0

        return feed

    # find the optimal N_f, N_r
    def find_optimal_N(self, M, feed):
        n = len(feed)
        # initial cash and N_f, N_r
        cash = -1000000
        N_f = 4
        N_n = 2
        for Nf in range(4, M):
            for Nn in range(2, Nf - 1):
                grab = Grab()
                hist = grab.trade(Nn, Nf, feed.copy())
                cash2 = final_balance(hist)
                # if this setting produce higher cash, then remember this setting
                if cash2 > cash:
                    cash = cash2
                    N_f = Nf
                    N_n = Nn
        return (N_f, N_n, cash)

    def optimal_trade(self, M, feed):
        trend = 0
        shares = 0  # number of shares holding
        cash = 10  # cash balance. Start with 0 cash

        far_support = None
        far_resistance = None
        near_support = None
        near_resistance = None

        feed.loc[feed.index, "Trend"] = 0
        feed.loc[feed.index, "Near support"] = None
        feed.loc[feed.index, "Near resistance"] = None
        feed.loc[feed.index, "Far support"] = None
        feed.loc[feed.index, "Far resistance"] = None
        feed.loc[feed.index, "Shares"] = 0
        feed.loc[feed.index, "Price"] = None
        feed.loc[feed.index, "Cash"] = None

        dates = []

        for window in feed.rolling(window=M):

            market = window.iloc[-1]
            ts = market.name  # timestamp of the current market
            close = market["Close"]
            high = market["High"]
            low = market["Low"]
            price = None
            # if ts == pd.Timestamp('2022-10-13'):
            #     print("Pause")
            if len(window) < M:
                # feed.loc[ts, "Cash"] = cash
                continue

            N_far, N_near, cash2 = self.find_optimal_N(M, feed.loc[:ts].copy())
            print(f"N_far:{N_far}, N_near:{N_near}, cash2: {cash2}")

            if far_support is None:
                near = window.tail(N_near)
                far_support = window["Low"].min()
                far_resistance = window["High"].max()
                near_support = near["Low"].min()
                near_resistance = near["High"].max()
                continue

            feed.at[ts, "Far support"] = far_support
            feed.at[ts, "Far resistance"] = far_resistance
            feed.at[ts, "Near support"] = near_support
            feed.at[ts, "Near resistance"] = near_resistance
            feed.at[ts, "N_far"] = N_far
            feed.at[ts, "N_near"] = N_near

            # decide trend
            prev_trend = trend
            if close > far_resistance:
                trend = 1
            elif close < far_support:
                trend = -1

            # if trend is not triggered yet, continue to next day
            # until trend is triggered (i.e. not equal to 0)
            if trend == 0:
                continue

            # if trend is up
            if trend == 1:
                # if trend is switched, then exit any existing short positions
                # by buying back shorted position at near support level.
                # we are assuming we can always execute the trade at
                # the near support level.
                if prev_trend != trend and shares != 0:
                    # record the profit and loss for the exit trade
                    # note that this may not be executed in real trading environment
                    # when trend is reversed, the buy back at near_resistance is far
                    # below the spot price because spot is above the far resistance
                    # level.
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Exit buying back {shares} share at ${near_support}")
                    price = close if self.use_close else near_resistance
                    cash = cash + shares * price
                    shares = 0  # exit all positons

                # if trend is not switched
                # and if the close price breaks the near support
                # and we are not holding any share, then buy one share
                # at the near support level (assuming trades can always be executed)
                elif close <= near_support and shares == 0:
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Buying 1 share at ${near_support}")
                    price = near_support
                    shares = 1
                    cash = cash - shares * price
                # if trend is not switched
                # and if close price breaks the near resistance
                # and we are holding a share, then sell the holding shares
                # at the near resistance level
                elif close >= near_resistance and shares != 0:
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Selling 1 share at ${near_resistance}")
                    price = near_resistance
                    cash = cash + shares * price
                    shares = 0
            elif trend == -1:
                # if trend is switched, then exit any existing long positions
                # by selling any holding position at near resistence level.
                # we are assuming we can always execute the trade at
                # the near support level.
                if prev_trend != trend and shares != 0:
                    # record the profit and loss for the exit trade
                    # note that this may not be executed in real trading environment
                    # when trend is reversed, the selling at near_support
                    # level is far above the spot price because spot is below
                    # the far support level.
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Exit selling {shares} share at ${near_resistance}")
                    price = close if self.use_close else near_support
                    cash = cash + shares * price
                    shares = 0
                # if trend is not switched
                # and if close price breaks the near resistance
                # and we are not holding any share, then short sell a share
                # at the near resistance level
                elif close <= near_resistance and shares == 0:
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Shorting 1 share at ${near_resistance}")
                    price = near_resistance
                    shares = -1
                    cash = cash - shares * price
                # if trend is not switched
                # and if the close price breaks the near support
                # and we have short sell a share, then buy one share
                # at the near support level (assuming trades can always be executed)
                elif close >= near_support and shares == 0:
                    # print(
                    #     f"{ts}:{prev_trend}:{trend}: Buying 1 share at ${near_support}")
                    price = near_support
                    cash = cash + shares * price
                    shares = 0

            feed.at[ts, "Price"] = price
            feed.at[ts, "Cash"] = cash
            feed.at[ts, "Trend"] = trend
            feed.at[ts, "Shares"] = shares

            # print(f"Time: {ts}, {trend}, shares:{shares}, cash:{cash}")

            near = window.tail(N_near)
            far_support = window["Low"].min()
            far_resistance = window["High"].max()
            near_support = near["Low"].min()
            near_resistance = near["High"].max()

        # if we are still holding or shorting any share, exit them all at close price
        if shares != 0:
            cash = cash + shares * close
            feed.at[ts, "Price"] = close
            feed.at[ts, "Cash"] = cash
            feed.at[ts, "Trend"] = trend
            feed.at[ts, "Shares"] = 0

        return feed

    def plot(self, trade_hist):
        mpf.plot(trade_hist, type='candle')
        plt.plot(trade_hist["Near support"], label="Near support")
        plt.plot(trade_hist["Near resistance"], label="Near resistance")
        plt.plot(trade_hist["Far support"], label="Far support")
        plt.plot(trade_hist["Far resistance"], label="Far resistance")
        # plt.plot(trade_hist["Shares"], label="Shares")
        plt.legend()
        plt.show()
        plt.plot(trade_hist["Cash"] + trade_hist["Shares"]
                 * trade_hist["Close"], label="Cash")
        plt.show()

    def plot2(self, trade_hist):
        fig = go.Figure(data=[go.Candlestick(x=trade_hist.index,
                                             open=trade_hist['Open'],
                                             high=trade_hist['High'],
                                             low=trade_hist['Low'],
                                             close=trade_hist['Close'], name="Candlestick")])
        fig.add_trace(go.Line(x=trade_hist.index,
                      y=trade_hist["Near support"], name="Near support"))
        fig.add_trace(go.Line(x=trade_hist.index,
                      y=trade_hist["Near resistance"], name="Near resistance"))
        fig.add_trace(go.Line(x=trade_hist.index,
                      y=trade_hist["Far support"], name="Far support"))
        fig.add_trace(go.Line(x=trade_hist.index,
                      y=trade_hist["Far resistance"], name="Far resistance"))
        # fig.add_line(x=trade_hist.index, y=trade_hist["Near support"])
        fig.show()


# get the final cash balance
def final_balance(trade_hist):
    return trade_hist.iloc[-1]["Cash"]


class OptimalGRAB:
    def __init__(self, M):
        self.M = M

    def trade(self, feed):
        n = len(feed)
        N_n = 10
        N_f = 20
        for i in range(self.M, n):
            feed2 = feed.iloc[0:i]
            # find optimal N_f, N_r
            N_f, N_n = self.find_optimal(feed2)
            ts = feed2.iloc[-1].name
            feed.at[ts, "Far support"] = feed2.iloc[-1]["Far support"]
            feed.at[ts, "Far resistance"] = feed2.iloc[-1]["Far resistance"]
            feed.at[ts, "Near support"] = feed2.iloc[-1]["Near support"]
            feed.at[ts, "Near resistance"] = feed2.iloc[-1]["Near resistance"]
            feed.at[ts, "Trend"] = feed2.iloc[-1]["Trend"]
            feed.at[ts, "Shares"] = feed2.iloc[-1]["Shares"]
            feed.at[ts, "Price"] = feed2.iloc[-1]["Price"]
            feed.at[ts, "Cash"] = feed2.iloc[-1]["Cash"]
            feed.at[ts, "Price"] = feed2.iloc[-1]["Price"]
            feed.at[ts, "N_f"] = N_f
            feed.at[ts, "N_n"] = N_n


# msft = yf.Ticker("AAPL")
# hist = msft.history(start="2022-01-01")
# hist = hist[["Open", "High", "Low", "Close"]]
# algo = Grab()
# trade_hist = algo.optimal_trade(50, hist)

# trade_hist.to_csv("optimal_trade.csv")
# algo.plot(trade_hist)


# # print(trade_hist.tail())
# print("Pause")
