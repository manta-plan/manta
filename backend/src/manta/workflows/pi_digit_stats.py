import sys
from collections import Counter
from math import isqrt

from prefect import flow, task

_C = 640320
_C3_OVER_24 = _C**3 // 24


def _binary_split(a: int, b: int) -> tuple[int, int, int]:
    if b - a == 1:
        if a == 0:
            p_ab = q_ab = 1
        else:
            p_ab = (6 * a - 5) * (2 * a - 1) * (6 * a - 1)
            q_ab = a**3 * _C3_OVER_24
        t_ab = p_ab * (13591409 + 545140134 * a)
        if a % 2 == 1:
            t_ab = -t_ab
        return p_ab, q_ab, t_ab

    m = (a + b) // 2
    p_am, q_am, t_am = _binary_split(a, m)
    p_mb, q_mb, t_mb = _binary_split(m, b)
    return p_am * p_mb, q_am * q_mb, q_mb * t_am + p_am * t_mb


@task
def compute_pi_digits(num_digits: int) -> str:
    # Chudnovsky algorithm with binary splitting, using exact integer
    # arithmetic throughout (no decimal/float rounding).
    num_terms = int(num_digits / 14.1816474627254776555) + 1
    _, q, t = _binary_split(0, num_terms)
    scale = 10**num_digits
    sqrt_10005 = isqrt(10005 * scale**2)
    pi_scaled = (q * 426880 * sqrt_10005) // t
    sys.set_int_max_str_digits(max(num_digits + 10, 640))
    return str(pi_scaled)[:num_digits]


@task
def digit_frequency(digits: str) -> dict[str, int]:
    return dict(Counter(digits))


@flow(name="pi-digit-stats", log_prints=True)
def pi_digit_stats_flow(num_digits: int = 100_000) -> None:
    digits = compute_pi_digits(num_digits)
    print(digit_frequency(digits))


if __name__ == "__main__":
    pi_digit_stats_flow.serve(name="pi-digit-stats")
