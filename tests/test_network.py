"""All workers share a request cap, including failed requests and robots."""
import concurrent.futures
import tempfile
import time
import unittest
from unittest.mock import patch
from traceatlas import network, core, registry
from tests.test_traceatlas import ORG, fixture

class RequestTests(unittest.TestCase):
    def tearDown(self):network._COOLDOWNS.clear()
    def test_parallel_workers_cannot_exceed_limit(self):
        budget=network.RequestBudget(7,time.monotonic()+10)
        def task(i):
            with network.request_scope(budget,i):
                try:network.take_request('https://example.com/');return True
                except network.BudgetError:return False
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            self.assertEqual(sum(pool.map(task,range(100))),7)
        self.assertEqual(budget.used,7)
    def test_429_honors_retry_after_without_spending_a_request(self):
        network.rate_limited('https://example.com/', '120')
        budget=network.RequestBudget(5,time.monotonic()+1)
        with network.request_scope(budget,0),self.assertRaisesRegex(network.BudgetError,'rate_limited'):
            network.take_request('https://example.com/other')
        self.assertEqual(budget.used,0)
    def test_expired_deadline_and_zero_request_budget(self):
        for limit,deadline in [(1,time.monotonic()-1),(0,time.monotonic()+5)]:
            with network.request_scope(network.RequestBudget(limit,deadline),0),self.assertRaises(network.BudgetError):network.take_request('https://example.com/')
    def test_batch_includes_runtime_and_actual_request_count(self):
        def fetch(number,timeout):network.take_request(registry.BASE+number);return fixture()
        with tempfile.TemporaryDirectory() as folder,patch.object(registry,'fetch',side_effect=fetch):
            report=core.run_batch([ORG]*3,folder,max_requests=1)
            self.assertEqual(report['requests'],1)
            self.assertEqual(report['states']['available'],1)
            self.assertEqual(report['states']['failed'],2)
    def test_cap_cannot_exceed_official_allowance(self):
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(ValueError):core.run_batch([ORG],folder,max_requests=21)

    def test_429_stops_other_sessions_and_counts_robots(self):
        from traceatlas.web import SiteSession,AccessError,_HOSTS
        from unittest.mock import MagicMock
        _HOSTS.clear()
        transport=MagicMock(side_effect=[(404,'text/plain',b''),(429,'text/html',b'')])
        budget=network.RequestBudget(20,time.monotonic()+5)
        with network.request_scope(budget,0),patch('traceatlas.web.time.sleep'):
            session=SiteSession('https://example.com/',budget.deadline,transport=transport)
            with self.assertRaisesRegex(AccessError,'source_blocked'):session.page('https://example.com/')
            with self.assertRaisesRegex(network.BudgetError,'rate_limited'):SiteSession('https://example.com/',budget.deadline,transport=transport)
        self.assertEqual(transport.call_count,2);self.assertEqual(budget.used,2)
