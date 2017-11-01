import numbers
import numpy as np


class TrigPoly(object):

    def __init__(self, freqs, coeffs):
        assert len(freqs) == len(coeffs)
        self.freqs = np.array(freqs)
        self.coeffs = np.array(coeffs)
        self.coeff_dict = {f: c for f, c in zip(freqs, coeffs)}

    @classmethod
    def dirichlet(cls, f):
        freqs = range(-f, f + 1)
        coeffs = [1.0 / (2.0 * f + 1.0) for _ in range(len(freqs))]
        return cls(freqs, coeffs)

    @classmethod
    def zero(cls):
        return cls([0], [0.0])

    @classmethod
    def one(cls):
        return cls([0], [1.0])

    def eval(self, t):
        repeated_ts = np.repeat(
            t.reshape([1] + list(t.shape)), len(self.freqs), axis=0)
        reshaped_freqs = (
            self.freqs.reshape([len(self.freqs)] + [1] * len(t.shape)))
        reshaped_coeffs = (
            self.coeffs.reshape([len(self.coeffs)] + [1] * len(t.shape)))
        return np.sum(
            reshaped_coeffs *
            np.exp(2.0 * np.pi * 1j * repeated_ts * reshaped_freqs),
            axis=0)

    def shift(self, t):
        """Returns the trig poly time-shifted by +t."""
        new_coeffs = self.coeffs * np.exp(2.0 * np.pi * 1j * self.freqs * t)
        return TrigPoly(self.freqs, new_coeffs)

    def derivative(self):
        return TrigPoly(
            self.freqs, self.coeffs * 2.0 * np.pi * 1j * self.freqs)

    def __call__(self, t):
        return self.eval(t)

    def __add__(self, other):
        all_freqs = sorted(set(self.freqs) | set(other.freqs))
        all_coeffs = [
            self.coeff_dict.get(f, 0.0) + other.coeff_dict.get(f, 0.0)
            for f in all_freqs]
        return TrigPoly(all_freqs, all_coeffs)

    def __mul__(self, other):
        if isinstance(other, numbers.Number):
            new_coeffs = [c * other for c in self.coeffs]
            return TrigPoly(self.freqs, new_coeffs)
        elif isinstance(other, TrigPoly):
            min_freq = min(min(self.freqs), min(other.freqs))
            max_freq = max(max(self.freqs), max(other.freqs))
            all_freqs = range(min_freq, max_freq + 1)

            all_self_coeffs = np.zeros(len(all_freqs))
            for f, c in zip(self.freqs, self.coeffs):
                all_self_coeffs[f - min_freq] = c

            all_other_coeffs = np.zeros(len(all_freqs))
            for f, c in zip(other.freqs, other.coeffs):
                all_other_coeffs[f - min_freq] = c

            new_freqs = range(2 * min_freq, 2 * max_freq + 1)
            new_coeffs = np.convolve(all_self_coeffs, all_other_coeffs)

            return TrigPoly(new_freqs, new_coeffs)
        else:
            assert False