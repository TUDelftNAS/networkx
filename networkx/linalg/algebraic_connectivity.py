# -*- coding: utf-8 -*-
"""
Algebraic connectivity and Fiedler vectors of undirected graphs.
"""

__author__ = """ysitu <ysitu@users.noreply.github.com>"""
# Copyright (C) 2014 ysitu <ysitu@users.noreply.github.com>
# All rights reserved.
# BSD license.

import networkx as nx
from networkx.utils import not_implemented_for
from random import normalvariate

try:
    from numpy import (array, asmatrix, asarray, dot, matrix, ndarray, reshape,
                       zeros)
    from numpy.linalg import norm
    from scipy.linalg import eigh, solve
    from scipy.sparse import csc_matrix
    from scipy.sparse.linalg import eigsh
    __all__ = ['algebraic_connectivity', 'fiedler_vector']
except ImportError:
    __all__ = []


class _PCGSolver(object):
    """Jacobi-preconditioned conjugate gradient method.
    """

    def __init__(self, A, tol):
        self._A = A
        self._M = 1. / A.diagonal()
        self._tol = tol

    def solve(self, b):
        A = self._A
        M = self._M
        tol = self._tol * norm(b, 1)
        # Initialize.
        x = zeros(b.shape)
        r = b.copy()
        z = M * r
        rz = dot(r, z)
        p = z
        # Iterate.
        while True:
            Ap = A * p
            alpha = rz / dot(p, Ap)
            x += alpha * p
            r -= alpha * Ap
            if norm(r, 1) < tol:
                return x
            z = M * r
            beta = dot(r, z)
            beta, rz = beta / rz, beta
            p = z + beta * p


class _CholeskySolver(object):
    """Cholesky factorization.
    """

    def __init__(self, A):
        A = csc_matrix(A, dtype=float)
        chol = self._analyze(A)
        perm = chol.P()
        A[perm[-1], perm[-1]] = float('inf')
        chol.cholesky_inplace(A)
        self._chol = chol

    def solve(self, b):
        return self._chol(b)

    try:
        from scikits.sparse.cholmod import analyze
        _analyze = analyze
        avail = True
    except ImportError:
        avail = False


def _tracemin_fiedler(L, tol, solver=None):
    """Compute the Fiedler vector of L using the TRACEMIN-Fiedler algorithm.
    """
    n = L.shape[0]
    q = 2

    Lnorm = max(asarray(abs(L).sum(axis=0))[0, :])

    def project(X):
        """Make X orthogonal to the nullspace of L.
        """
        X = asarray(X)
        for j in range(q):
            X[:, j] -= sum(X[:, j]) / n

    def gram_schmidt(X):
        """Return an orthonormalized copy of X.
        """
        V = asarray(X.copy())
        for j in range(q):
            for k in range(j):
                V[:, j] -= dot(V[:, k], V[:, j]) * V[:, k]
            V[:, j] /= norm(V[:, j])
        return asmatrix(V)

    if solver is None:
        solver = 'pcg' if not _CholeskySolver.avail else 'chol'
    if solver == 'pcg':
        solver = _PCGSolver(L, tol / 10)
    elif solver == 'chol':
        if not _CholeskySolver.avail:
            raise nx.NetworkXError('Chokesky solver unavailable.')
        solver = _CholeskySolver(L)
    else:
        raise nx.NetworkXError('unknown solver.')

    # Randomly initialize eigenvectors.
    X = asmatrix(reshape([normalvariate(0, 1) for i in range(n * q)], (n, q),
                         order='F'))
    project(X)
    W = asmatrix(ndarray((n, q), order='F'))

    first = True
    while True:
        V = gram_schmidt(X)
        # Compute interation matrix H.
        H = V.transpose() * L * V
        sigma, Y = eigh(H, overwrite_a=True)
        # Test for convergence.
        if not first:
            r = L * X[:, 0] - sigma[0] * X[:, 0]
            if norm(r, 1) < tol * Lnorm:
                break
        else:
            first = False
        # Compute Ritz vectors.
        X = V * Y
        # Solve saddle point problem using the Schur complement.
        for j in range(q):
            asarray(W)[:, j] = solver.solve(asarray(X)[:, j])
        project(W)
        S = X.transpose() * W  # Schur complement
        N = solve(S, X.transpose() * X, overwrite_a=True, overwrite_b=True)
        X = W * N

    return sigma, asarray(X)


@not_implemented_for('directed')
def algebraic_connectivity(G, weight='weight', tol=1e-8, method='tracemin'):
    """Return the algebraic connectivity of a connected undirected graph.

    The algebraic connectivity of a connected undirected graph is the second
    smallest eigenvalue of its Laplacian matrix.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    weight : string or None
        The data key used to determine the weight of each edge. If None, then
        each edge has unit weight. Default value: None.

    tol : float
        Tolerance of eigenvalue computation. Default value: 1e-8.

    method : string
        Method of eigenvalue computation. It should be either 'tracemin'
        (TraceMIN) or 'arnoldi' (Arnoldi iteration). Default value: 'tracemin'.

    Returns
    -------
    aconn : float
        Algebraic connectivity.

    Raises
    ------
    NetworkXNotImplemented :
        If G is directed.

    NetworkXError :
        If G as less than two nodes or is not connected.

    Notes
    -----
    For MultiGraph, the edge weights are summed. Zero-weighted edges are ignored.

    See Also
    --------
    laplacian_matrix
    """
    if len(G) < 2:
        raise nx.NetworkXError('graph has less than two nodes.')
    if not nx.is_connected(G):
        raise nx.NetworkXError('graph is not connected.')

    L = nx.laplacian_matrix(G, weight=weight)
    if any(L.diagonal() == 0):
        raise nx.NetworkXError('graph is not connected.')

    if len(G) == 2:
        return 2. * L[0, 0]

    if method == 'tracemin':
        sigma, X = _tracemin_fiedler(L, tol)
        return sigma[0]
    elif method == 'tracemin_pcg':
        sigma, X = _tracemin_fiedler(L, tol, 'pcg')
        return sigma[0]
    elif method == 'tracemin_chol':
        sigma, X = _tracemin_fiedler(L, tol, 'chol')
        return sigma[0]
    elif method == 'arnoldi':
        L = csc_matrix(L, dtype=float)
        sigma = eigsh(L, 2, which='SM', tol=tol, return_eigenvectors=False)
        return sigma[0]
    else:
        raise nx.NetworkXError(
            "method should be either 'tracemin' or 'arnoldi'.")


@not_implemented_for('directed')
def fiedler_vector(G, weight='weight', tol=1e-8, method='tracemin'):
    """Return the Fiedler vector of a connected undirected graph.

    The Fiedler vector of a connected undirected graph is the eigenvector
    corresponding to the second smallest eigenvalue of the Laplacian matrix of
    of the graph.

    Parameters
    ----------
    G : NetworkX graph
        An undirected graph.

    weight : string or None
        The data key used to determine the weight of each edge. If None, then
        each edge has unit weight. Default value: None.

    tol : float
        Tolerance of relative residual in eigenvalue computation. Default
        value: 1e-8.

    method : string
        Method of eigenvalue computation. It should be either 'tracemin'
        (TraceMIN) or 'arnoldi' (Arnoldi iteration). Default value: 'tracemin'.

    Returns
    -------
    aconn : float
        Algebraic connectivity.

    Raises
    ------
    NetworkXNotImplemented :
        If G is directed.

    NetworkXError :
        If G as less than two nodes or is not connected.

    Notes
    -----
    For MultiGraph, the edge weights are summed. Zero-weighted edges are ignored.

    See Also
    --------
    laplacian_matrix
    """
    if len(G) < 2:
        raise nx.NetworkXError('graph has less than two nodes.')
    if not nx.is_connected(G):
        raise nx.NetworkXError('graph is not connected.')

    L = nx.laplacian_matrix(G, weight=weight)
    if any(L.diagonal() == 0):
        raise nx.NetworkXError('graph is not connected.')

    if len(G) == 2:
        return array([1., -1.])

    if method == 'tracemin':
        sigma, X = _tracemin_fiedler(L, tol)
        return array(X[:, 0])
    elif method == 'tracemin_pcg':
        sigma, X = _tracemin_fiedler(L, tol, 'pcg')
        return array(X[:, 0])
    elif method == 'tracemin_chol':
        sigma, X = _tracemin_fiedler(L, tol, 'chol')
        return array(X[:, 0])
    elif method == 'arnoldi':
        L = csc_matrix(L, dtype=float)
        sigma, X = eigsh(L, 2, which='SM', tol=tol)
        return array(X[:, 1])
    else:
        raise nx.NetworkXError(
            "method should be either 'tracemin' or 'arnoldi'.")


# fixture for nose tests
def setup_module(module):
    from nose import SkipTest
    try:
        import numpy
        import scipy.sparse
    except ImportError:
        raise SkipTest('SciPy not available.')
