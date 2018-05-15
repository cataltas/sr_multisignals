"""Tools for creating interpolation-based dual certificates."""

from trig_poly import TrigPoly, MultiTrigPoly

import mpmath
import numpy as np
from scipy import linalg as sp_linalg


def _interpolator_norm_quadratic_form(kernel, support):
    """Quadratic form calculating L2 norm of interpolator from coefficients."""
    n = support.shape[0]

    kernel_1 = kernel.derivative()

    kernel_inners = kernel.inners_of_shifts(support)
    kernel_1_inners = kernel_1.inners_of_shifts(support)
    cross_inners = kernel.inners_of_shifts_and_derivative_shifts(support)

    # Build objective quadratic form corresponding to interpolator L2 norm:
    S = np.zeros((4*n, 4*n)).astype(np.complex128)
    S[:n, :n] = kernel_inners
    S[n:2*n, n:2*n] = kernel_1_inners
    S[n:2*n, :n] = cross_inners.T
    S[:n, n:2*n] = cross_inners
    S[2*n:3*n, 2*n:3*n] = kernel_inners
    S[3*n:, 3*n:] = kernel_1_inners
    S[3*n:, 2*n:3*n] = cross_inners.T
    S[2*n:3*n, 3*n:] = cross_inners
    # TODO: Make sure it's ok to cast to real here
    S = (S + S.T).real * 0.5
    return S


def _optimize_quadratic_form(S, A, y, multiplier=1.0):
    """Maximize x^T S x subject to Ax = y.

    The multiplier is a factor multiplied into S in formulating the linear
    problem, which can help mitigate ill-conditioned systems (resulting from
    magnitude discrepancies between S and A).
    """
    m = A.shape[0]
    n = S.shape[0]
    # This expression for the solution is derived with Lagrange multipliers,
    # the multiplier vector of the constraint Ax = y being in the last m
    # coordinates of the result, which we discard.
    return np.linalg.solve(
        np.bmat([[multiplier * S, A.T], [A, np.zeros((m, m))]]),
        np.hstack([np.zeros(n), y]))[:n]


#
# Interpolation functions
#


def interpolate(support, sign_pattern, kernel):
    assert support.shape == sign_pattern.shape
    assert np.all(np.absolute(np.absolute(sign_pattern) - 1.0) < 1e-10)

    n = support.shape[0]

    # time_deltas[i, j] = t_i - t_j
    time_deltas = np.outer(support, np.ones(n)) - np.outer(np.ones(n), support)
    kernel_values = kernel(time_deltas)

    coeffs = np.linalg.solve(kernel_values, sign_pattern)

    return kernel.sum_shifts(-support, coeffs)


def interpolate_with_derivative(support, sign_pattern, kernel):
    assert support.shape == sign_pattern.shape
    assert np.all(np.absolute(np.absolute(sign_pattern) - 1.0) < 1e-10)

    n = support.shape[0]

    # time_deltas[i, j] = t_i - t_j
    time_deltas = np.outer(support, np.ones(n)) - np.outer(np.ones(n), support)

    # NOTE: This is assuming that the kernel is real-valued.

    kernel_1 = kernel.derivative()
    kernel_2 = kernel_1.derivative()

    kernel_values = kernel(time_deltas)
    kernel_1_values = kernel_1(time_deltas)
    kernel_2_values = kernel_2(time_deltas)

    sign_pattern_real = np.real(sign_pattern)
    sign_pattern_imag = np.imag(sign_pattern)

    zeros = np.zeros((n, n))

    # Build linear constraint objects
    A = np.bmat([
        [kernel_values, kernel_1_values, zeros, zeros],
        [zeros, zeros, kernel_values, kernel_1_values],
        [sign_pattern_real.reshape((n, 1)) * kernel_1_values,
         sign_pattern_real.reshape((n, 1)) * kernel_2_values,
         sign_pattern_imag.reshape((n, 1)) * kernel_1_values,
         sign_pattern_imag.reshape((n, 1)) * kernel_2_values]]).astype(
             np.float64)
    y = np.hstack(
        [sign_pattern_real,
         sign_pattern_imag,
         np.zeros(sign_pattern.shape[0])])

    # Build objective quadratic form corresponding to interpolator L2 norm:
    S = _interpolator_norm_quadratic_form(kernel, support)

    coeffs = _optimize_quadratic_form(S, A, y)

    return (
        kernel.sum_shifts(-support, coeffs[:n]) +
        kernel_1.sum_shifts(-support, coeffs[n:2*n]) +
        kernel.sum_shifts(-support, coeffs[2*n:3*n] * 1j) +
        kernel_1.sum_shifts(-support, coeffs[3*n:] * 1j))


def interpolate_multidim(support, sign_pattern, kernel):
    assert support.shape[0] == sign_pattern.shape[0]
    assert np.all(
        np.absolute(
            np.sum(np.absolute(sign_pattern) ** 2, axis=1) - 1.0) < 1e-10)

    n = support.shape[0]
    m = sign_pattern.shape[1]

    time_deltas = np.outer(support, np.ones(n)) - np.outer(np.ones(n), support)
    kernel_values = kernel(time_deltas)

    coeffss = []
    for k in range(m):
        single_sign_pattern = sign_pattern[:, k]
        coeffss.append(
            np.linalg.solve(kernel_values, single_sign_pattern))

    return MultiTrigPoly([
        kernel.sum_shifts(-support, coeffs)
        for coeffs in coeffss])


def interpolate_multidim_with_derivative(
        support, sign_pattern, kernel):
    assert support.shape[0] == sign_pattern.shape[0]
    assert np.all(
        np.absolute(
            np.sum(np.absolute(sign_pattern) ** 2, axis=1) - 1.0) < 1e-10)

    n = support.shape[0]
    m = sign_pattern.shape[1]

    time_deltas = np.outer(support, np.ones(n)) - np.outer(np.ones(n), support)

    kernel_1 = kernel.derivative()
    kernel_2 = kernel_1.derivative()

    kernel_values = kernel(time_deltas)
    kernel_1_values = kernel_1(time_deltas)
    kernel_2_values = kernel_2(time_deltas)

    sign_pattern_real = np.real(sign_pattern)
    sign_pattern_imag = np.imag(sign_pattern)

    #
    # Build linear constraint data
    #

    zeros = np.zeros((n, n))
    problem_mx_rows = []
    problem_obj_cols = []
    for k in range(m):
        # Row of real part constraint
        row1 = []
        for _ in range(4 * k):
            row1.append(zeros)
        row1.append(kernel_values)
        row1.append(kernel_1_values)
        row1.append(zeros)
        row1.append(zeros)
        for _ in range(4 * (m - 1 - k)):
            row1.append(zeros)
        problem_mx_rows.append(row1)

        # Row of imaginary part constraint
        row2 = []
        for _ in range(4 * k):
            row2.append(zeros)
        row2.append(zeros)
        row2.append(zeros)
        row2.append(kernel_values)
        row2.append(kernel_1_values)
        for _ in range(4 * (m - 1 - k)):
            row2.append(zeros)
        problem_mx_rows.append(row2)

    gradient_row = []
    for k in range(m):
        # Row of gradient constraint
        single_sign_pattern_real = sign_pattern_real[:, k]
        single_sign_pattern_imag = sign_pattern_imag[:, k]
        gradient_row.append(
            single_sign_pattern_real.reshape((n, 1)) * kernel_1_values)
        gradient_row.append(
            single_sign_pattern_real.reshape((n, 1)) * kernel_2_values)
        gradient_row.append(
            single_sign_pattern_imag.reshape((n, 1)) * kernel_1_values)
        gradient_row.append(
            single_sign_pattern_imag.reshape((n, 1)) * kernel_2_values)

        # Objective
        problem_obj_cols.append(single_sign_pattern_real)
        problem_obj_cols.append(single_sign_pattern_imag)

    problem_mx_rows.append(gradient_row)
    problem_mx = np.bmat(problem_mx_rows)

    problem_obj_cols.append(np.zeros(n))
    problem_obj = np.hstack(problem_obj_cols)

    #
    # Build objective quadratic form
    #

    # S is block-diagonal, with k blocks of size 4n x 4n each of which is the
    # same as the objective quadratic form from the one-sample case.
    S_diag_block = _interpolator_norm_quadratic_form(kernel, support)
    S = np.kron(np.identity(m), S_diag_block)

    # This multiplier value is heuristically chosen.
    multiplier = kernel_1.squared_norm() / kernel.squared_norm() * 1e3
    coeffs = _optimize_quadratic_form(
        S,
        problem_mx,
        problem_obj,
        multiplier=multiplier)

    return MultiTrigPoly([
        (kernel.sum_shifts(-support, coeffs[4*k*n:(4*k+1)*n]) +
         kernel_1.sum_shifts(-support, coeffs[(4*k+1)*n:(4*k+2)*n]) +
         kernel.sum_shifts(-support, coeffs[(4*k+2)*n:(4*k+3)*n] * 1j) +
         kernel_1.sum_shifts(-support, coeffs[(4*k+3)*n:(4*k+4)*n] * 1j))
        for k in range(m)]), coeffs, kernel, kernel_1


def interpolate_multidim_adjacent_samples(
        support, sign_pattern, kernel, random_derivatives = False):
    assert support.shape[0] == sign_pattern.shape[0]
    assert np.all(
        np.absolute(
            np.sum(np.absolute(sign_pattern) ** 2, axis=1) - 1.0) < 1e-10)

    n = support.shape[0]
    m = sign_pattern.shape[1]

    time_deltas = np.outer(support, np.ones(n)) - np.outer(np.ones(n), support)

    kernel_1 = kernel.derivative()
    kernel_2 = kernel_1.derivative()

    kernel_values = kernel(time_deltas)
    kernel_1_values = kernel_1(time_deltas)
    kernel_2_values = kernel_2(time_deltas)

    sign_pattern_real = np.real(sign_pattern)
    sign_pattern_imag = np.imag(sign_pattern)

    #
    # Build linear constraint data
    #

    zeros = np.zeros((n, n))
    problem_mx_rows = []
    problem_obj_cols = []
    
    if not random_derivatives:
        vj_p1_real = np.append(np.asarray([sign_pattern_real[i + 1,:] for i in range(n-1)]), np.zeros((1,m))).reshape((n,m))
        vj_m1_real = np.append(np.zeros((1,m)), np.asarray([sign_pattern_real[i ,:] for i in range(n-1)])).reshape((n,m)) 
        vj_diff_real = vj_p1_real - vj_m1_real
    else:
        #random projection    
        vj_diff_real = np.random.randn(n,m)
    vj_diff_real = vj_diff_real/np.sqrt(np.sum(np.square(vj_diff_real), axis=1)).reshape(n,1)

    vj_coeffs_real = np.diagonal(vj_diff_real.dot(sign_pattern_real.T) )
    
    if not random_derivatives:    
        vj_p1_imag = np.append(np.asarray([sign_pattern_imag[i + 1,:] for i in range(n-1)]), np.zeros((1,m))).reshape((n,m))
        vj_m1_imag = np.append(np.zeros((1,m)), np.asarray([sign_pattern_imag[i ,:] for i in range(n-1)])).reshape((n,m))    
        vj_diff_imag = vj_p1_imag - vj_m1_imag
    else:
        #random projection
        vj_diff_imag = np.random.randn(n,m)
    vj_diff_imag = vj_diff_imag/np.sqrt(np.sum(np.square(vj_diff_imag), axis=1)).reshape(n,1)

    vj_coeffs_imag = np.diagonal(vj_diff_imag.dot(sign_pattern_imag.T) )
    
    
    for k in range(m):
        # Row of real part constraint
        row1 = []
        for _ in range(4 * k):
            row1.append(zeros)
        row1.append(kernel_values)
        row1.append(kernel_1_values)
        row1.append(zeros)
        row1.append(zeros)
        for _ in range(4 * (m - 1 - k)):
            row1.append(zeros)
        problem_mx_rows.append(row1)

        # Row of imaginary part constraint
        row2 = []
        for _ in range(4 * k):
            row2.append(zeros)
        row2.append(zeros)
        row2.append(zeros)
        row2.append(kernel_values)
        row2.append(kernel_1_values)
        for _ in range(4 * (m - 1 - k)):
            row2.append(zeros)
        problem_mx_rows.append(row2)
        
        # Objective
        problem_obj_cols.append(sign_pattern_real[:, k])
        problem_obj_cols.append(sign_pattern_imag[:, k])
        
    for k in range(m):     
        row1 = []
        for _ in range(4 * k):
            row1.append(zeros)
        row1.append(kernel_1_values)
        row1.append(kernel_2_values)
        row1.append(zeros)
        row1.append(zeros)
        for _ in range(4 * (m - 1 - k)):
            row1.append(zeros)
        problem_mx_rows.append(row1)
                
        # Row of imaginary part constraint
        row2 = []
        for _ in range(4 * k):
            row2.append(zeros)
        row2.append(zeros)
        row2.append(zeros)
        row2.append(kernel_1_values)
        row2.append(kernel_2_values)
        for _ in range(4 * (m - 1 - k)):
            row2.append(zeros)
        problem_mx_rows.append(row2)        
        
        # Objective
        # problem_obj_cols.append(1*vj_p1_real[:, k] - 1*vj_m1_real[:, k] - 1*np.multiply(vj_coeffs_real,sign_pattern_real[:, k]) )
        # problem_obj_cols.append(1*vj_p1_imag[:, k] - 1*vj_m1_imag[:, k] - 1*np.multiply(vj_coeffs_imag,sign_pattern_imag[:, k]) )

        problem_obj_cols.append(vj_diff_real[:, k] - np.multiply(vj_coeffs_real,sign_pattern_real[:, k]) )
        problem_obj_cols.append(vj_diff_imag[:, k] - np.multiply(vj_coeffs_imag,sign_pattern_imag[:, k]) )


    problem_mx = np.bmat(problem_mx_rows)
    problem_obj = np.hstack(problem_obj_cols)

    #
    # Solve
    #
    coeffs = np.linalg.solve(problem_mx, problem_obj)
    print(coeffs.ndim)
    s = np.linalg.svd(problem_mx, compute_uv=False)
    print(min(s))
    print(max(s))
    # coeffs = np.dot(np.linalg.inv(problem_mx), problem_obj)
    # print(coeffs.shape)
    # coeffs = coeffs.flatten()
    # print(coeffs.ndim)
    
    #Or L2 min
#     S_diag_block = _interpolator_norm_quadratic_form(kernel, support)
#     S = np.kron(np.identity(m), S_diag_block)

#     # This multiplier value is heuristically chosen.
#     multiplier = kernel_1.squared_norm() / kernel.squared_norm() * 1e3
#     coeffs = _optimize_quadratic_form(
#         S,
#         problem_mx,
#         problem_obj,
#         multiplier=multiplier)
    
    
    return MultiTrigPoly([
        (kernel.sum_shifts(-support, coeffs[4*k*n:(4*k+1)*n]) +
         kernel_1.sum_shifts(-support, coeffs[(4*k+1)*n:(4*k+2)*n]) +
         kernel.sum_shifts(-support, coeffs[(4*k+2)*n:(4*k+3)*n] * 1j) +
         kernel_1.sum_shifts(-support, coeffs[(4*k+3)*n:(4*k+4)*n] * 1j))
        for k in range(m)])


def interpolate_multidim_0Grad(support, sign_pattern, kernel):
    assert support.shape[0] == sign_pattern.shape[0]
    assert np.all(
        np.absolute(
            np.sum(np.absolute(sign_pattern) ** 2, axis=1) - 1.0) < 1e-10)

    n = support.shape[0]
    m = sign_pattern.shape[1]

    kernel1 = kernel.derivative()
    kernel2 = kernel1.derivative()

    time_deltas = np.outer(support, np.ones(n)) - np.outer(np.ones(n), support)
    kernel_values = kernel(time_deltas)
    kernel1_values = kernel1(time_deltas)
    kernel2_values = kernel2(time_deltas)
    problem_mx = np.bmat([
        [kernel_values, kernel1_values],
        [kernel1_values, kernel2_values]])

    coeffss = []
    for k in range(m):
        single_sign_pattern = sign_pattern[:, k]
        problem_obj = np.hstack(
            [single_sign_pattern, np.zeros(single_sign_pattern.shape[0])])
        coeffss.append(np.linalg.solve(problem_mx, problem_obj))

    return MultiTrigPoly([
        (TrigPoly(
            kernel.freqs,
            sum(kernel.coeffs * np.exp(2.0 * np.pi * 1j * kernel.freqs * -t) * c
                for c, t in zip(coeffs[:n], support))) +
         TrigPoly(
             kernel1.freqs,
             sum(kernel1.coeffs * np.exp(2.0 * np.pi * 1j * kernel1.freqs * -t) * c
                 for c, t in zip(coeffs[n:], support))))
        for coeffs in coeffss])

    return MultiTrigPoly([
        sum([kernel.shift(-t) * c for c, t in zip(coeffs[:n], support)],
            TrigPoly.zero()) +
        sum([kernel1.shift(-t) * c for c, t in zip(coeffs[n:], support)],
            TrigPoly.zero())
        for coeffs in coeffss])


_EPSILON = 1e-7

#
# Validation functions
#

def validate(support, sign_pattern, interpolator, grid_pts=1e3):
    max_deviation = float('-inf')
    for i in range(support.shape[0]):
        if len(sign_pattern.shape) == 1:
            sign_pattern_slice = sign_pattern[i]
        else:
            sign_pattern_slice = sign_pattern[i, :]
        max_deviation = max(
            max_deviation,
            np.max(
                np.absolute(
                    interpolator(support[i]).T - sign_pattern_slice)))
    values_achieved = max_deviation <= _EPSILON

    grid = np.linspace(0.0, 1.0, grid_pts)
    grid_values = interpolator(grid)
    if len(grid_values.shape) == 1:
        grid_magnitudes = np.absolute(grid_values)
    else:
        grid_magnitudes = np.linalg.norm(grid_values, axis=0)

    grid_magnitudes = np.ma.array(grid_magnitudes)
    for t in support:
        left_ix = np.searchsorted(grid, t)
        grid_magnitudes[left_ix % grid_magnitudes.shape[0]] = np.ma.masked
        grid_magnitudes[(left_ix + 1) % grid_magnitudes.shape[0]] = (
            np.ma.masked)

    bound_achieved = np.all(grid_magnitudes < 1.0)

    status = values_achieved and bound_achieved

    return {
        'status': status,
        'values_achieved': values_achieved,
        'max_deviation': max_deviation,
        'bound_achieved': bound_achieved}
