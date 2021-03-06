
# Copyright (c) 2015, 2014 Computational Molecular Biology Group, Free University
# Berlin, 14195 Berlin, Germany.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#  * Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation and/or
# other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS ``AS IS''
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

r"""Implement a MSM class that builds a Markov state models from
microstate trajectories automatically computes important properties
and provides them for later access.

.. moduleauthor:: F. Noe <frank DOT noe AT fu-berlin DOT de>

"""

__docformat__ = "restructuredtext en"

import numpy as _np

from pyemma.msm.models.msm import MSM as _MSM
from pyemma.util import types as _types


class HMSM(_MSM):
    r""" Hidden Markov model on discrete states.

    Parameters
    ----------
    hmm : :class:`DiscreteHMM <bhmm.DiscreteHMM>`
        Hidden Markov Model

    """

    def __init__(self, P, pobs, pi=None, dt_model='1 step'):
        """

        Parameters
        ----------
        Pcoarse : ndarray (m,m)
            coarse-grained or hidden transition matrix

        Pobs : ndarray (m,n)
            observation probability matrix from hidden to observable discrete states

        dt_model : str, optional, default='1 step'
            time step of the model

        """
        # construct superclass and check input
        _MSM.__init__(self, P, dt_model=dt_model)
        self.set_model_params(pobs=pobs, pi=pi, dt_model=dt_model)

    def set_model_params(self, P=None, pobs=None, pi=None, reversible=None, dt_model='1 step', neig=None):
        """

        Parameters
        ----------
        P : ndarray(m,m)
            coarse-grained or hidden transition matrix

        pobs : ndarray (m,n)
            observation probability matrix from hidden to observable discrete
            states

        pi : ndarray(m), optional, default=None
            stationary or distribution. Can be optionally given in case if
            it was already computed, e.g. by the estimator.

        dt_model : str, optional, default='1 step'
            time step of the model

        neig : int or None
            The number of eigenvalues / eigenvectors to be kept. If set to
            None, all eigenvalues will be used.

        """
        _MSM.set_model_params(self, P=P, pi=pi, reversible=reversible, dt_model=dt_model, neig=neig)
        # set P and derived quantities if available
        if pobs is not None:
            # check and save copy of output probability
            assert _types.is_float_matrix(pobs), 'pobs is not a matrix of floating numbers'
            assert _np.allclose(pobs.sum(axis=1), 1), 'pobs is not a stochastic matrix'
            self._nstates_obs = pobs.shape[1]
            self.update_model_params(pobs=pobs)

    @property
    def observation_probabilities(self):
        r""" returns the output probability matrix

        Returns
        -------
        Pout : ndarray (m,n)
            output probability matrix from hidden to observable discrete states

        """
        return self.pobs

    @property
    def nstates_obs(self):
        return self.observation_probabilities.shape[1]

    @property
    def lifetimes(self):
        r""" Lifetimes of states of the hidden transition matrix

        Returns
        -------
        l : ndarray(nstates)
            state lifetimes in units of the input trajectory time step,
            defined by :math:`-tau / ln | p_{ii} |, i = 1,...,nstates`, where
            :math:`p_{ii}` are the diagonal entries of the hidden transition matrix.

        """
        return -self._timeunit_model.dt / _np.log(_np.diag(self.transition_matrix))

    def transition_matrix_obs(self, k=1):
        """ Computes the transition matrix between observed states

        Transition matrices for longer lag times than the one used to
        parametrize this HMSM can be obtained by setting the k option.
        Note that a HMSM is not Markovian, thus we cannot compute transition
        matrices at longer lag times using the Chapman-Kolmogorow equality.
        I.e.:

        .. math::
            P (k \tau) \neq P^k (\tau)

        This function computes the correct transition matrix using the
        metastable (coarse) transition matrix :math:`P_c` as:

        .. math::
            P (k \tau) = {\Pi}^-1 \chi^{\top} ({\Pi}_c) P_c^k (\tau) \chi

        where :math:`\chi` is the output probability matrix, :math:`\Pi_c` is
        a diagonal matrix with the metastable-state (coarse) stationary
        distribution and :math:`\Pi` is a diagonal matrix with the
        observable-state stationary distribution.

        Parameters
        ----------
        k : int, optional, default=1
            Multiple of the lag time for which the
            By default (k=1), the transition matrix at the lag time used to
            construct this HMSM will be returned. If a higher power is given,

        """
        Pi_c = _np.diag(self.stationary_distribution)
        P_c = self.transition_matrix
        P_c_k = _np.linalg.matrix_power(P_c, k)  # take a power if needed
        B = self.observation_probabilities
        C = _np.dot(_np.dot(B.T, Pi_c), _np.dot(P_c_k, B))
        P = C / C.sum(axis=1)[:, None]  # row normalization
        return P

    @property
    def stationary_distribution_obs(self):
        return _np.dot(self.stationary_distribution, self.observation_probabilities)

    @property
    def eigenvectors_left_obs(self):
        return _np.dot(self.eigenvectors_left(), self.observation_probabilities)

    @property
    def eigenvectors_right_obs(self):
        return _np.dot(self.metastable_memberships, self.eigenvectors_right())

    def propagate(self, p0, k):
        """ Propagates the initial distribution p0 k times

        Computes the product

        .. math:
            p_k = p_0^T P^k

        If the lag time of transition matrix :math:`P` is :math:`\tau`, this
        will provide the probability distribution at time :math:`k \tau`.

        Parameters
        ----------
        p0 : ndarray(n)
            Initial distribution. Vector of size of the active set.

        k : int
            Number of time steps

        Returns
        ----------
        pk : ndarray(n)
            Distribution after k steps. Vector of size of the active set.

        """
        p0 = _types.ensure_ndarray(p0, ndim=1, kind='numeric')
        assert _types.is_int(k) and k>=0, 'k must be a non-negative integer'
        if k == 0:  # simply return p0 normalized
            return p0 / p0.sum()

        micro = False
        # are we on microstates space?
        if len(p0) == self.nstates_obs:
            micro = True
            # project to hidden and compute
            p0 = _np.dot(self.observation_probabilities, p0)

        self._ensure_eigendecomposition(self.nstates)
        from pyemma.util.linalg import mdot
        pk = mdot(p0.T, self.eigenvectors_right(), _np.diag(_np.power(self.eigenvalues(), k)), self.eigenvectors_left())

        if micro:
            pk = _np.dot(pk, self.observation_probabilities)  # convert back to microstate space

        # normalize to 1.0 and return
        return pk / pk.sum()

    # ================================================================================================================
    # Experimental properties: Here we allow to use either coarse-grained or microstate observables
    # ================================================================================================================

    def expectation(self, a):
        a = _types.ensure_float_vector(a, require_order=True)
        # are we on microstates space?
        if len(a) == self.nstates_obs:
            # project to hidden and compute
            a = _np.dot(self.observation_probabilities, a)
        # now we are on macrostate space, or something is wrong
        if len(a) == self.nstates:
            return _MSM.expectation(self, a)
        else:
            raise ValueError('observable vector a has size ' + len(a) + ' which is incompatible with both hidden (' +
                             self.nstates + ') and observed states (' + self.nstates_obs + ')')

    def correlation(self, a, b=None, maxtime=None, k=None, ncv=None):
        # basic checks for a and b
        a = _types.ensure_ndarray(a, ndim=1, kind='numeric')
        b = _types.ensure_ndarray_or_None(b, ndim=1, kind='numeric', size=len(a))
        # are we on microstates space?
        if len(a) == self.nstates_obs:
            a = _np.dot(self.observation_probabilities, a)
            if b is not None:
                b = _np.dot(self.observation_probabilities, b)
        # now we are on macrostate space, or something is wrong
        if len(a) == self.nstates:
            return _MSM.correlation(self, a, b=b, maxtime=maxtime)
        else:
            raise ValueError('observable vectors have size ' + len(a) + ' which is incompatible with both hidden (' +
                             self.nstates + ') and observed states (' + self.nstates_obs + ')')

    def fingerprint_correlation(self, a, b=None, k=None, ncv=None):
        # basic checks for a and b
        a = _types.ensure_ndarray(a, ndim=1, kind='numeric')
        b = _types.ensure_ndarray_or_None(b, ndim=1, kind='numeric', size=len(a))
        # are we on microstates space?
        if len(a) == self.nstates_obs:
            a = _np.dot(self.observation_probabilities, a)
            if b is not None:
                b = _np.dot(self.observation_probabilities, b)
        # now we are on macrostate space, or something is wrong
        if len(a) == self.nstates:
            return _MSM.fingerprint_correlation(self, a, b=b)
        else:
            raise ValueError('observable vectors have size ' + len(a) + ' which is incompatible with both hidden (' +
                             self.nstates + ') and observed states (' + self.nstates_obs + ')')

    def relaxation(self, p0, a, maxtime=None, k=None, ncv=None):
        # basic checks for a and b
        p0 = _types.ensure_ndarray(p0, ndim=1, kind='numeric')
        a = _types.ensure_ndarray(a, ndim=1, kind='numeric', size=len(p0))
        # are we on microstates space?
        if len(a) == self.nstates_obs:
            p0 = _np.dot(self.observation_probabilities, p0)
            a = _np.dot(self.observation_probabilities, a)
        # now we are on macrostate space, or something is wrong
        if len(a) == self.nstates:
            return _MSM.relaxation(self, p0, a, maxtime=maxtime)
        else:
            raise ValueError('observable vectors have size ' + len(a) + ' which is incompatible with both hidden (' +
                             self.nstates + ') and observed states (' + self.nstates_obs + ')')

    def fingerprint_relaxation(self, p0, a, k=None, ncv=None):
        # basic checks for a and b
        p0 = _types.ensure_ndarray(p0, ndim=1, kind='numeric')
        a = _types.ensure_ndarray(a, ndim=1, kind='numeric', size=len(p0))
        # are we on microstates space?
        if len(a) == self.nstates_obs:
            p0 = _np.dot(self.observation_probabilities, p0)
            a = _np.dot(self.observation_probabilities, a)
        # now we are on macrostate space, or something is wrong
        if len(a) == self.nstates:
            return _MSM.fingerprint_relaxation(self, p0, a)
        else:
            raise ValueError('observable vectors have size ' + len(a) + ' which is incompatible with both hidden (' +
                             self.nstates + ') and observed states (' + self.nstates_obs + ')')

    def pcca(self, m):
        raise NotImplementedError('PCCA is not meaningful for Hidden Markov models. ' +
                                  'If you really want to do this, initialize an MSM with the HMSM transition matrix.')

    # ================================================================================================================
    # Metastable state stuff is overwritten, because we now have the HMM output probability matrix
    # ================================================================================================================

    @property
    def metastable_memberships(self):
        """ Computes the memberships of observable states to metastable sets by
            Bayesian inversion as described in [1]_.

        Returns
        -------
        M : ndarray((n,m))
            A matrix containing the probability or membership of each
            observable state to be assigned to each metastable or hidden state.
            The row sums of M are 1.

        References
        ----------
        .. [1] F. Noe, H. Wu, J.-H. Prinz and N. Plattner: Projected and hidden
            Markov models for calculating kinetics and metastable states of
            complex molecules. J. Chem. Phys. 139, 184114 (2013)

        """
        A = _np.dot(_np.diag(self.stationary_distribution), self.observation_probabilities)
        M = _np.dot(A, _np.diag(1.0/self.stationary_distribution_obs)).T
        # renormalize
        M /= M.sum(axis=1)[:, None]
        return M

    @property
    def metastable_distributions(self):
        """ Returns the output probability distributions. Identical to
            :meth:`observation_probability`

        Returns
        -------
        Pout : ndarray (m,n)
            output probability matrix from hidden to observable discrete states

        See also
        --------
        observation_probability

        """
        return self.observation_probabilities

    @property
    def metastable_sets(self):
        """ Computes the metastable sets of observable states within each
            metastable set

        This is only recommended for visualization purposes. You *cannot*
        compute any actual quantity of the coarse-grained kinetics without
        employing the fuzzy memberships!

        Returns
        -------
        A list of length equal to metastable states. Each element is an array
        with observable state indexes contained in it

        """
        res = []
        assignment = self.metastable_assignments
        for i in range(self.nstates):
            res.append(_np.where(assignment == i)[0])
        return res

    @property
    def metastable_assignments(self):
        """ Computes the assignment to metastable sets for observable states

        This is only recommended for visualization purposes. You *cannot*
        compute any actual quantity of the coarse-grained kinetics without
        employing the fuzzy memberships!

        Returns
        -------
        For each observable state, the metastable state it is located in.

        """
        return _np.argmax(self.observation_probabilities, axis=0)
