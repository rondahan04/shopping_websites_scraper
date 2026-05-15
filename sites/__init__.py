"""Site adapter registry."""

from sites.amazon import AmazonAdapter
from sites.bestbuy import BestBuyAdapter
from sites.newegg import NeweggAdapter
from sites.walmart import WalmartAdapter

ALL_ADAPTERS = [
    AmazonAdapter(),
    BestBuyAdapter(),
    WalmartAdapter(),
    NeweggAdapter(),
]
