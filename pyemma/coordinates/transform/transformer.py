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
from pyemma.util.log import getLogger
from pyemma.util.progressbar import ProgressBar
from pyemma.util.progressbar.gui import show_progressbar

from itertools import count
import numpy as np
from math import ceil

from abc import ABCMeta, abstractmethod
from pyemma.util.exceptions import NotConvergedWarning

__all__ = ['Transformer']
__author__ = 'noe, marscher'


class SkipPassException(Exception):
    """ raise this to skip a pass during parametrization """
    def __init__(self, next_pass_lagtime=0):
        self.next_pass_lagtime = next_pass_lagtime


class TransformerIterator(object):
    def __init__(self, transformer, stride=1, lag=0):
        # reset transformer iteration
        transformer._reset(stride)
        self._stride = stride
        self._lag = lag
        self._transformer = transformer

    def __iter__(self):
        return self

    def next(self):
        if self._transformer._itraj >= self._transformer.number_of_trajectories():
            raise StopIteration

        last_itraj = self._transformer._itraj
        if self._lag == 0:
            X = self._transformer._next_chunk(lag=self._lag, stride=self._stride)
            return (last_itraj, X)
        else:
            X, Y = self._transformer._next_chunk(lag=self._lag, stride=self._stride)
            return (last_itraj, X, Y)


class Transformer(object):

    r""" Basis class for pipeline objects

    Parameters
    ----------
    chunksize : int (optional)
        the chunksize used to batch process underlying data

    """
    __metaclass__ = ABCMeta
    # count instances
    _ids = count(0)

    def __init__(self, chunksize=100):
        self.chunksize = chunksize
        self._in_memory = False
        self._data_producer = None
        self._parametrized = False
        self._param_with_stride = 1
        # allow children of this class to implement their own progressbar handling
        self._custom_param_progress_handling = False

        self.__create_logger()

    @property
    def data_producer(self):
        r"""where the transformer obtains its data."""
        return self._data_producer

    @data_producer.setter
    def data_producer(self, dp):
        if dp is not self._data_producer:
            self._logger.debug("reset (previous) parametrization state, since"
                               " data producer has been changed.")
            self._parametrized = False
        self._data_producer = dp

    @property
    def chunksize(self):
        """chunksize defines how much data is being processed at once."""
        return self._chunksize

    @chunksize.setter
    def chunksize(self, size):
        if not size >= 0:
            raise ValueError("chunksize has to be positive")
        self._chunksize = int(size)

    def _n_chunks(self, stride=1):
        """ rough estimate of how many chunks will be processed """
        if self._chunksize != 0:
            chunks = sum([ceil(l / float(self._chunksize))
                          for l in self.trajectory_lengths(stride)])
        else:
            chunks = 1
        return chunks

    def _close(self):
        if self.data_producer is not self:
            self.data_producer._close()

    @property
    def in_memory(self):
        r"""are results stored in memory?"""
        return self._in_memory

    @in_memory.setter
    def in_memory(self, op_in_mem):
        r"""
        If set to True, the output will be stored in memory.
        """
        old_state = self._in_memory
        if not old_state and op_in_mem:
            self._in_memory = op_in_mem
            self._Y = []
            self._map_to_memory()
        elif not op_in_mem and old_state:
            self._clear_in_memory()
            self._in_memory = op_in_mem

    def _clear_in_memory(self):
        if __debug__:
            self._logger.debug("clear memory")
        assert self.in_memory, "tried to delete in memory results which are not set"
        self._Y = None

    @abstractmethod
    def dimension(self):
        r""" Number of dimensions that should be used for the output of the transformer. """
        pass

    def __create_logger(self):
        # note this is private, since it should only be called (once) from this class.
        count = self._ids.next()
        i = self.__module__.rfind(".")
        j = self.__module__.find(".") + 1
        package = self.__module__[j:i]
        name = "%s.%s[%i]" % (package, self.__class__.__name__, count)
        self._name = name
        self._logger = getLogger(name)

    def number_of_trajectories(self):
        r"""
        Returns the number of trajectories.

        Returns
        -------
            int : number of trajectories
        """
        return self.data_producer.number_of_trajectories()

    def trajectory_length(self, itraj, stride=1):
        r"""
        Returns the length of trajectory of the requested index.

        Parameters
        ----------
        itraj : int
            trajectory index
        stride : int
            return value is the number of frames in the trajectory when
            running through it with a step size of `stride`.

        Returns
        -------
        int : length of trajectory
        """
        return self.data_producer.trajectory_length(itraj, stride=stride)

    def trajectory_lengths(self, stride=1):
        r"""
        Returns the length of each trajectory.

        Parameters
        ----------
        stride : int
            return value is the number of frames of the trajectories when
            running through them with a step size of `stride`.

        Returns
        -------
        array(dtype=int) : containing length of each trajectory
        """
        return self.data_producer.trajectory_lengths(stride=stride)

    def n_frames_total(self, stride=1):
        r"""
        Returns total number of frames.

        Parameters
        ----------
        stride : int
            return value is the number of frames in trajectories when
            running through them with a step size of `stride`.

        Returns
        -------
        int : n_frames_total
        """
        return self.data_producer.n_frames_total(stride=stride)

    @abstractmethod
    def describe(self):
        r""" Get a descriptive string representation of this class."""
        pass

    def output_type(self):
        r""" By default transformers return single precision floats. """
        return np.float32

    def parametrize(self, stride=1):
        r""" Parametrize this Transformer
        """
        # check if ready
        if self.data_producer is None:
            raise RuntimeError('Called parametrize while data producer is not'
                               ' yet set. Ensure "data_producer" attribute is set!')

        # if stride is not equal to one and does not match to a previous call
        # retrigger parametrization (but not for readers).
        if stride != self._param_with_stride and not self._data_producer is self:
            self._parametrized = False

        self._param_with_stride = stride

        if self._parametrized:
            return

        # init
        return_value = self._param_init()
        if return_value is not None:
            lag = return_value
        else:
            lag = 0
        # feed data, until finished
        add_data_finished = False
        ipass = 0

        if not self._custom_param_progress_handling:
            # NOTE: this assumes this class implements a 1-pass algo
            progress = ProgressBar(self._n_chunks(stride),
                                   description="parameterizing "
                                   + self.__class__.__name__)
        # parametrize
        try:
            while not add_data_finished:
                first_chunk = True
                self.data_producer._reset(stride=stride)
                # iterate over trajectories
                last_chunk = False
                itraj = 0
                while not last_chunk:
                    last_chunk_in_traj = False
                    t = 0
                    while not last_chunk_in_traj:
                        # iterate over times within trajectory
                        if lag == 0:
                            X = self.data_producer._next_chunk(stride=stride)
                            Y = None
                        else:
                            X, Y = self.data_producer._next_chunk(lag=lag, stride=stride)
                        L = np.shape(X)[0]
                        # last chunk in traj?
                        last_chunk_in_traj = (
                            t + L >= self.trajectory_length(itraj, stride=stride))
                        # last chunk?
                        last_chunk = (
                            last_chunk_in_traj and itraj >= self.number_of_trajectories() - 1)
                        # pass chunks to algorithm and respect its return values
                        # and possible SkipPassException
                        try:
                            return_value = self._param_add_data(
                                X, itraj, t, first_chunk, last_chunk_in_traj,
                                last_chunk, ipass, Y=Y, stride=stride)
                        except SkipPassException as spe:
                            self._logger.debug("got skip pass exception."
                                               "Skipping pass %i" % ipass)
                            # break the inner loops
                            last_chunk_in_traj = True
                            last_chunk = True
                            # set lag time for next pass
                            lag = spe.next_pass_lagtime

                        if not self._custom_param_progress_handling:
                            progress.numerator += 1
                            show_progressbar(progress)

                        if isinstance(return_value, tuple):
                            add_data_finished, lag = return_value
                        else:
                            add_data_finished = return_value

                        first_chunk = False
                        # increment time
                        t += L

                    # increment trajectory
                    itraj += 1
                ipass += 1
        except NotConvergedWarning:
            self._logger.info("presumely finished parameterization.")
            self._close()

        # finish parametrization
        if ((not self._custom_param_progress_handling)
                and progress.numerator < progress.denominator):
            progress.numerator = progress.denominator
            show_progressbar(progress)

        self._param_finish()
        self._parametrized = True
        # memory mode? Then map all results. Avoid recursion here, if parametrization
        # is triggered from get_output
        if self.in_memory and not self._mapping_to_mem_active:
            self._map_to_memory()

    def map(self, X):
        r"""Maps the input data through the transformer to correspondingly shaped output data array/list.

        Parameters
        ----------
        X : ndarray(T, n) or list of ndarray(T_i, n)
            The input data, where T is the number of time steps and n is the number of dimensions.
            If a list is provided, the number of time steps is allowed to vary, but the number of dimensions are
            required to be to be consistent.
            required to be to be consistent.

        Returns
        -------
        Y : ndarray(T, d) or list of ndarray(T_i, d)
            The mapped data, where T is the number of time steps of the input data and d is the output dimension
            of this transformer. If called with a list of trajectories, Y will also be a corresponding list of
            trajectories
        """
        if isinstance(X, np.ndarray):
            if X.ndim == 2:
                mapped = self._map_array(X)
                return mapped
            else:
                raise TypeError('Input has the wrong shape: %s with %i'
                                ' dimensions. Expecting a matrix (2 dimensions)'
                                % (str(X.shape, X.ndim)))
        elif isinstance(X, (list, tuple)):
            out = []
            for x in X:
                mapped = self._map_array(x)
                out.append(mapped)
            return out
        else:
            raise TypeError('Input has the wrong type: %s '
                            '. Either accepting numpy arrays of dimension 2 '
                            'or lists of such arrays' % (str(type(X))))

    @abstractmethod
    def _map_array(self, X):
        r"""
        Initializes the parametrization.

        Parameters
        ----------
        X : ndarray(T, n)
            The input data, where T is the number of time steps and n is the number of dimensions.

        Returns
        -------
        Y : ndarray(T, d)
            The projected data, where T is the number of time steps of the input data and d is the output dimension
            of this transformer.

        """
        pass

    def _param_init(self):
        r"""
        Initializes the parametrization.
        """
        pass

    def _param_finish(self):
        r"""
        Finalizes the parametrization.
        """
        pass

    @abstractmethod
    def _param_add_data(self, *args, **kwargs):
        r""" Adds data to parameterization """
        pass

    def _map_to_memory(self, stride=1):
        r"""Maps results to memory. Will be stored in attribute :attr:`Y`."""
        self._logger.debug("mapping to mem")
        assert self._in_memory
        self._mapping_to_mem_active = True
        self._Y = self.get_output(stride=stride)
        self._mapping_to_mem_active = False

    def _reset(self, stride=1):
        r"""_reset data position"""
        # TODO: children of this do not call parametrize nor reset their data_producers.
        # check if this is an issue
        if not self._parametrized:
            self._logger.warning("reset(): not yet parametrized! Performing now.")
            self.parametrize()
        self._itraj = 0
        self._t = 0
        if not self.in_memory and self.data_producer is not self:
            # operate in pipeline
            self.data_producer._reset(stride=stride)

    def _next_chunk(self, lag=0, stride=1):
        r"""
        Transforms next available chunk from either in memory data or internal
        data_producer

        Parameters
        ----------
        lag  : int
            time delay of second data source.

        Returns
        -------
        X, (Y if lag > 0) : array_like
            mapped (transformed) data
        """
        if self.in_memory and not self._mapping_to_mem_active:
            if self._itraj >= self.number_of_trajectories():
                return None
            # operate in memory, implement iterator here
            traj_len = self.trajectory_length(self._itraj)
            if lag == 0:
                Y = self._Y[self._itraj][
                    self._t:min(self._t + self.chunksize*stride, traj_len):stride]
                # increment counters
                self._t += self.chunksize*stride
                if self._t >= traj_len:
                    self._itraj += 1
                    self._t = 0
                return Y
            else:
                Y0 = self._Y[self._itraj][
                    self._t:min(self._t + self.chunksize*stride, traj_len):stride]
                Ytau = self._Y[self._itraj][
                    self._t + lag*stride:min(self._t + (self.chunksize + lag)*stride, traj_len):stride]
                # increment counters
                self._t += self.chunksize*stride
                if self._t >= traj_len:
                    self._itraj += 1
                return (Y0, Ytau)
        else:
            # operate in pipeline
            if lag == 0:
                X = self.data_producer._next_chunk(stride=stride)
                self._t += X.shape[0]
                if self._t >= self.trajectory_length(self._itraj, stride=stride):
                    self._itraj += 1
                    self._t = 0
                return self.map(X)
            # TODO: this seems to be a dead branch of code
            else:
                (X0, Xtau) = self.data_producer._next_chunk(lag=lag, stride=stride)
                self._t += X0.shape[0]
                if self._t >= self.trajectory_length(self._itraj, stride=stride):
                    self._itraj += 1
                    self._t = 0
                return (self.map(X0), self.map(Xtau))

    def __iter__(self):
        r"""
        Returns an iterator that allows to access the transformed data.

        Returns
        -------
        iterator : a :class:`pyemma.coordinates.transfrom.TransformerIterator` transformer iterator
            a call to the .next() method of this iterator will return the pair
            (itraj, X) : (int, ndarray(n, m))
            where itraj corresponds to input sequence number (eg. trajectory index)
            and X is the transformed data, n = chunksize or n < chunksize at end
            of input.
        """
        self._reset()
        return TransformerIterator(self, stride=1, lag=0)

    def iterator(self, stride=1, lag=0):
        r"""
        Returns an iterator that allows to access the transformed data.

        Parameters
        ----------
        stride : int
            Only transform every N'th frame, default = 1
        lag : int
            Configure the iterator such that it will return time-lagged data
            with a lag time of `lag`. If `lag` is used together with `stride`
            the operation will work as if the striding operation is applied
            before the time-lagged trajectory is shifted by `lag` steps.
            Therefore the effective lag time will be stride*lag.

        Returns
        -------
        iterator : a :class:`pyemma.coordinates.transfrom.TransformerIterator` transformer iterator
            If lag = 0, a call to the .next() method of this iterator will return
            the pair
            (itraj, X) : (int, ndarray(n, m)),
            where itraj corresponds to input sequence number (eg. trajectory index)
            and X is the transformed data, n = chunksize or n < chunksize at end
            of input.

            If lag > 0, a call to the .next() method of this iterator will return
            the tuple
            (itraj, X, Y) : (int, ndarray(n, m), ndarray(p, m))
            where itraj and X are the same as above and Y contain the time-lagged
            data.
        """
        return TransformerIterator(self, stride=stride, lag=lag)

    def get_output(self, dimensions=slice(0, None), stride=1):
        r""" Maps all input data of this transformer and returns it as an array or list of arrays.

        Parameters
        ----------
        dimensions : list-like of indexes or slice
            indices of dimensions you like to keep, default = all
        stride : int
            only take every n'th frame, default = 1

        Returns
        -------
        output : ndarray(T, d) or list of ndarray(T_i, d)
            the mapped data, where T is the number of time steps of the input data, or if stride > 1,
            floor(T_in / stride). d is the output dimension of this transformer.
            If the input consists of a list of trajectories, Y will also be a corresponding list of trajectories

        Notes
        -----
        * This function may be RAM intensive if stride is too large or
          too many dimensions are selected.
        * if in_memory attribute is True, then results of this methods are cached.

        Example
        -------
        plotting trajectories

        >>> import pyemma.coordinates as coor # doctest: +SKIP
        >>> import matplotlib.pyplot as plt # doctest: +SKIP

        Fill with some actual data!
        >>> tica = coor.tica() # doctest: +SKIP
        >>> trajs = tica.get_output(dimensions=(0,), stride=100) # doctest: +SKIP
        >>> for traj in trajs: # doctest: +SKIP
        ...     plt.figure() # doctest: +SKIP
        ...     plt.plot(traj[:, 0]) # doctest: +SKIP

        """

        if isinstance(dimensions, int):
            ndim = 1
            dimensions = slice(dimensions, dimensions+1)
        elif isinstance(dimensions, list):
            ndim = len(np.zeros(self.dimension())[dimensions])
        elif isinstance(dimensions, np.ndarray):
            assert dimensions.ndim == 1, 'dimension indices can\'t have more than one dimension'
            ndim = len(np.zeros(self.dimension())[dimensions])
        elif isinstance(dimensions, slice):
            ndim = len(np.zeros(self.dimension())[dimensions])
        else:
            raise ValueError('unsupported type (%s) of \"dimensions\"' % type(dimensions))

        assert ndim > 0, "ndim was zero in %s" % self.__class__.__name__

        if not self._parametrized:
            self._logger.warning("has to be parametrized before getting output!"
                                 " Doing it now.")
            self.parametrize(stride)

        # if we are in memory and have results already computed, return them
        if self._in_memory:
            # ensure stride and dimensions are same of cached result
            if self._Y and all(self._Y[i].shape == (self.trajectory_length(i, stride=stride), ndim)
                               for i in xrange(self.number_of_trajectories())):
                return self._Y

        # allocate memory
        try:
            trajs = [np.empty((l, ndim), dtype=self.output_type())
                     for l in self.trajectory_lengths(stride=stride)]
        except MemoryError:
            self._logger.exception("Could not allocate enough memory to map all data."
                                   " Consider using a larger stride.")
            return

        if __debug__:
            self._logger.debug("get_output(): dimensions=%s" % str(dimensions))
            self._logger.debug("get_output(): created output trajs with shapes: %s"
                               % [x.shape for x in trajs])
        # fetch data
        last_itraj = -1
        t = 0  # first time point

        progress = ProgressBar(self._n_chunks(stride), description=
                               'getting output of ' + self.__class__.__name__)

        for itraj, chunk in self.iterator(stride=stride):
            if itraj != last_itraj:
                last_itraj = itraj
                t = 0  # reset time to 0 for new trajectory
            L = chunk.shape[0]
            trajs[itraj][t:t + L, :] = chunk[:, dimensions]
            t += L

            # update progress
            progress.numerator += 1
            show_progressbar(progress)

        if self._in_memory:
            self._Y = trajs

        return trajs
