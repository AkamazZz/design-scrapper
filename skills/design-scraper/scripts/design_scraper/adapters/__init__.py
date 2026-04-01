from .base import AdapterRegistry, PlaceholderAdapter, SourceAdapter
from .app_store import AppStoreAdapter
from .awwwards import AwwwardsAdapter
from .behance import BehanceAdapter
from .dribbble import DribbbleAdapter
from .generic import DirectMediaAdapter, OpenGraphAdapter
from .mobbin import MobbinAdapter
from .pinterest import PinterestAdapter


def build_default_registry() -> AdapterRegistry:
    adapters: list[SourceAdapter] = [
        DribbbleAdapter(),
        MobbinAdapter(),
        AppStoreAdapter(),
        BehanceAdapter(),
        PinterestAdapter(),
        AwwwardsAdapter(),
        DirectMediaAdapter(),
        OpenGraphAdapter(),
    ]
    return AdapterRegistry(adapters)
