from datetime import timedelta, datetime
from typing import List

from jdatetime import date, time

from tsetmc_api.cache import PersistentCache
from tsetmc_api.shareholder import SymbolMajorShareholder
from tsetmc_api.utils import get_timezone
from . import core as day_details_core
from .snapshot import Snapshot
from .trade import Trade


class SymbolDayDetails:
    def __init__(self, symbol, jyear: int, jmonth: int, jday: int):
        self.symbol = symbol
        self.date = date(year=jyear, month=jmonth, day=jday)
        self.greg_date = self.date.togregorian()

        self._load()

    def _load(self):
        cache_minor = f'{self.symbol.id}-{self.date.year}-{self.date.month}-{self.date.day}'
        if PersistentCache.exists('symbol_day_details', cache_minor):
            f = PersistentCache.fetch('symbol_day_details', cache_minor)
            self._final_shareholders = f['final_shareholders']
            self._initial_shareholders = f['initial_shareholders']
            self._trades = f['trades']
            self._snapshots = f['snapshots']
            return

        mdate = self.date.togregorian()
        data = day_details_core.load_intraday_data(self.symbol.id, mdate.year, mdate.month, mdate.day)
        symbol_details = self.symbol.get_details()

        self._final_shareholders = []
        for shdata in data['shareholders']:
            self._final_shareholders.append(SymbolMajorShareholder(self.symbol.id,
                                                                   company_isin=symbol_details['company_isin'],
                                                                   holder_name=shdata['name'],
                                                                   holder_id=shdata['id'],
                                                                   percentage=shdata['percentage'],
                                                                   shares_count=shdata['shares_count']))

        self._initial_shareholders = []
        for shdata in data['previous_shareholders']:
            self._initial_shareholders.append(SymbolMajorShareholder(self.symbol.id,
                                                                     company_isin=symbol_details['company_isin'],
                                                                     holder_name=shdata['name'],
                                                                     holder_id=shdata['id'],
                                                                     percentage=shdata['percentage'],
                                                                     shares_count=shdata['shares_count']))

        self._trades = Trade.from_raw_trades_data(data['trades'])

        self._snapshots = list(
            Snapshot.generate_snapshots_from_raw_day_detail_data(self.greg_date,
                                                                 data['price_data'],
                                                                 data['orders_data'])
        )

        PersistentCache.store('asset_day_details', cache_minor, {
            'final_shareholders': self._final_shareholders,
            'initial_shareholders': self._initial_shareholders,
            'trades': self._trades,
            'snapshots': self._snapshots,
        })

    def get_final_major_shareholders(self) -> List[SymbolMajorShareholder]:
        """
        سهامداران عمده در پایان روز
        """
        return self._final_shareholders

    def get_initial_major_shareholders(self) -> List[SymbolMajorShareholder]:
        """
        سهامداران عمده در ابتدای روز
        """
        return self._initial_shareholders

    def get_trades(self) -> List[Trade]:
        """
        معاملات
        """
        return self._trades

    def get_snapshots(self) -> List[Snapshot]:
        """
        تمام لحظات سهم در طور روز
        """
        return self._snapshots

    def get_snapshots_by_time(self, hour: int, minute: int, second: int) -> List[Snapshot]:
        """
        وضعیت سهم در زمان خاصی از روز
        """
        snapshots = []
        t = int(datetime(year=self.greg_date.year, month=self.greg_date.month, day=self.greg_date.day,
                         hour=hour, minute=minute, second=second, tzinfo=get_timezone()).timestamp())
        last_snapshot = None
        for snapshot in self._snapshots:
            if snapshot.time > t:
                if not snapshots:
                    return [last_snapshot]

                return snapshots

            if snapshot.time == t:
                snapshots.append(snapshot)

            last_snapshot = snapshot

        if not snapshots:
            return [last_snapshot]

        return snapshots

    def get_snapshots_by_rate(self, from_time: time, to_time: time, delta: timedelta) -> List[Snapshot]:
        """
        وضعیت سهم در لحظات مختلف روز در بازه‌هایی با طول pick_rate
        """
        ret = []
        start_datetime = datetime(year=self.greg_date.year, month=self.greg_date.month, day=self.greg_date.day,
                                  hour=from_time.hour, minute=from_time.minute, second=from_time.second,
                                  tzinfo=get_timezone())
        end_timestamp = int(datetime(year=self.greg_date.year, month=self.greg_date.month, day=self.greg_date.day,
                                     hour=to_time.hour, minute=to_time.minute, second=to_time.second,
                                     tzinfo=get_timezone()).timestamp())
        next_pick_datetime = start_datetime
        next_pick_timestamp = int(start_datetime.timestamp())
        last_snapshot = None
        for snapshot in self.get_snapshots():
            if snapshot.time > next_pick_timestamp:
                if last_snapshot:
                    snapshot_copy = last_snapshot.copy()
                    snapshot_copy.time = next_pick_timestamp
                    ret.append(snapshot_copy)
                    next_pick_datetime += delta
                    next_pick_timestamp = int(next_pick_datetime.timestamp())

            last_snapshot = snapshot
            if next_pick_timestamp > end_timestamp:
                break

        return ret
