# --- FILE: tests/test_worker_metrics.py ---
"""
Celery worker metrics (task 4 of the 18.11 plan): the worker's main process serves /metrics, in multiprocess mode the sum of
the child processes' files; engine time accumulated in a child process is visible in the response. Port 0 - the server is not
started. Celery signals are connected to these functions.
"""

import os

from celery.signals import worker_init, worker_process_shutdown
from prometheus_client import CollectorRegistry, Counter, generate_latest, values

from src.core import observability
from src.worker import celery_app


def test_port_zero_starts_nothing(monkeypatch):
    started = []
    monkeypatch.setattr("prometheus_client.start_http_server", lambda *a, **k: started.append(a))
    assert observability.start_worker_metrics_server(0) is False
    assert started == []


def test_worker_serves_the_sum_of_child_process_files(monkeypatch, tmp_path):
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    served = {}
    monkeypatch.setattr("prometheus_client.start_http_server",
                        lambda port, registry: served.update(port=port, registry=registry))
    # "Child process" writes engine time to a file in the directory, as Counter does in multiprocess mode.
    monkeypatch.setattr(values, "ValueClass", values.MultiProcessValue(lambda: 4242))
    counter = Counter("regence_engine_seconds_probe", "probe", ["kind"], registry=CollectorRegistry())
    counter.labels("analysis").inc(7.5)

    assert observability.start_worker_metrics_server(9101) is True
    body = generate_latest(served["registry"]).decode()
    assert served["port"] == 9101
    assert 'regence_engine_seconds_probe_total{kind="analysis"} 7.5' in body
    assert any(name.endswith("_4242.db") for name in os.listdir(tmp_path))


def test_celery_signals_are_connected():
    assert celery_app._serve_worker_metrics in [ref() for _, ref in worker_init.receivers]
    assert celery_app._forget_worker_process in [ref() for _, ref in worker_process_shutdown.receivers]
