import json
import os
import sys
import time
import typing
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TypeAlias

Value: TypeAlias = str | int | float | bool
Timestamp: TypeAlias = int | float | datetime


class MetricRecorder(ABC):
    def record(self, metric: str, value_name: str, value: Value, ts: Timestamp | None = None, **attributes) -> None:
        self.record_many(metric, {value_name: value}, ts, **attributes)

    @abstractmethod
    def record_many(self, metric: str, values: dict[str, Value], ts: Timestamp | None = None, **attributes) -> None:
        raise NotImplementedError()


class InfluxLineProtocolMetricsRecorder(MetricRecorder, ABC):
    def record_many(self, metric: str, values: dict[str, Value], ts: Timestamp | None = None, **attributes) -> None:
        if len(values) == 0:
            return
        if ts is None:
            ts = time.time()
        fields = ','.join(f'{k}={self._value_to_influx(v)}' for k, v in values.items())
        attrs = ''.join(f',{k}={self._value_to_influx(v)}' for k, v in attributes.items())
        line = f'{metric}{attrs} {fields} {self._ts_to_influx(ts)}\n'
        writer = self.get_writer()
        writer.write(line.encode('utf-8'))
        writer.flush()

    @classmethod
    def _ts_to_influx(cls, ts: Timestamp) -> str:
        if isinstance(ts, datetime):
            ts = ts.timestamp()
        return str(int(ts * 1000000000))

    @classmethod
    def _value_to_influx(cls, value: Value) -> str:
        if isinstance(value, int):
            return f'{value}i'
        elif isinstance(value, str):
            return json.dumps(value)
        return str(value)

    @abstractmethod
    def get_writer(self) -> typing.BinaryIO:
        raise NotImplementedError()


class TelegrafTailMetricsRecorder(InfluxLineProtocolMetricsRecorder):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.file: typing.BinaryIO | None = None

    def get_writer(self) -> typing.BinaryIO:
        if self.file is None:
            self.file = open(self.filename, 'ab')
        return self.file


class TelegrafBufferMetricsRecorder(InfluxLineProtocolMetricsRecorder):
    def __init__(self, writer: typing.BinaryIO) -> None:
        self.file = writer

    def get_writer(self) -> typing.BinaryIO:
        return self.file


class MetricsProxy(MetricRecorder):
    def __init__(self) -> None:
        self._recorder: MetricRecorder | None = None

    def set_recorder(self, recorder: MetricRecorder) -> None:
        self._recorder = recorder

    def record_many(self, metric: str, values: dict[str, Value], ts: Timestamp | None = None, **attributes) -> None:
        if self._recorder is not None:
            self._recorder.record_many(metric, values, ts, **attributes)

    def is_initialized(self) -> bool:
        return self._recorder is not None


Metrics = MetricsProxy()


def setup_default_metrics() -> None:
    if Metrics.is_initialized():
        return
    if 'METRICS_LOGFILE' in os.environ:
        f = os.environ['METRICS_LOGFILE']
        if f == '-':
            Metrics.set_recorder(TelegrafBufferMetricsRecorder(sys.stdout.buffer))
        else:
            Metrics.set_recorder(TelegrafTailMetricsRecorder(f))
