"""FX / Macro vertical — momentum backtesting + macro-news research.

Ported from the standalone `macrohero` app into the assethero platform. Mounted
under /fx/* by app.py via ``verticals.fx.routes.register``. Heavy dependencies
(yfinance, feedparser, newspaper, tavily, langchain_openai, numpy) are imported
lazily inside functions so ``import verticals.fx.routes`` succeeds without them.
"""
