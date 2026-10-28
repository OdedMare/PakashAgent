"""Concurrent solves share the machine instead of oversubscribing it."""

import threading
import time

from app.bl.solver.cpu_budget import CpuBudget


def test_a_solve_asking_for_more_than_the_machine_gets_all_of_it():
    with CpuBudget(4).threads(8) as granted:
        assert granted == 4


def test_a_second_solve_waits_until_the_first_returns_its_threads():
    budget = CpuBudget(8)
    running, peak, lock = [0], [0], threading.Lock()

    def solve():
        with budget.threads(8):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.05)
            with lock:
                running[0] -= 1

    threads = [threading.Thread(target=solve) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert peak[0] == 1


def test_smaller_solves_run_side_by_side():
    budget = CpuBudget(8)
    acquired = threading.Event()

    def other_solve():
        with budget.threads(4):
            acquired.set()

    with budget.threads(4):
        threading.Thread(target=other_solve).start()
        assert acquired.wait(1)
